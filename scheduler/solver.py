# scheduler/solver.py  (UPDATED)
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
from aimatching.models import InstructorSubjectMatch

# ----------------- Configuration -----------------
TARGET_SEMESTER_ID = 16  # fallback
DEFAULT_NORMAL_HOURS = 18  # fallback normal hours (in hours)
# windows (minutes)
GLOBAL_DAY_START, GLOBAL_DAY_END = 8 * 60, 20 * 60  # 08:00 - 20:00
LUNCH_START, LUNCH_END = 12 * 60, 13 * 60  # lunch gap

# objective weights (tune if needed)
WEIGHT_MATCH = 1000
WEIGHT_ROOM_PRIORITY = 200000

# Soft overload / fairness weights (still usable for distribution but hard caps enforced for permanent instructors)
SOFT_OVERLOAD_PENALTY = 50
FAIRNESS_PENALTY = 20


# ----------------- Helpers -----------------
def minutes_to_time(mins):
    hr = mins // 60
    m = mins % 60
    return datetime.time(hr, m)


def window_name_for_start(start_min, dur_min):
    """
    Classify start+dur into 'normal' or 'overload' windows according to final rules:
    - Normal windows: Mon-Fri 08:00-12:00 and 13:00-17:00
    - Overload windows:
        - Mon-Fri 17:00-20:00
        - Sat-Sun 08:00-12:00 and 13:00-20:00
    Note: This function only tells window type for a start time and duration independent of day;
    caller must combine with day index to decide allowed window types for that day.
    Returns: "normal", "overload", or None if not fully inside any allowed window (e.g. overlaps lunch)
    """
    # Accept only starts that do not overlap lunch and fit within global day bounds
    end = start_min + dur_min
    if start_min < GLOBAL_DAY_START or end > GLOBAL_DAY_END:
        return None
    # If it crosses lunch, it's invalid (we don't allow splits across lunch)
    if not (end <= LUNCH_START or start_min >= LUNCH_END):
        return None

    # For general classification by time-of-day (day-specific logic applied by caller)
    # Return "normal" if it fits entirely in a normal window (08-12 or 13-17)
    if (GLOBAL_DAY_START <= start_min and end <= LUNCH_START) or (LUNCH_END <= start_min and end <= 17 * 60):
        return "normal"
    # Return "overload" if it fits entirely in 17:00-20:00 or (for weekends) 08-12 or 13-20,
    # caller will decide if the day is weekend or weekday.
    if start_min >= 17 * 60 and end <= GLOBAL_DAY_END:
        return "overload"
    # For weekend day classification, caller can also treat normal windows of weekend as overload
    return None


def make_task_id(section_id, kind, part=None):
    if part:
        return f"{section_id}__{kind}_p{part}"
    return f"{section_id}__{kind}"


# get instructor normal / overload limits
# returns (normal_minutes, overload_minutes, employmentType, has_designation_flag)
def resolve_instructor_limits(instr: Instructor):
    """
    Implements the final employmentType logic:
    - If employmentType == 'on-leave/retired' -> should be excluded (handled upstream).
    - For 'permanent':
        - normal_limit_hours = designation.instructionHours if designation else rank.instructionHours (fallback DEFAULT_NORMAL_HOURS)
        - overload_limit_hours = 9 if has designation else 12
        Both are hard caps.
    - For 'part-time': no caps (return very large caps or special marker)
    - For 'overload' (Part-Time (Overload)): no caps but restricted windows
    Returns minutes.
    """
    employment = getattr(instr, "employmentType", "").lower() if getattr(instr, "employmentType", None) else "permanent"
    has_designation = getattr(instr, "designation", None) is not None

    # Normal hours
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

    # Overload caps (hours)
    # For permanent: if has designation -> 9h, else 12h
    # For others: we will return large caps (no hard limit) but enforcement differs by employmentType
    if employment == "permanent":
        overload_h = 9 if has_designation else 12
        # ensure normal cap is not greater than some sanity bound, but leave as-is
        return normal_h * 60, overload_h * 60, employment, has_designation
    elif employment == "part-time":
        # no caps; return large sentinel
        return 10_000 * 60, 10_000 * 60, employment, has_designation
    elif employment.lower().startswith("overload"):
        # overload-only instructors: no caps but restricted in allowed windows
        return 10_000 * 60, 10_000 * 60, "overload", has_designation
    else:
        # default treat as permanent if unspecified
        overload_h = 9 if has_designation else 12
        return normal_h * 60, overload_h * 60, "permanent", has_designation


# ----------------- Build tasks (lecture + lab) -----------------
def build_tasks_from_sections(sections, interval_minutes=30):
    """
    Returns:
      tasks: list of task ids (str)
      task_to_section: {task: section_id}
      task_duration_min: {task: duration in minutes}
      task_units: {task: units (int)}  # units retained for compatibility but not used for overload
      lec_lab_pairs: [(lec_task, lab_task), ...]  # lecture task ids may be p1/p2
    Splitting logic:
      - If lecture durationMinutes > 120, split into two tasks of roughly equal minutes (respecting integer mins).
      - Lab tasks are not split.
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

        lec_tasks = []
        if lec_min > 0:
            if lec_min > 120:
                # Split into two parts roughly equal, prefer rounding to nearest interval if possible
                half1 = lec_min // 2
                half2 = lec_min - half1
                # adjust halves to align with interval_minutes if possible
                def align(x):
                    rem = x % interval_minutes
                    if rem == 0:
                        return x
                    # try shifting down to nearest multiple (prefer not to exceed original total)
                    return x - rem
                # Try to align both halves, but ensure sum equals original (we'll fix remainder)
                a1 = align(half1)
                a2 = align(half2)
                if a1 <= 0:
                    a1 = half1
                if a2 <= 0:
                    a2 = half2
                # if alignment changed total, distribute leftover to second part
                diff = lec_min - (a1 + a2)
                a2 += diff
                # final guard
                if a1 <= 0 or a2 <= 0:
                    a1 = half1
                    a2 = half2
                # create two lecture tasks
                t1 = make_task_id(sec.sectionId, "lec", part=1)
                t2 = make_task_id(sec.sectionId, "lec", part=2)
                lec_tasks = [t1, t2]
                tasks.extend(lec_tasks)
                task_to_section[t1] = sec.sectionId
                task_to_section[t2] = sec.sectionId
                task_duration_min[t1] = a1
                task_duration_min[t2] = a2
                task_units[t1] = units
                task_units[t2] = units
            else:
                t = make_task_id(sec.sectionId, "lec")
                lec_tasks = [t]
                tasks.append(t)
                task_to_section[t] = sec.sectionId
                task_duration_min[t] = lec_min
                task_units[t] = units

        lab_task = None
        if lab_min > 0:
            lt = make_task_id(sec.sectionId, "lab")
            tasks.append(lt)
            task_to_section[lt] = sec.sectionId
            task_duration_min[lt] = lab_min
            task_units[lt] = 0  # labs don't contribute units per previous semantics; but now they count minutes
            lab_task = lt

        # Build lec-lab pairing: each lecture part pairs with the single lab (if both present)
        if lec_tasks and lab_task:
            for lec_t in lec_tasks:
                lec_lab_pairs.append((lec_t, lab_task))

    return tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs


# ----------------- Main scheduling function -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=30, interval_minutes=30):
    """
    Updated solver implementing minute-based overloads and new employmentType/time window rules.
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
    instructors_all = list(Instructor.objects.all())
    # Filter out on-leave/retired instructors from pool
    instructors = [i for i in instructors_all if (getattr(i, "employmentType", "") or "").lower() != "on-leave/retired"]
    rooms = list(Room.objects.filter(isActive=True))
    gened_qs = list(GenEdSchedule.objects.filter(semester=semester))

    if not sections:
        print("[Solver] No sections found for semester — nothing to do.")
        return None
    if not instructors:
        print("[Solver] No instructors available for scheduling (all filtered out or none exist).")
        return None

    # Build tasks
    tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs = build_tasks_from_sections(sections, interval_minutes=interval_minutes)
    if not tasks:
        print("[Solver] No tasks (lecture/lab) built — nothing to schedule.")
        return None

    # Build time grid (respecting 8:00-20:00 and skipping lunch 12:00-13:00)
    start_of_day = GLOBAL_DAY_START
    end_of_day = GLOBAL_DAY_END
    time_blocks = [t for t in range(start_of_day, end_of_day + 1, interval_minutes) if not (LUNCH_START <= t < LUNCH_END)]
    if not time_blocks:
        print("[Solver] No time blocks generated. Check interval_minutes.")
        return None

    # Precompute valid starts per task (start times that fit entirely within day windows and don't overlap lunch)
    valid_starts = {}
    for t in tasks:
        dur = task_duration_min[t]
        vs = [s for s in time_blocks if (s + dur) <= end_of_day and window_name_for_start(s, dur) is not None]
        if not vs:
            print(f"[WARN] Task {t} (section {task_to_section[t]}) has no valid start times for duration {dur}min.")
        valid_starts[t] = vs

    # GenEd blocks list (day_idx, start, end)
    gened_blocks = []
    for g in gened_qs:
        sch = g.schedule
        day_idx = int(sch.dayOfWeek) if isinstance(sch.dayOfWeek, int) else {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(sch.dayOfWeek, 0)
        s = sch.startTime.hour * 60 + sch.startTime.minute
        e = sch.endTime.hour * 60 + sch.endTime.minute
        gened_blocks.append((day_idx, s, e))

    # Matches by subject
    match_qs = InstructorSubjectMatch.objects.select_related("instructor", "subject").all()
    matches_by_subject = defaultdict(list)
    for m in match_qs:
        subj_id = m.subject.subjectId
        # try confidenceScore first, fallback to isRecommended
        score = getattr(m, "confidenceScore", None)
        if score is None:
            score = 1.0 if getattr(m, "isRecommended", False) else 0.0
        matches_by_subject[subj_id].append((m.instructor.instructorId, float(score)))

    # Quick maps and indices
    instructors_by_index = {idx: instr for idx, instr in enumerate(instructors)}
    instr_index_by_id = {instr.instructorId: idx for idx, instr in enumerate(instructors)}
    room_index_by_id = {r.roomId: idx for idx, r in enumerate(rooms)}
    num_rooms = len(rooms)
    TBA_ROOM_IDX = num_rooms

    # Employment and caps map per instructor index
    instr_caps = {}
    for iidx, instr in instructors_by_index.items():
        normal_min, overload_min, employment, has_designation = resolve_instructor_limits(instr)
        instr_caps[iidx] = {
            "normal_limit_min": normal_min,
            "overload_limit_min": overload_min,
            "employment": employment,
            "has_designation": has_designation
        }

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
            # keep fallback domain but will likely be infeasible
            task_start[t] = model.NewIntVar(GLOBAL_DAY_START, GLOBAL_DAY_END, f"start_{t}")

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
    # Lecture/Lab pairing: same instructor, lecture parts on different days
    for lec_task, lab_task in lec_lab_pairs:
        model.Add(task_instr[lec_task] == task_instr[lab_task])
        # keep day != day between lec and lab if desired (existing behavior)
        model.Add(task_day[lec_task] != task_day[lab_task])

    # If lecture was split into p1/p2, ensure they are same instructor and different days
    # find split pairs by naming convention
    lec_split_map = {}
    for t in tasks:
        if "__lec_p1" in t:
            sec = task_to_section[t]
            p2 = f"{sec}__lec_p2"
            if p2 in tasks:
                lec_split_map[t] = p2
    for p1, p2 in lec_split_map.items():
        model.Add(task_instr[p1] == task_instr[p2])
        model.Add(task_day[p1] != task_day[p2])

    # Employment-type time restrictions & availability rule removal
    # We will forbid assignment of tasks that fall into windows not allowed by employmentType
    # To do that, first prepare per-task per-day start-window booleans (is_normal/is_overload)
    is_normal = {}
    is_overload = {}
    # Precompute for each task which (day, start) pairs correspond to normal or overload windows
    task_start_day_allowed = {}  # task -> {(day, start): "normal"/"overload"}
    for t in tasks:
        dur = task_duration_min[t]
        mapping = {}
        for d in range(7):
            # For each valid start s, determine if it's fully in a normal/overload window for day d
            for s in valid_starts.get(t, []):
                # classify by time-of-day first
                base_class = window_name_for_start(s, dur)
                if base_class is None:
                    continue
                # Now determine if on this day that base_class corresponds to normal or overload
                # weekday 0-4: Mon-Fri
                if d <= 4:
                    # Mon-Fri: base_class "normal" => normal; base_class "overload" => overload
                    if base_class == "normal":
                        mapping[(d, s)] = "normal"
                    elif base_class == "overload":
                        mapping[(d, s)] = "overload"
                else:
                    # Saturday/Sunday: treat day-time 08-12 and 13-20 as overload windows (per final rules)
                    # recall window_name_for_start returns "normal" for 08-12 and 13-17; treat as overload on weekends
                    if base_class == "normal":
                        mapping[(d, s)] = "overload"
                    elif base_class == "overload":
                        # evening 17-20 on weekend still overload
                        mapping[(d, s)] = "overload"
        task_start_day_allowed[t] = mapping

    # Create boolean helpers is_normal[t] and is_overload[t] as true if assigned start/day maps to that class
    for t in tasks:
        bool_norm = model.NewBoolVar(f"is_normal_{t}")
        bool_over = model.NewBoolVar(f"is_over_{t}")
        # Build clauses from p_task_instr & day_eq & start_eq
        norm_clauses = []
        over_clauses = []
        # For each instructor option, we will express implication below; but here gather start/day mapping
        for (d, s), typ in task_start_day_allowed.get(t, {}).items():
            # a potential indicator that (day==d and start==s) -> typ
            conj = model.NewBoolVar(f"pair_{t}_d{d}_s{s}")
            # conj implies both day_eq and start_eq
            model.AddBoolAnd([day_eq[t][d], start_eq[t][s]]).OnlyEnforceIf(conj)
            model.AddBoolOr([day_eq[t][d].Not(), start_eq[t][s].Not()]).OnlyEnforceIf(conj.Not())
            if typ == "normal":
                norm_clauses.append(conj)
            elif typ == "overload":
                over_clauses.append(conj)
        # if any norm_clauses present, bool_norm == OR(norm_clauses)
        if norm_clauses:
            model.AddBoolOr(norm_clauses).OnlyEnforceIf(bool_norm)
            model.AddBoolAnd([c.Not() for c in norm_clauses]).OnlyEnforceIf(bool_norm.Not())
        else:
            model.Add(bool_norm == 0)
        if over_clauses:
            model.AddBoolOr(over_clauses).OnlyEnforceIf(bool_over)
            model.AddBoolAnd([c.Not() for c in over_clauses]).OnlyEnforceIf(bool_over.Not())
        else:
            model.Add(bool_over == 0)
        is_normal[t] = bool_norm
        is_overload[t] = bool_over

    # Now enforce employment-type restrictions:
    # - For 'overload' instructors: forbid assignment if task is NOT overload (i.e., is_normal==True)
    # - For 'part-time' instructors: no caps or time restrictions (except global 08-20 which is already enforced)
    # - For 'permanent' instructors: allowed anywhere but will be subject to hard caps checked later
    for t in tasks:
        for iidx, instr in instructors_by_index.items():
            emp = instr_caps[iidx]["employment"]
            if emp == "overload":
                # if task is normal -> cannot assign to this instructor
                # model.Add(p_task_instr[t][iidx] == 0) if is_normal[t] else allowed
                # Implement as: p => is_overload[t] (i.e. p implies is_over)
                model.AddImplication(p_task_instr[t][iidx], is_overload[t])
            elif emp == "permanent":
                # permanent instructors can be assigned anywhere but ultimately caps will be enforced
                pass
            elif emp == "part-time":
                # part-time: no further enforcement here
                pass
            else:
                pass

    # GenEd blocking (unchanged): sections that are gened should not intersect gened blocks
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

    # Room-type matching (unchanged)
    for t in tasks:
        sec_id = task_to_section[t]
        subj = Section.objects.get(pk=sec_id).subject

        # Determine what kind of room is needed
        if t.endswith("__lab") or "__lab" in t:
            required_type = "Laboratory"
        else:
            required_type = "Lecture"

        for r_idx, room in enumerate(rooms):
            room_type = getattr(room, "type", None)
            if room_type is None:
                continue
            if room_type.lower() != required_type.lower():
                model.Add(p_task_room[t][r_idx] == 0)

        # allow TBA if no valid room is found
        if any(room_type.lower() == required_type.lower() for room_type in [getattr(r, "type", "").lower() for r in rooms]):
            model.Add(task_room[t] != TBA_ROOM_IDX)

    # No-overlap per instructor and per room (unchanged, but uses tasks list which now includes splits)
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

    # Instructor load constraints (minute-based) for normal and overload
    instr_total_normal_minutes = {}
    instr_total_overload_minutes = {}
    instr_total_minutes = {}

    for iidx, instr in instructors_by_index.items():
        normal_limit_min = instr_caps[iidx]["normal_limit_min"]
        overload_limit_min = instr_caps[iidx]["overload_limit_min"]
        employment = instr_caps[iidx]["employment"]

        normal_terms = []
        overload_terms = []
        total_terms = []

        for t in tasks:
            dur = task_duration_min[t]
            total_terms.append(p_task_instr[t][iidx] * dur)
            # create indicator that (p_task_instr[t][iidx] AND is_normal[t])
            c_norm = model.NewBoolVar(f"c_norm_{t}_i{iidx}")
            model.AddBoolAnd([p_task_instr[t][iidx], is_normal[t]]).OnlyEnforceIf(c_norm)
            model.AddBoolOr([p_task_instr[t][iidx].Not(), is_normal[t].Not()]).OnlyEnforceIf(c_norm.Not())
            normal_terms.append(c_norm * dur)

            c_over = model.NewBoolVar(f"c_over_{t}_i{iidx}")
            model.AddBoolAnd([p_task_instr[t][iidx], is_overload[t]]).OnlyEnforceIf(c_over)
            model.AddBoolOr([p_task_instr[t][iidx].Not(), is_overload[t].Not()]).OnlyEnforceIf(c_over.Not())
            overload_terms.append(c_over * dur)

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

        total_overload_min_var = model.NewIntVar(0, 20000, f"total_overload_min_i{iidx}")
        if overload_terms:
            model.Add(total_overload_min_var == sum(overload_terms))
        else:
            model.Add(total_overload_min_var == 0)

        # Hard caps enforcement for permanent instructors
        if employment == "permanent":
            model.Add(total_normal_min <= normal_limit_min)
            model.Add(total_overload_min_var <= overload_limit_min)
        # part-time and overload types have no hard caps (but overload type already restricted to overload windows)

        instr_total_normal_minutes[iidx] = total_normal_min
        instr_total_overload_minutes[iidx] = total_overload_min_var
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
    # Soft overload penalty per instructor (still present but hard caps for permanent enforced above)
    # -------------------------
    overload_excess_vars = []
    for iidx, instr in instructors_by_index.items():
        # for soft penalty, compare assigned overload minutes against soft cap = instr_caps overload_limit_min
        cap_min = instr_caps[iidx]["overload_limit_min"]
        excess = model.NewIntVar(0, 20000, f"overload_excess_i{iidx}")
        model.Add(excess >= instr_total_overload_minutes[iidx] - cap_min)
        overload_excess_vars.append(excess)

    # -------------------------
    # Fairness: penalize deviation from average overload (kept as soft term)
    # -------------------------
    instr_count = len(instructors)
    total_overload_minutes_sum = model.NewIntVar(0, 20000, "total_overload_minutes_sum")
    model.Add(total_overload_minutes_sum == sum(instr_total_overload_minutes.values()))

    avg_overload = model.NewIntVar(0, 20000, "avg_overload")
    model.AddDivisionEquality(avg_overload, total_overload_minutes_sum, max(1, instr_count))

    deviation_vars = []
    for iidx in instr_total_overload_minutes:
        diff = model.NewIntVar(-20000, 20000, f"diff_i{iidx}")
        model.Add(diff == instr_total_overload_minutes[iidx] - avg_overload)
        dev = model.NewIntVar(0, 20000, f"deviation_i{iidx}")
        model.AddAbsEquality(dev, diff)
        deviation_vars.append(dev)

    # -------------------------
    # Final objective: maximize match scores + room priority, minus overload penalties and fairness penalties
    # -------------------------
    objective_terms = []
    if match_score_terms:
        objective_terms.append(sum(match_score_terms))
    if room_priority_terms:
        objective_terms.append(sum(room_priority_terms))

    if overload_excess_vars:
        objective_terms.append(- SOFT_OVERLOAD_PENALTY * sum(overload_excess_vars))
    if deviation_vars:
        objective_terms.append(- FAIRNESS_PENALTY * sum(deviation_vars))

    model.Maximize(sum(objective_terms))

    # ---------- Solve ----------
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 8
    solver.parameters.max_time_in_seconds = max(1, time_limit_seconds)
    solver.parameters.random_seed = 42
    solver.parameters.symmetry_level = 0
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

        kind = "lecture" if "__lec" in t else "lab"
        is_overtime = False
        # determine if this scheduled meeting is in overload window for that day
        # classify by day + start
        typ = task_start_day_allowed.get(t, {}).get((assigned_day, assigned_start), None)
        if typ == "overload":
            is_overtime = True

        print(f"[Assign] Task {t} ({kind}) -> Section {sec_id} | Instr {instr_obj.instructorId} | Day {assigned_day} ({weekday[assigned_day]}) | Start {start_time} | Dur {dur} | Room {getattr(room_obj, 'roomCode', None)} | Overtime={is_overtime}")

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
        normal_limit_min, overload_limit_min, _, _ = resolve_instructor_limits(instr)
        assigned_normal_min = solver.Value(instr_total_normal_minutes[iidx])
        assigned_overload_min = solver.Value(instr_total_overload_minutes[iidx])
        total_min = solver.Value(instr_total_minutes[iidx])
        # overload excess var value
        try:
            excess_val = solver.Value(model.GetVarFromProtoName(f"overload_excess_i{iidx}"))
        except Exception:
            excess_val = None
        print(f" - {instr.instructorId}: normal_limit={normal_limit_min}min ({normal_limit_min/60:.2f}h), "
              f"overload_limit={overload_limit_min}min ({overload_limit_min/60:.2f}h), assigned_normal={assigned_normal_min}min ({assigned_normal_min/60:.2f}h), "
              f"assigned_overload={assigned_overload_min}min ({assigned_overload_min/60:.2f}h), total_minutes={total_min}min ({total_min/60:.2f}h), overload_excess={excess_val}")

    # Bulk create schedules
    with transaction.atomic():
        Schedule.objects.bulk_create(schedules_to_create)
        print(f"[Solver] Saved {len(schedules_to_create)} schedules for semester {semester} (status='active').")

    return schedules_to_create


def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=3600, interval_minutes=30)


if __name__ == "__main__":
    print("Running scheduler...")
    schedules = generateSchedule()
    if schedules:
        print(f"Generated {len(schedules)} schedules.")
    else:
        print("No schedules generated.")
