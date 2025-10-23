import datetime
from collections import defaultdict
from itertools import combinations
import copy

from ortools.sat.python import cp_model
from django.db import transaction
from django.utils import timezone

from scheduling.models import (
    Subject, Section, Semester, Schedule, Room, GenEdSchedule
)
from core.models import Instructor
from instructors.models import InstructorAvailability
from aimatching.models import InstructorSubjectMatch


# ----------------- Configuration -----------------
TARGET_SEMESTER_ID = 16  # hard-coded as requested
DEFAULT_NORMAL_HOURS = 18  # fallback normal hours (in hours)
DEFAULT_OVERLOAD_UNITS = 6  # fallback overload units (units)
# windows
MORNING_START, MORNING_END = 8 * 60, 12 * 60
AFTERNOON_START, AFTERNOON_END = 13 * 60, 17 * 60
OVERLOAD_START, OVERLOAD_END = 17 * 60, 20 * 60

# objective weights (tune these as needed)
WEIGHT_MATCH = 1000
WEIGHT_ROOM_PRIORITY = 200000
# load balance: we will *minimize* overload imbalance (sum abs deviations scaled)
WEIGHT_LOAD_BALANCE = -1
# penalize total overload minutes as a secondary objective (negative because model.Maximize)
WEIGHT_OVERLOAD_PENALTY = -1


# ----------------- Helpers -----------------
def minutes_to_time(mins):
    hr = mins // 60
    m = mins % 60
    return datetime.time(hr, m)


def window_name_for_start(start_min, dur_min):
    if start_min >= MORNING_START and (start_min + dur_min) <= MORNING_END:
        return "morning"
    if start_min >= AFTERNOON_START and (start_min + dur_min) <= AFTERNOON_END:
        return "afternoon"
    if start_min >= OVERLOAD_START and (start_min + dur_min) <= OVERLOAD_END:
        return "overload"
    return None


def make_task_id(section_id, kind):
    return f"{section_id}__{kind}"


# get instructor normal / overload limits
# returns (normal_minutes, overload_units) where overload_units is number of units (not minutes)
def resolve_instructor_limits(instr: Instructor):
    # normal hours: designation.instructionHours -> rank.instructionHours -> instructor.normalLoad -> DEFAULT_NORMAL_HOURS
    normal_h = None
    try:
        if getattr(instr, "designation", None) and getattr(instr.designation, "instructionHours", None) is not None:
            normal_h = instr.designation.instructionHours
        elif getattr(instr, "rank", None) and getattr(instr.rank, "instructionHours", None) is not None:
            normal_h = instr.rank.instructionHours
        elif getattr(instr, "normalLoad", None) is not None:
            normal_h = instr.normalLoad
    except Exception:
        normal_h = None

    normal_h = int(normal_h) if normal_h else int(DEFAULT_NORMAL_HOURS)

    # overload units: academicAttainment.overloadUnitsHasDesignation / overloadUnitsNoDesignation -> instructor.overLoad -> DEFAULT_OVERLOAD_UNITS
    overload_units = None
    try:
        att = getattr(instr, "academicAttainment", None)
        if att:
            if getattr(instr, "designation", None):
                overload_units = getattr(att, "overloadUnitsHasDesignation", None)
            else:
                overload_units = getattr(att, "overloadUnitsNoDesignation", None)
    except Exception:
        overload_units = None

    if overload_units is None:
        overload_units = getattr(instr, "overLoad", None)

    overload_units = int(overload_units) if overload_units else int(DEFAULT_OVERLOAD_UNITS)

    # Return normal in minutes, overload in units
    return normal_h * 60, overload_units


# ----------------- Build tasks (lecture + lab) -----------------
def build_tasks_from_sections(sections):
    """
    Returns:
      tasks: list of task ids (str)
      task_to_section: {task: section_id}
      task_duration_min: {task: duration in minutes}
      task_units: {task: units (int)}  # units only meaningful for lecture tasks (0 for labs)
      lec_lab_pairs: [(lec_task, lab_task), ...]
    """
    tasks = []
    task_to_section = {}
    task_duration_min = {}
    task_units = {}
    lec_lab_pairs = []

    for sec in sections:
        subj = sec.subject
        # Prefer Subject DB exact minutes
        lec_min = int(getattr(subj, "durationMinutes", 0) or 0)
        lab_min = int(getattr(subj, "labDurationMinutes", 0) or 0) if getattr(subj, "hasLab", False) else 0

        # Units: try 'units' or 'creditUnits' fallback to 0
        units = int(getattr(subj, "units", None) or getattr(subj, "creditUnits", None) or 0)

        lec_task = None
        lab_task = None
        if lec_min > 0:
            lec_task = make_task_id(sec.sectionId, "lec")
            tasks.append(lec_task)
            task_to_section[lec_task] = sec.sectionId
            task_duration_min[lec_task] = lec_min
            task_units[lec_task] = units
        if lab_min > 0:
            lab_task = make_task_id(sec.sectionId, "lab")
            tasks.append(lab_task)
            task_to_section[lab_task] = sec.sectionId
            task_duration_min[lab_task] = lab_min
            # labs do not count toward normal load nor overload units
            task_units[lab_task] = 0

        if lec_task and lab_task:
            lec_lab_pairs.append((lec_task, lab_task))

    return tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs


# ----------------- Main scheduling function -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=30, interval_minutes=30):
    """
    Entry point: reads DB, builds CP-SAT model, solves, archives old schedules and saves new ones.

    Parameters
    - semester: either a Semester instance or a primary key (int). If None, falls back to TARGET_SEMESTER_ID.
    - time_limit_seconds: max solve time for OR-Tools.
    - interval_minutes: schedule start time granularity.
    """
    # Resolve semester: accept Semester instance, integer PK, or fallback to TARGET_SEMESTER_ID
    if semester is None:
        semester = Semester.objects.get(pk=TARGET_SEMESTER_ID)
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)
    # otherwise assume it's already a Semester instance

    print(f"[Solver] Semester: {semester}")

    # Archive old active schedules
    archived = Schedule.objects.filter(semester=semester, status='active').update(status='archived')
    print(f"[Solver] Archived {archived} old active schedules for semester {semester}")

    # Load DB data
    sections = list(Section.objects.filter(semester=semester).select_related("subject"))
    instructors = list(Instructor.objects.all())
    rooms = list(Room.objects.filter(isActive=True))
    gened_qs = list(GenEdSchedule.objects.filter(semester=semester))

    if not sections:
        print("[Solver] No sections found for semester — nothing to do.")
        return None

    if not instructors:
        print("[Solver] No instructors found — cannot schedule.")
        return None

    # Build tasks
    tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs = build_tasks_from_sections(sections)
    if not tasks:
        print("[Solver] No tasks (lecture/lab) built — nothing to schedule.")
        return None

    # Build time grid
    start_of_day = 8 * 60
    end_of_day = 20 * 60
    # generate start times spaced by interval_minutes but exclude starts in lunch (12:00-12:59)
    time_blocks = [t for t in range(start_of_day, end_of_day + 1, interval_minutes) if not (12 * 60 <= t < 13 * 60)]
    if not time_blocks:
        print("[Solver] No time blocks generated. Check interval_minutes.")
        return None

    # Precompute valid starts per task that fit entirely within a single window
    valid_starts = {}
    for t in tasks:
        dur = task_duration_min[t]
        vs = [s for s in time_blocks if window_name_for_start(s, dur) is not None]
        if not vs:
            print(f"[WARN] Task {t} (section {task_to_section[t]}) has no valid start times for duration {dur}min.")
        valid_starts[t] = vs

    # Build availability map: instructor_id -> {day_idx: [(start_min, end_min), ...]}
    avail_map = defaultdict(lambda: defaultdict(list))
    # First overlay any availability from InstructorAvailability table
    try:
        for ia in InstructorAvailability.objects.select_related("instructor").all():
            iid = ia.instructor.instructorId
            day_idx = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(ia.dayOfWeek, 0)
            s = ia.startTime.hour * 60 + ia.startTime.minute
            e = ia.endTime.hour * 60 + ia.endTime.minute
            avail_map[iid][day_idx].append((s, e))
    except Exception:
        pass

    # Also allow full availability for instructors with no availability entries (assume permanent)
    for instr in instructors:
        iid = instr.instructorId
        if iid not in avail_map or not avail_map[iid]:
            # assume available every day 08:00-20:00
            for d in range(7):
                avail_map[iid][d].append((8 * 60, 20 * 60))

    # GenEd blocks list: (day_idx, start_min, end_min)
    gened_blocks = []
    for g in gened_qs:
        sch = g.schedule
        day_idx = int(sch.dayOfWeek) if isinstance(sch.dayOfWeek, int) else {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(sch.dayOfWeek, 0)
        s = sch.startTime.hour * 60 + sch.startTime.minute
        e = sch.endTime.hour * 60 + sch.endTime.minute
        gened_blocks.append((day_idx, s, e))

    # Map for matches: section_id -> list of (instructorId, score)
    match_qs = InstructorSubjectMatch.objects.select_related("instructor", "subject").all()
    matches_by_subject = defaultdict(list)
    for m in match_qs:
        subj_id = m.subject.subjectId
        matches_by_subject[subj_id].append((m.instructor.instructorId, getattr(m, "confidenceScore", getattr(m, "isRecommended", 1.0))))

    # Build maps for quick lookup
    instructors_by_index = {idx: instr for idx, instr in enumerate(instructors)}
    instr_index_by_id = {instr.instructorId: idx for idx, instr in enumerate(instructors)}
    room_index_by_id = {r.roomId: idx for idx, r in enumerate(rooms)}
    num_rooms = len(rooms)
    TBA_ROOM_IDX = num_rooms  # allowed TBA index

    # Build per-subject metadata (kept minimal)
    subject_meta = {}
    for sec in sections:
        subj = sec.subject
        subject_meta[subj.subjectId] = {
            "is_gened": bool(getattr(subj.curriculum, "is_gened", False)) if getattr(subj, "curriculum", None) else False
        }

    # ------------- Build CP-SAT model -------------
    model = cp_model.CpModel()

    # Decision vars
    task_day = {}
    task_start = {}
    task_instr = {}
    task_room = {}

    # helper bools:
    # start_eq[t][s] : True iff task_start[t] == s
    # day_eq[t][d] : True iff task_day[t] == d
    start_eq = {}
    day_eq = {}
    # presence per (task,instructor): p_task_instr[t][iidx]
    p_task_instr = {}
    # presence per (task,room_idx): p_task_room[t][r]
    p_task_room = {}

    # create variables
    for t in tasks:
        # day 0..4 (Mon-Fri)
        task_day[t] = model.NewIntVar(0, 4, f"day_{t}")
        # start var domain from valid_starts if available; fallback to full time domain
        vs = valid_starts.get(t, [])
        if vs:
            task_start[t] = model.NewIntVarFromDomain(cp_model.Domain.FromValues(vs), f"start_{t}")
        else:
            task_start[t] = model.NewIntVar(8 * 60, 20 * 60, f"start_{t}")

        # instructor index var
        task_instr[t] = model.NewIntVar(0, len(instructors) - 1, f"instr_{t}")

        # room var (0..num_rooms or TBA)
        if num_rooms > 0:
            task_room[t] = model.NewIntVar(0, TBA_ROOM_IDX, f"room_{t}")
        else:
            # only TBA
            task_room[t] = model.NewIntVar(TBA_ROOM_IDX, TBA_ROOM_IDX, f"room_{t}")

        # create start_eq booleans for each valid start value
        start_eq[t] = {}
        for s in vs:
            b = model.NewBoolVar(f"start_{t}_is_{s}")
            start_eq[t][s] = b
            model.Add(task_start[t] == s).OnlyEnforceIf(b)
            model.Add(task_start[t] != s).OnlyEnforceIf(b.Not())
        if vs:
            model.Add(sum(start_eq[t].values()) == 1)

        # create day_eq booleans for 0..4
        day_eq[t] = {}
        for d in range(5):
            bd = model.NewBoolVar(f"day_{t}_is_{d}")
            day_eq[t][d] = bd
            model.Add(task_day[t] == d).OnlyEnforceIf(bd)
            model.Add(task_day[t] != d).OnlyEnforceIf(bd.Not())
        model.Add(sum(day_eq[t].values()) == 1)

        # presence per instructor for this task
        p_task_instr[t] = {}
        for iidx, instr in instructors_by_index.items():
            p = model.NewBoolVar(f"p_{t}_i{iidx}")
            p_task_instr[t][iidx] = p
            # reify relation between task_instr and p
            model.Add(task_instr[t] == iidx).OnlyEnforceIf(p)
            model.Add(task_instr[t] != iidx).OnlyEnforceIf(p.Not())

        # presence per room
        p_task_room[t] = {}
        for r_idx in range(TBA_ROOM_IDX + 1):
            pr = model.NewBoolVar(f"p_{t}_r{r_idx}")
            p_task_room[t][r_idx] = pr
            model.Add(task_room[t] == r_idx).OnlyEnforceIf(pr)
            model.Add(task_room[t] != r_idx).OnlyEnforceIf(pr.Not())
        model.Add(sum(p_task_room[t].values()) == 1)

    # ------------- Constraints -------------
    # 1) Each original section's lecture+lab tasks need assignment; no explicit "exactly once" because tasks exist once.
    # 2) Lecture/Lab same instructor + different day
    for lec_task, lab_task in lec_lab_pairs:
        model.Add(task_instr[lec_task] == task_instr[lab_task])
        model.Add(task_day[lec_task] != task_day[lab_task])

    # 3) instructor availability: forbid combinations (p_task_instr && day==d && start==s) when (d,s) not allowed
    for t in tasks:
        dur = task_duration_min[t]
        sec_id = task_to_section[t]
        for iidx, instr in instructors_by_index.items():
            iid = instr.instructorId
            # build set of allowed (d,s) for this instructor for this task
            allowed = set()
            avail = avail_map.get(iid, {})
            for d, blocks in avail.items():
                for blk_start, blk_end in blocks:
                    for s in valid_starts.get(t, []):
                        if s >= blk_start and (s + dur) <= blk_end:
                            allowed.add((d, s))
            # If allowed empty => cannot assign this instructor to this task
            if not allowed:
                model.Add(p_task_instr[t][iidx] == 0)
                continue
            # Forbid any (d,s) not in allowed by adding: p -> (day,d and start s) must not be true simultaneously
            for d in range(5):
                for s in valid_starts.get(t, []):
                    if (d, s) not in allowed:
                        # disallow p & day_eq & start_eq all true
                        model.AddBoolOr([p_task_instr[t][iidx].Not(), day_eq[t][d].Not(), start_eq[t][s].Not()])

    # 4) GenEd blocking: for tasks whose subject is not gened, forbid overlaps with any gened block on same day
    section_is_gened = {}
    for sec in sections:
        subj = sec.subject
        is_gened = False
        try:
            is_gened = bool(subj.curriculum and getattr(subj.curriculum, "is_gened", False))
        except Exception:
            is_gened = False
        section_is_gened[sec.sectionId] = is_gened

    for t in tasks:
        sec_id = task_to_section[t]
        if section_is_gened.get(sec_id, False):
            continue
        dur = task_duration_min[t]
        for (gday, gstart, gend) in gened_blocks:
            for s in valid_starts.get(t, []):
                # overlap if NOT (s+dur <= gstart or s >= gend)
                if not (s + dur <= gstart or s >= gend):
                    # forbid day==gday AND start==s for this task
                    model.AddBoolOr([day_eq[t][gday].Not(), start_eq[t][s].Not()])

    # 5) Room type matching: if room has .type and subject has .type, forbid mismatch
    for t in tasks:
        sec_id = task_to_section[t]
        subj = Section.objects.get(pk=sec_id).subject  # select_related not used here; small overhead
        subj_type = getattr(subj, "type", None)
        if subj_type is None:
            continue
        for r_idx, room in enumerate(rooms):
            room_type = getattr(room, "type", None)
            if room_type is None:
                continue
            if room_type != subj_type:
                # forbid assigning this room index to task: p_task_room[t][r_idx] == 0
                model.Add(p_task_room[t][r_idx] == 0)

    # 6) No-overlap per instructor and per room (if room != TBA)
    for iidx in instructors_by_index:
        for t1, t2 in combinations(tasks, 2):
            dur1 = task_duration_min[t1]
            dur2 = task_duration_min[t2]
            if dur1 <= 0 or dur2 <= 0:
                continue
            b1 = p_task_instr[t1][iidx]
            b2 = p_task_instr[t2][iidx]
            for d in range(5):
                t1_after_t2 = model.NewBoolVar(f"{t1}_after_{t2}_i{iidx}_d{d}")
                t2_after_t1 = model.NewBoolVar(f"{t2}_after_{t1}_i{iidx}_d{d}")
                model.Add(task_start[t1] >= task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2)
                model.Add(task_start[t1] < task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2.Not())
                model.Add(task_start[t2] >= task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1)
                model.Add(task_start[t2] < task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1.Not())

                model.AddBoolOr([b1.Not(), b2.Not(), day_eq[t1][d].Not(), day_eq[t2][d].Not(), t1_after_t2, t2_after_t1])

    # For room conflicts: for each real room r (not TBA), ensure that tasks assigned to it on same day do not overlap
    for r_idx in range(num_rooms):
        for t1, t2 in combinations(tasks, 2):
            dur1 = task_duration_min[t1]
            dur2 = task_duration_min[t2]
            if dur1 <= 0 or dur2 <= 0:
                continue
            b_r1 = p_task_room[t1][r_idx]
            b_r2 = p_task_room[t2][r_idx]
            for d in range(5):
                t1_after_t2 = model.NewBoolVar(f"{t1}_after_{t2}_r{r_idx}_d{d}")
                t2_after_t1 = model.NewBoolVar(f"{t2}_after_{t1}_r{r_idx}_d{d}")
                model.Add(task_start[t1] >= task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2)
                model.Add(task_start[t1] < task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2.Not())
                model.Add(task_start[t2] >= task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1)
                model.Add(task_start[t2] < task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1.Not())

                model.AddBoolOr([b_r1.Not(), b_r2.Not(), day_eq[t1][d].Not(), day_eq[t2][d].Not(), t1_after_t2, t2_after_t1])

    # 7) Enforce that every task has exactly one instructor and one room presence boolean is true — already ensured by reification above

    # 8) Instructor load constraints (normal vs overload)
    # Precompute is_normal_window[t] and is_overload_window[t] as BoolVars linked to start_eq booleans (keeps current logic of morning/afternoon vs overtime windows)
    is_normal = {}
    is_overload = {}
    for t in tasks:
        is_norm = model.NewBoolVar(f"is_normal_{t}")
        is_over = model.NewBoolVar(f"is_over_{t}")
        # normal if any start s in morning or afternoon
        morning_afternoon_bools = []
        overload_bools = []
        for s, b in start_eq[t].items():
            wn = window_name_for_start(s, task_duration_min[t])
            if wn in ("morning", "afternoon"):
                morning_afternoon_bools.append(b)
            elif wn == "overload":
                overload_bools.append(b)
        if morning_afternoon_bools:
            model.AddBoolOr(morning_afternoon_bools).OnlyEnforceIf(is_norm)
            model.AddBoolAnd([bb.Not() for bb in morning_afternoon_bools]).OnlyEnforceIf(is_norm.Not())
        else:
            model.Add(is_norm == 0)
        if overload_bools:
            model.AddBoolOr(overload_bools).OnlyEnforceIf(is_over)
            model.AddBoolAnd([bb.Not() for bb in overload_bools]).OnlyEnforceIf(is_over.Not())
        else:
            model.Add(is_over == 0)
        is_normal[t] = is_norm
        is_overload[t] = is_over

    # For each instructor compute total lecture minutes, total overload minutes (derived), and cap overload by attainment
    instr_total_lecture = {}
    instr_overload_minutes = {}
    instr_total_minutes = {}

    for iidx, instr in instructors_by_index.items():
        # normal limit (minutes) and overload limit (units)
        normal_limit_min, overload_limit_units = resolve_instructor_limits(instr)
        overload_limit_min = overload_limit_units * 60  # convert overload units to minutes (1 unit == 60 minutes)

        # Sum of lecture minutes assigned to this instructor
        lecture_terms = []
        total_terms = []
        overload_terms = []  # we'll still compute overload based on lecture minutes beyond normal, but need this list for completeness
        for t in tasks:
            dur = task_duration_min[t]
            if t.endswith("__lec"):
                # counts toward lecture load
                lecture_terms.append(p_task_instr[t][iidx] * dur)
            # total contribution (lecture + lab) - used for optional metrics
            total_terms.append(p_task_instr[t][iidx] * dur)

        # Create IntVars for totals
        total_lecture_min = model.NewIntVar(0, 20000, f"total_lecture_min_i{iidx}")
        total_min = model.NewIntVar(0, 40000, f"total_min_i{iidx}")

        if lecture_terms:
            model.Add(total_lecture_min == sum(lecture_terms))
        else:
            model.Add(total_lecture_min == 0)

        if total_terms:
            model.Add(total_min == sum(total_terms))
        else:
            model.Add(total_min == 0)

        # Overload minutes variable: overload when lecture exceeds normal_limit_min
        overload_min_var = model.NewIntVar(0, overload_limit_min, f"overload_min_i{iidx}")
        # Enforce overload_min_var >= total_lecture_min - normal_limit_min
        # and overload_min_var >= 0 (already by domain)
        # Since CP-SAT can't do max directly, we encode:
        # overload_min_var >= total_lecture_min - normal_limit_min
        model.Add(overload_min_var >= total_lecture_min - normal_limit_min)
        # Enforce hard cap: overload cannot exceed instructor's attainment-based cap (converted to minutes)
        model.Add(overload_min_var <= overload_limit_min)
        # Also enforce total lecture + (0) <= normal + overload cap (redundant given above but explicit)
        model.Add(total_lecture_min <= normal_limit_min + overload_limit_min)

        instr_total_lecture[iidx] = total_lecture_min
        instr_overload_minutes[iidx] = overload_min_var
        instr_total_minutes[iidx] = total_min

    # 9) Objective: combine match scores, room priority, minimize overload imbalance & total overload
    match_score_terms = []
    room_priority_terms = []
    subj_match_map = defaultdict(list)
    for subj_id, lst in matches_by_subject.items():
        subj_match_map[subj_id] = lst

    for t in tasks:
        sec_id = task_to_section[t]
        sec_obj = next((s for s in sections if s.sectionId == sec_id), None)
        subj_id = sec_obj.subject.subjectId if sec_obj else None
        for iidx, instr in instructors_by_index.items():
            iid = instr.instructorId
            score = 0.0
            for (mid, mscore) in subj_match_map.get(subj_id, []):
                if mid == iid:
                    score = float(mscore)
                    break
            if score:
                match_score_terms.append(p_task_instr[t][iidx] * int(round(score * WEIGHT_MATCH)))
        subj_obj = sec_obj.subject if sec_obj else None
        if subj_obj and getattr(subj_obj, "isPriorityForRooms", False):
            assigned_room_bool = model.NewBoolVar(f"room_assigned_{t}")
            if num_rooms > 0:
                model.AddBoolOr([p_task_room[t][r] for r in range(num_rooms)]).OnlyEnforceIf(assigned_room_bool)
                model.AddBoolAnd([p_task_room[t][r].Not() for r in range(num_rooms)]).OnlyEnforceIf(assigned_room_bool.Not())
            else:
                model.Add(assigned_room_bool == 0)
            room_priority_terms.append(assigned_room_bool * WEIGHT_ROOM_PRIORITY)

    # Build overload balancing measure:
    # We'll minimize sum of absolute deviations of each instructor's overload minutes from the average overload.
    # To avoid fractional average, use scaled diffs:
    # diff_scaled_i = overload_i * N - total_overload_sum
    instr_count = len(instructors)
    total_overload_sum = model.NewIntVar(0, 20000, "total_overload_sum")
    model.Add(total_overload_sum == sum(instr_overload_minutes.values()))

    abs_scaled_diffs = []
    for iidx in instr_overload_minutes:
        diff_scaled = model.NewIntVar(-200000, 200000, f"diff_scaled_i{iidx}")
        # diff_scaled = overload_i * N - total_overload_sum
        model.Add(diff_scaled == instr_overload_minutes[iidx] * instr_count - total_overload_sum)
        abs_scaled = model.NewIntVar(0, 200000, f"abs_scaled_i{iidx}")
        model.AddAbsEquality(abs_scaled, diff_scaled)
        abs_scaled_diffs.append(abs_scaled)

    # total overload minutes (to penalize overloads overall)
    total_overload_minutes = total_overload_sum

    # Combine objective terms
    objective_terms = []
    if match_score_terms:
        objective_terms.append(sum(match_score_terms))
    if room_priority_terms:
        objective_terms.append(sum(room_priority_terms))

    # Penalize overload imbalance (scaled absolute diffs)
    if abs_scaled_diffs:
        # sum(abs_scaled_diffs) scaled compared to minutes: note it's scaled by N; account in weight if needed
        objective_terms.append(WEIGHT_LOAD_BALANCE * sum(abs_scaled_diffs))

    # Penalize total overload minutes (secondary)
    objective_terms.append(WEIGHT_OVERLOAD_PENALTY * total_overload_minutes)

    # Maximize overall objective (match + room priority - imbalance - overload)
    model.Maximize(sum(objective_terms))

    # ---------- Solve ----------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 8
    print(f"[Solver] Solving {len(tasks)} tasks with {len(instructors)} instructors and {num_rooms} rooms...")
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("[Solver] No feasible solution found.")
        return None

    # ---------- Extract & Save schedule ----------
    schedules_to_create = []
    section_by_id = {s.sectionId: s for s in sections}
    room_by_index = {idx: r for idx, r in enumerate(rooms)}

    weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for t in tasks:
        sec_id = task_to_section[t]
        sec_obj = section_by_id.get(sec_id)
        subj_obj = sec_obj.subject if sec_obj else None

        assigned_iidx = solver.Value(task_instr[t])
        instr_obj = instructors_by_index[assigned_iidx]

        assigned_ridx = solver.Value(task_room[t])
        room_obj = None
        if assigned_ridx != TBA_ROOM_IDX:
            room_obj = room_by_index.get(assigned_ridx)

        assigned_day = int(solver.Value(task_day[t]))
        assigned_start = int(solver.Value(task_start[t]))
        dur = int(task_duration_min[t])
        start_time = minutes_to_time(assigned_start)
        end_time = minutes_to_time(assigned_start + dur)

        kind = "lecture" if t.endswith("__lec") else "lab"
        is_overtime = assigned_start >= OVERLOAD_START

        # Print assignment
        print(f"[Assign] Task {t} ({kind}) -> Section {sec_id} | Instr {instr_obj.instructorId} | Day {assigned_day} ({weekday[assigned_day]}) | Start {start_time} | Dur {dur} | Room {getattr(room_obj, 'roomCode', None)}")

        # Build Schedule instance (do not save yet)
        schedules_to_create.append(Schedule(
            subject=subj_obj,
            instructor=instr_obj,
            section=sec_obj,
            room=room_obj,
            semester=semester,
            dayOfWeek=weekday[assigned_day],
            startTime=start_time,
            endTime=end_time,
            scheduleType=kind,
            isOvertime=is_overtime,
            status='active'
        ))

    # Bulk create within transaction
    with transaction.atomic():
        Schedule.objects.bulk_create(schedules_to_create)
        print(f"[Solver] Saved {len(schedules_to_create)} schedules for semester {semester} (status='active').")

    return schedules_to_create


def generateSchedule():
    # You can customize args here if needed
    return solve_schedule_for_semester(time_limit_seconds=30, interval_minutes=30)


if __name__ == "__main__":
    print("Running generateSchedule() from scheduler/solver.py...")
    schedules = generateSchedule()
    if schedules:
        print(f"Generated {len(schedules)} schedules.")
    else:
        print("No schedules generated.")
