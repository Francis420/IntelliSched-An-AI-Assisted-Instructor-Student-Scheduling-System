# scheduler/solver.py
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
# windows (minutes)
MORNING_START, MORNING_END = 8 * 60, 12 * 60
AFTERNOON_START, AFTERNOON_END = 13 * 60, 17 * 60
OVERLOAD_START, OVERLOAD_END = 17 * 60, 20 * 60

# objective weights (tune these as needed)
WEIGHT_MATCH = 1000
WEIGHT_ROOM_PRIORITY = 200000

# Soft overload / fairness weights (integers)
SOFT_OVERLOAD_PENALTY = 50   # penalty per overload unit beyond cap (integer scale)
FAIRNESS_PENALTY = 20        # penalty per unit deviation from average overload


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
# returns (normal_minutes, overload_units)
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

    return normal_h * 60, overload_units  # normal in minutes, overload in units


# ----------------- Build tasks (lecture + lab) -----------------
def build_tasks_from_sections(sections):
    """
    Returns:
      tasks: list of task ids (str)
      task_to_section: {task: section_id}
      task_duration_min: {task: duration in minutes}
      task_units: {task: units (int)}  # units only for lecture tasks; labs = 0
      lec_lab_pairs: [(lec_task, lab_task), ...]
    """
    tasks = []
    task_to_section = {}
    task_duration_min = {}
    task_units = {}
    lec_lab_pairs = []

    for sec in sections:
        subj = sec.subject
        lec_min = int(getattr(subj, "durationMinutes", 0) or 0)
        lab_min = int(getattr(subj, "labDurationMinutes", 0) or 0) if getattr(subj, "hasLab", False) else 0
        units = int(getattr(subj, "units", 0) or 0)

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
            task_units[lab_task] = 0  # labs do not count toward normal load nor overload units

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
    # Resolve semester
    if semester is None:
        semester = Semester.objects.get(pk=TARGET_SEMESTER_ID)
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

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
    time_blocks = [t for t in range(start_of_day, end_of_day + 1, interval_minutes) if not (12 * 60 <= t < 13 * 60)]
    if not time_blocks:
        print("[Solver] No time blocks generated. Check interval_minutes.")
        return None

    # Precompute valid starts per task
    valid_starts = {}
    for t in tasks:
        dur = task_duration_min[t]
        vs = [s for s in time_blocks if window_name_for_start(s, dur) is not None]
        if not vs:
            print(f"[WARN] Task {t} (section {task_to_section[t]}) has no valid start times for duration {dur}min.")
        valid_starts[t] = vs

    # Build availability map
    avail_map = defaultdict(lambda: defaultdict(list))
    try:
        for ia in InstructorAvailability.objects.select_related("instructor").all():
            iid = ia.instructor.instructorId
            day_idx = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(ia.dayOfWeek, 0)
            s = ia.startTime.hour * 60 + ia.startTime.minute
            e = ia.endTime.hour * 60 + ia.endTime.minute
            avail_map[iid][day_idx].append((s, e))
    except Exception:
        pass

    for instr in instructors:
        iid = instr.instructorId
        if iid not in avail_map or not avail_map[iid]:
            for d in range(7):
                avail_map[iid][d].append((8 * 60, 20 * 60))

    # GenEd blocks list
    gened_blocks = []
    for g in gened_qs:
        sch = g.schedule
        day_idx = int(sch.dayOfWeek) if isinstance(sch.dayOfWeek, int) else {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(sch.dayOfWeek, 0)
        s = sch.startTime.hour * 60 + sch.startTime.minute
        e = sch.endTime.hour * 60 + sch.endTime.minute
        gened_blocks.append((day_idx, s, e))

    # Matches
    match_qs = InstructorSubjectMatch.objects.select_related("instructor", "subject").all()
    matches_by_subject = defaultdict(list)
    for m in match_qs:
        subj_id = m.subject.subjectId
        matches_by_subject[subj_id].append((m.instructor.instructorId, getattr(m, "confidenceScore", getattr(m, "isRecommended", 1.0))))

    # Quick maps
    instructors_by_index = {idx: instr for idx, instr in enumerate(instructors)}
    instr_index_by_id = {instr.instructorId: idx for idx, instr in enumerate(instructors)}
    room_index_by_id = {r.roomId: idx for idx, r in enumerate(rooms)}
    num_rooms = len(rooms)
    TBA_ROOM_IDX = num_rooms

    # Build subject metadata (minimal)
    subject_meta = {}
    for sec in sections:
        subj = sec.subject
        subject_meta[subj.subjectId] = {"is_gened": bool(getattr(subj.curriculum, "is_gened", False)) if getattr(subj, "curriculum", None) else False}

    # Build model
    model = cp_model.CpModel()

    # Decision vars and helpers
    task_day = {}
    task_start = {}
    task_instr = {}
    task_room = {}
    start_eq = {}
    day_eq = {}
    p_task_instr = {}
    p_task_room = {}

    for t in tasks:
        task_day[t] = model.NewIntVar(0, 6, f"day_{t}")
        vs = valid_starts.get(t, [])
        if vs:
            task_start[t] = model.NewIntVarFromDomain(cp_model.Domain.FromValues(vs), f"start_{t}")
        else:
            task_start[t] = model.NewIntVar(8 * 60, 20 * 60, f"start_{t}")

        task_instr[t] = model.NewIntVar(0, len(instructors) - 1, f"instr_{t}")
        if num_rooms > 0:
            task_room[t] = model.NewIntVar(0, TBA_ROOM_IDX, f"room_{t}")
        else:
            task_room[t] = model.NewIntVar(TBA_ROOM_IDX, TBA_ROOM_IDX, f"room_{t}")

        start_eq[t] = {}
        for s in vs:
            b = model.NewBoolVar(f"start_{t}_is_{s}")
            start_eq[t][s] = b
            model.Add(task_start[t] == s).OnlyEnforceIf(b)
            model.Add(task_start[t] != s).OnlyEnforceIf(b.Not())
        if vs:
            model.Add(sum(start_eq[t].values()) == 1)

        day_eq[t] = {}
        for d in range(7):
            bd = model.NewBoolVar(f"day_{t}_is_{d}")
            day_eq[t][d] = bd
            model.Add(task_day[t] == d).OnlyEnforceIf(bd)
            model.Add(task_day[t] != d).OnlyEnforceIf(bd.Not())
        model.Add(sum(day_eq[t].values()) == 1)

        p_task_instr[t] = {}
        for iidx, instr in instructors_by_index.items():
            p = model.NewBoolVar(f"p_{t}_i{iidx}")
            p_task_instr[t][iidx] = p
            model.Add(task_instr[t] == iidx).OnlyEnforceIf(p)
            model.Add(task_instr[t] != iidx).OnlyEnforceIf(p.Not())

        p_task_room[t] = {}
        for r_idx in range(TBA_ROOM_IDX + 1):
            pr = model.NewBoolVar(f"p_{t}_r{r_idx}")
            p_task_room[t][r_idx] = pr
            model.Add(task_room[t] == r_idx).OnlyEnforceIf(pr)
            model.Add(task_room[t] != r_idx).OnlyEnforceIf(pr.Not())
        model.Add(sum(p_task_room[t].values()) == 1)

    # Constraints
    # Lecture/Lab pairing: same instructor, different day
    for lec_task, lab_task in lec_lab_pairs:
        model.Add(task_instr[lec_task] == task_instr[lab_task])
        model.Add(task_day[lec_task] != task_day[lab_task])

    # Instructor availability constraints
    for t in tasks:
        dur = task_duration_min[t]
        for iidx, instr in instructors_by_index.items():
            iid = instr.instructorId
            allowed = set()
            avail = avail_map.get(iid, {})
            for d, blocks in avail.items():
                for blk_start, blk_end in blocks:
                    for s in valid_starts.get(t, []):
                        if s >= blk_start and (s + dur) <= blk_end:
                            allowed.add((d, s))
            if not allowed:
                model.Add(p_task_instr[t][iidx] == 0)
                continue
            for d in range(7):
                for s in valid_starts.get(t, []):
                    if (d, s) not in allowed:
                        model.AddBoolOr([p_task_instr[t][iidx].Not(), day_eq[t][d].Not(), start_eq[t][s].Not()])

    # GenEd blocking
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
                if not (s + dur <= gstart or s >= gend):
                    model.AddBoolOr([day_eq[t][gday].Not(), start_eq[t][s].Not()])

    # Room-type matching
    for t in tasks:
        sec_id = task_to_section[t]
        subj = Section.objects.get(pk=sec_id).subject

        # Determine what kind of room is needed
        if t.endswith("__lab"):
            required_type = "Laboratory"
        else:
            required_type = "Lecture"

        for r_idx, room in enumerate(rooms):
            room_type = getattr(room, "type", None)
            if room_type is None:
                continue
            # If the room type does not match what’s required, forbid assignment
            if room_type.lower() != required_type.lower():
                model.Add(p_task_room[t][r_idx] == 0)
        
        # allow TBA if no valid room is found
        if any(room_type.lower() == required_type.lower() for room_type in [getattr(r, "type", "").lower() for r in rooms]):
            model.Add(task_room[t] != TBA_ROOM_IDX)


    # No-overlap per instructor and per room
    for iidx in instructors_by_index:
        for t1, t2 in combinations(tasks, 2):
            dur1 = task_duration_min[t1]
            dur2 = task_duration_min[t2]
            if dur1 <= 0 or dur2 <= 0:
                continue
            b1 = p_task_instr[t1][iidx]
            b2 = p_task_instr[t2][iidx]
            for d in range(7):
                t1_after_t2 = model.NewBoolVar(f"{t1}_after_{t2}_i{iidx}_d{d}")
                t2_after_t1 = model.NewBoolVar(f"{t2}_after_{t1}_i{iidx}_d{d}")
                model.Add(task_start[t1] >= task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2)
                model.Add(task_start[t1] < task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2.Not())
                model.Add(task_start[t2] >= task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1)
                model.Add(task_start[t2] < task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1.Not())
                model.AddBoolOr([b1.Not(), b2.Not(), day_eq[t1][d].Not(), day_eq[t2][d].Not(), t1_after_t2, t2_after_t1])

    for r_idx in range(num_rooms):
        for t1, t2 in combinations(tasks, 2):
            dur1 = task_duration_min[t1]
            dur2 = task_duration_min[t2]
            if dur1 <= 0 or dur2 <= 0:
                continue
            b_r1 = p_task_room[t1][r_idx]
            b_r2 = p_task_room[t2][r_idx]
            for d in range(7):
                t1_after_t2 = model.NewBoolVar(f"{t1}_after_{t2}_r{r_idx}_d{d}")
                t2_after_t1 = model.NewBoolVar(f"{t2}_after_{t1}_r{r_idx}_d{d}")
                model.Add(task_start[t1] >= task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2)
                model.Add(task_start[t1] < task_start[t2] + dur2).OnlyEnforceIf(t1_after_t2.Not())
                model.Add(task_start[t2] >= task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1)
                model.Add(task_start[t2] < task_start[t1] + dur1).OnlyEnforceIf(t2_after_t1.Not())
                model.AddBoolOr([b_r1.Not(), b_r2.Not(), day_eq[t1][d].Not(), day_eq[t2][d].Not(), t1_after_t2, t2_after_t1])

    # Precompute is_normal / is_overload windows per task
    is_normal = {}
    is_overload = {}
    for t in tasks:
        is_norm = model.NewBoolVar(f"is_normal_{t}")
        is_over = model.NewBoolVar(f"is_over_{t}")
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

    # Instructor load constraints:
    # - normal load counts only lecture tasks scheduled in normal windows (morning/afternoon): minutes
    # - overload counts only lecture tasks scheduled in overload window: units
    instr_total_normal_minutes = {}
    instr_total_overload_units = {}
    instr_total_minutes = {}

    for iidx, instr in instructors_by_index.items():
        normal_limit_min, overload_limit_units = resolve_instructor_limits(instr)
        # make sum of lecture minutes in normal windows assigned to this instructor
        normal_terms = []
        total_terms = []
        overload_unit_terms = []  # units for lecture tasks assigned in overload window
        for t in tasks:
            dur = task_duration_min[t]
            units = task_units.get(t, 0)
            total_terms.append(p_task_instr[t][iidx] * dur)
            if t.endswith("__lec"):
                # lecture tasks: contribute to normal or overload depending on window
                # normal window contribution (minutes)
                c_norm = model.NewBoolVar(f"c_norm_{t}_i{iidx}")
                model.AddBoolAnd([p_task_instr[t][iidx], is_normal[t]]).OnlyEnforceIf(c_norm)
                model.AddBoolOr([p_task_instr[t][iidx].Not(), is_normal[t].Not()]).OnlyEnforceIf(c_norm.Not())
                normal_terms.append(c_norm * dur)
                # overload window contribution (units)
                c_over_unit = model.NewBoolVar(f"c_over_unit_{t}_i{iidx}")
                model.AddBoolAnd([p_task_instr[t][iidx], is_overload[t]]).OnlyEnforceIf(c_over_unit)
                model.AddBoolOr([p_task_instr[t][iidx].Not(), is_overload[t].Not()]).OnlyEnforceIf(c_over_unit.Not())
                # only count units when in overload window
                overload_unit_terms.append(c_over_unit * units)
            else:
                # labs do not contribute to normal minutes nor to overload units
                pass

        total_normal_min = model.NewIntVar(0, 20000, f"total_normal_min_i{iidx}")
        total_min = model.NewIntVar(0, 40000, f"total_min_i{iidx}")
        if normal_terms:
            model.Add(total_normal_min == sum(normal_terms))
        else:
            model.Add(total_normal_min == 0)
        if total_terms:
            model.Add(total_min == sum(total_terms))
        else:
            model.Add(total_min == 0)

        # overload units assigned in overload window
        total_overload_units_var = model.NewIntVar(0, 2000, f"total_overload_units_i{iidx}")
        if overload_unit_terms:
            model.Add(total_overload_units_var == sum(overload_unit_terms))
        else:
            model.Add(total_overload_units_var == 0)

        # Enforce hard caps:
        # - normal lecture minutes must not exceed instructor's normal minutes
        model.Add(total_normal_min <= normal_limit_min)
        # - overload units assigned (in overload window) must not exceed a high cap (we will soft-penalize actual desired cap below)
        # keep a safety hard cap so variables don't blow up; realistic upper bound:
        model.Add(total_overload_units_var <= 2000)

        instr_total_normal_minutes[iidx] = total_normal_min
        instr_total_overload_units[iidx] = total_overload_units_var
        instr_total_minutes[iidx] = total_min

    # -------------------------
    # Build match and room-priority terms (existing objective building)
    # -------------------------
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

    # -------------------------
    # Soft overload penalty per instructor (uses attainment caps)
    # -------------------------
    overload_excess_vars = []
    for iidx, instr in instructors_by_index.items():
        # get attainment cap for this instructor
        _, cap_units = resolve_instructor_limits(instr)
        cap_units = int(cap_units)

        # create overload excess var: max(0, assigned_overload_units - cap_units)
        excess = model.NewIntVar(0, 2000, f"overload_excess_i{iidx}")
        # constraint: excess >= assigned_overload - cap
        model.Add(excess >= instr_total_overload_units[iidx] - cap_units)
        # also excess >= 0 already implied by var domain
        overload_excess_vars.append(excess)

    # -------------------------
    # Fairness: penalize deviation from average overload
    # -------------------------
    instr_count = len(instructors)
    total_overload_units_sum = model.NewIntVar(0, 20000, "total_overload_units_sum")
    model.Add(total_overload_units_sum == sum(instr_total_overload_units.values()))

    avg_overload = model.NewIntVar(0, 20000, "avg_overload")
    # integer division equality (avg_overload = total_overload_units_sum // instr_count)
    model.AddDivisionEquality(avg_overload, total_overload_units_sum, max(1, instr_count))

    deviation_vars = []
    for iidx in instr_total_overload_units:
        diff = model.NewIntVar(-20000, 20000, f"diff_i{iidx}")
        model.Add(diff == instr_total_overload_units[iidx] - avg_overload)
        dev = model.NewIntVar(0, 20000, f"deviation_i{iidx}")
        model.AddAbsEquality(dev, diff)
        deviation_vars.append(dev)

    # -------------------------
    # Final objective: maximize match scores + room priority, minus overload penalties and fairness penalties
    # -------------------------
    # Build objective expression parts
    objective_terms = []
    if match_score_terms:
        objective_terms.append(sum(match_score_terms))
    if room_priority_terms:
        objective_terms.append(sum(room_priority_terms))

    # Subtract penalties (we maximize)
    if overload_excess_vars:
        objective_terms.append(- SOFT_OVERLOAD_PENALTY * sum(overload_excess_vars))
    if deviation_vars:
        objective_terms.append(- FAIRNESS_PENALTY * sum(deviation_vars))

    # Final maximize
    model.Maximize(sum(objective_terms))

    # ---------- Solve ----------
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 8
    solver.parameters.max_time_in_seconds = 300
    solver.parameters.random_seed = 42
    solver.parameters.log_search_progress = True
    solver.parameters.cp_model_presolve = True
    solver.parameters.cp_model_probing_level = 0 
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

    # Debug info build: per-instructor totals
    per_instructor_info = []

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

        print(f"[Assign] Task {t} ({kind}) -> Section {sec_id} | Instr {instr_obj.instructorId} | Day {assigned_day} ({weekday[assigned_day]}) | Start {start_time} | Dur {dur} | Room {getattr(room_obj, 'roomCode', None)}")

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

    # Build and print per-instructor summary
    print("\n[Solver] Per-instructor load summary (limits and assignments):")
    for iidx, instr in instructors_by_index.items():
        normal_limit_min, overload_limit_units = resolve_instructor_limits(instr)
        assigned_normal_min = solver.Value(instr_total_normal_minutes[iidx])
        assigned_overload_units = solver.Value(instr_total_overload_units[iidx])
        total_min = solver.Value(instr_total_minutes[iidx])
        # overload excess value (soft penalty)
        # compute excess var name and print if exists
        try:
            excess_val = solver.Value(model.GetVarFromProtoName(f"overload_excess_i{iidx}"))
        except Exception:
            excess_val = None
        print(f" - {instr.instructorId}: normal_limit={normal_limit_min}min ({normal_limit_min/60:.2f}h), "
              f"overload_limit={overload_limit_units} units, assigned_normal={assigned_normal_min}min ({assigned_normal_min/60:.2f}h), "
              f"assigned_overload_units={assigned_overload_units}, total_minutes_assigned={total_min}min ({total_min/60:.2f}h), overload_excess={excess_val}")

    # Bulk create schedules
    with transaction.atomic():
        Schedule.objects.bulk_create(schedules_to_create)
        print(f"[Solver] Saved {len(schedules_to_create)} schedules for semester {semester} (status='active').")

    return schedules_to_create


def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=3600, interval_minutes=30)


if __name__ == "__main__":
    print("Running generateSchedule() from scheduler/solver.py...")
    schedules = generateSchedule()
    if schedules:
        print(f"Generated {len(schedules)} schedules.")
    else:
        print("No schedules generated.")
