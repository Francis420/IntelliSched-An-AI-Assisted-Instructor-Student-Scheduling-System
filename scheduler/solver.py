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
TARGET_SEMESTER_ID = 16  
DEFAULT_NORMAL_HOURS = 18  

GLOBAL_DAY_START, GLOBAL_DAY_END = 8 * 60, 20 * 60  
LUNCH_START, LUNCH_END = 12 * 60, 13 * 60  

WEIGHT_MATCH = 1000
WEIGHT_ROOM_PRIORITY = 200000

SOFT_OVERLOAD_PENALTY = 50
FAIRNESS_PENALTY = 2000

MAX_REASONABLE_MIN = 20000 * 60


def clamp_minutes(x):
    try:
        if x is None:
            return None
        xv = int(x)
        if xv > MAX_REASONABLE_MIN:
            return MAX_REASONABLE_MIN
        return xv
    except Exception:
        return x


# ----------------- Helpers -----------------
def minutes_to_time(mins):
    hr = mins // 60
    m = mins % 60
    return datetime.time(hr, m)


def window_name_for_start(start_min, dur_min):
    end = start_min + dur_min

    if start_min < 480 or end > 1200:
        return None

    if not (end <= 720 or start_min >= 780):
        return None

    if end <= 17 * 60:  # 5 PM
        return "normal"
    elif start_min >= 17 * 60:
        return "overload"

    return None



def make_task_id(section_id, kind, part=None):
    if part:
        return f"{section_id}__{kind}_p{part}"
    return f"{section_id}__{kind}"


def is_instructor_available(instructor, day_name, start_time, end_time):
    employment = (getattr(instructor, "employmentType", "") or "").strip().lower()
    day_name = (day_name or "").upper()

    weekday = day_name in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
    weekend = day_name in ["SATURDAY", "SUNDAY"]

    if not (end_time <= 720 or start_time >= 780):
        return False

    if start_time < 480 or end_time > 1200:
        return False

    if employment in ["on-leave", "on-leave/retired", "retired"]:
        return False

    if employment == "permanent":
        if weekday and end_time <= 17 * 60:
            return True
        if (weekday and start_time >= 17 * 60) or (weekend and end_time <= 20 * 60):
            return True
        return False

    elif employment == "part-time":
        if weekday and end_time <= 20 * 60:
            return True
        if weekend and end_time <= 20 * 60:
            return True
        return False

    elif employment == "overload":
        # Weekdays 5–8 PM
        if weekday and (17 * 60 <= start_time < 20 * 60):
            return True
        # Sat/Sun 8–12 + 1–8
        if weekend and ((480 <= start_time < 720) or (780 <= start_time < 1200)):
            return True
        return False

    return False



def resolve_instructor_limits(instr: Instructor):
    employment = getattr(instr, "employmentType", "").lower() if getattr(instr, "employmentType", None) else "permanent"
    designation = getattr(instr, "designation", None)
    if isinstance(designation, str) and designation.strip().upper() == "N/A":
        designation = None
    has_designation = designation is not None

    normal_h = None
    try:
        if designation and getattr(designation, "instructionHours", None) is not None:
            normal_h = designation.instructionHours
        elif getattr(instr, "rank", None) and getattr(instr.rank, "instructionHours", None) is not None:
            normal_h = instr.rank.instructionHours
        elif getattr(instr, "normalLoad", None) is not None:
            normal_h = instr.normalLoad
    except Exception:
        normal_h = None

    normal_h = int(normal_h) if normal_h else int(DEFAULT_NORMAL_HOURS)

    if employment == "permanent":
        overload_h = 9 if has_designation else 12
        return normal_h * 60, overload_h * 60, employment, has_designation
    elif employment == "part-time":
        return 10_000 * 60, 10_000 * 60, employment, has_designation
    elif employment.lower().startswith("overload"):
        return 10_000 * 60, 10_000 * 60, "overload", has_designation
    else:
        overload_h = 9 if has_designation else 12
        return normal_h * 60, overload_h * 60, "permanent", has_designation


def build_tasks_from_sections(sections, interval_minutes=30):
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
                half1 = lec_min // 2
                half2 = lec_min - half1
                def align(x):
                    rem = x % interval_minutes
                    if rem == 0:
                        return x
                    return x - rem
                a1 = align(half1)
                a2 = align(half2)

                if a1 <= 0:
                    a1 = half1

                if a2 <= 0:
                    a2 = half2
                diff = lec_min - (a1 + a2)
                a2 += diff

                if a1 <= 0 or a2 <= 0:
                    a1 = half1
                    a2 = half2
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
            task_units[lt] = 0
            lab_task = lt

        if lec_tasks and lab_task:
            for lec_t in lec_tasks:
                lec_lab_pairs.append((lec_t, lab_task))

    return tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs

class StopAfterFeasibleSolution(cp_model.CpSolverSolutionCallback):
    def __init__(self):
        super().__init__()
        self.solution_found = False

    def OnSolutionCallback(self):
        print("[Solver] Feasible solution found — stopping search early.")
        self.solution_found = True
        self.StopSearch()

from collections import Counter

def debug_instructor_availability(instructors):
    """
    Prints all instructors with their employment type, rank, and designation.
    Also shows totals per employment type.
    """
    print("--------------------------------------------------")
    print("[DEBUG] Listing all instructors with type, rank, and designation...\n")

    seen = set()
    counts = Counter()

    for instr in instructors:
        # Basic fields
        name = getattr(instr, "full_name", None) or str(instr)
        employment = (getattr(instr, "employmentType", "") or "").strip().upper()

        # Optional related fields (safe handling if None)
        rank = getattr(instr.rank, "name", None) if instr.rank else "—"
        designation = getattr(instr.designation, "name", None) if instr.designation else "—"

        key = (name, employment, rank, designation)
        if key in seen:
            continue
        seen.add(key)
        counts[employment] += 1

        print(f"- {name} ({employment}) | Rank: {rank} | Designation: {designation}")

    print("\n[DEBUG] Totals by type:")
    for etype, num in counts.items():
        print(f"  {etype}: {num}")

    print(f"\n[DEBUG] Total unique instructors found: {len(seen)}")
    print("--------------------------------------------------\n")


def solve_schedule_for_semester(semester=None, time_limit_seconds=30, interval_minutes=30):
    if semester is None:
        semester = Semester.objects.get(pk=TARGET_SEMESTER_ID)
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Semester: {semester}")

    archived = Schedule.objects.filter(semester=semester, status='active').update(status='archived')
    print(f"[Solver] Archived {archived} old active schedules for semester {semester}")

    sections = list(Section.objects.filter(semester=semester).select_related("subject"))
    instructors_all = list(Instructor.objects.all())
    section_by_id = {s.sectionId: s for s in sections}
    instructors = [i for i in instructors_all if (getattr(i, "employmentType", "") or "").lower() != "on-leave/retired"]
    rooms = list(Room.objects.filter(isActive=True))
    tba_room = Room()
    setattr(tba_room, "name", "TBA")
    setattr(tba_room, "type", "Any")
    rooms.append(tba_room)
    tba_idx = len(rooms) - 1
    gened_qs = list(GenEdSchedule.objects.filter(semester=semester))

    if not sections:
        raise ValueError("No sections found for semester — nothing to do.")
    if not instructors:
        raise ValueError("No instructors available for scheduling (all filtered out or none exist).")


    tasks, task_to_section, task_duration_min, task_units, lec_lab_pairs = build_tasks_from_sections(sections, interval_minutes=interval_minutes)
    if not tasks:
        raise ValueError("No tasks (lecture/lab) built — nothing to schedule.")

    start_of_day = GLOBAL_DAY_START
    end_of_day = GLOBAL_DAY_END
    time_blocks = [t for t in range(start_of_day, end_of_day + 1, interval_minutes) if not (LUNCH_START <= t < LUNCH_END)]
    if not time_blocks:
        raise ValueError("No time blocks generated. Check interval_minutes.")

    valid_starts = {}
    for t in tasks:
        dur = task_duration_min[t]
        vs = [s for s in time_blocks if (s + dur) <= end_of_day and window_name_for_start(s, dur) is not None]
        if not vs:
            print(f"[WARN] Task {t} (section {task_to_section[t]}) has no valid start times for duration {dur}min.")
        valid_starts[t] = vs

    gened_blocks = []
    for g in gened_qs:
        sch = g.schedule
        day_idx = int(sch.dayOfWeek) if isinstance(sch.dayOfWeek, int) else {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(sch.dayOfWeek, 0)
        s = sch.startTime.hour * 60 + sch.startTime.minute
        e = sch.endTime.hour * 60 + sch.endTime.minute
        gened_blocks.append((day_idx, s, e))

    match_qs = InstructorSubjectMatch.objects.select_related("instructor", "subject").all()
    matches_by_subject = defaultdict(list)
    for m in match_qs:
        subj_id = m.subject.subjectId
        score = getattr(m, "confidenceScore", None)
        if score is None:
            score = 1.0 if getattr(m, "isRecommended", False) else 0.0
        matches_by_subject[subj_id].append((m.instructor.instructorId, float(score)))

    instructors_by_index = {idx: instr for idx, instr in enumerate(instructors)}
    instr_index_by_id = {instr.instructorId: idx for idx, instr in enumerate(instructors)}
    room_index_by_id = {r.roomId: idx for idx, r in enumerate(rooms)}
    num_rooms = len(rooms)
    TBA_ROOM_IDX = tba_idx

    instr_caps = {}
    for iidx, instr in instructors_by_index.items():
        normal_min, overload_min, employment, has_designation = resolve_instructor_limits(instr)
        normal_min = clamp_minutes(normal_min)
        overload_min = clamp_minutes(overload_min)
        instr_caps[iidx] = {
            "normal_limit_min": normal_min,
            "overload_limit_min": overload_min,
            "employment": employment,
            "has_designation": has_designation
        }

        source = "default"
        if getattr(instr, "designation", None) and getattr(instr.designation, "instructionHours", None):
            source = "designation"
        elif getattr(instr, "rank", None) and getattr(instr.rank, "instructionHours", None):
            source = "rank"
        elif getattr(instr, "normalLoad", None):
            source = "manual"

        print(
            f"[Instructor] {getattr(instr, 'instructorId', '?')} | "
            f"{getattr(instr, 'lastName', '')}, {getattr(instr, 'firstName', '')} | "
            f"Employment: {employment.upper()} | "
            f"Has Designation: {has_designation} | "
            f"Normal Load Source: {source} | "
            f"Normal Limit: {normal_min} mins ({normal_min/60:.2f} hrs) | "
            f"Overload Limit: {overload_min} mins ({overload_min/60:.2f} hrs)"
        )

    tasks_no_start = [t for t, vs in valid_starts.items() if not vs]
    if tasks_no_start:
        raise ValueError(f"Tasks with NO valid starts ({len(tasks_no_start)}): {tasks_no_start[:10]}")

    room_types = defaultdict(list)
    for idx, r in enumerate(rooms):
        room_types[getattr(r, "type", "Unknown")].append(idx)

    tasks_no_room = set()
    for t in tasks:
        required = "Laboratory" if t.endswith("__lab") else "Lecture"
        if not any(getattr(r, "type", "").lower() == required.lower() for r in rooms if getattr(r, "type", None)):
            tasks_no_room.add((t, required))


    total_required_minutes = sum(task_duration_min[t] for t in tasks)
    total_perm_capacity = sum(instr_caps[iidx]["normal_limit_min"] + instr_caps[iidx]["overload_limit_min"]
                            for iidx in instr_caps if instr_caps[iidx]["employment"] == "permanent")
    other_capacity = sum(instr_caps[iidx]["normal_limit_min"] + instr_caps[iidx]["overload_limit_min"]
                        for iidx in instr_caps if instr_caps[iidx]["employment"] != "permanent")
    print(f"[DIAG] total_required_minutes={total_required_minutes} (hrs={total_required_minutes/60:.1f})")
    print(f"[DIAG] permanent_capacity (normal+overload)={total_perm_capacity} (hrs={total_perm_capacity/60:.1f})")
    print(f"[DIAG] other_capacity sum={other_capacity} (hrs={other_capacity/60:.1f})")
    print(f"[DIAG] rooms: total={len(rooms)}, by_type={{{', '.join(f'{k}:{len(v)}' for k,v in room_types.items())}}}")

    tasks_no_start = [t for t, vs in valid_starts.items() if not vs]
    if tasks_no_start:
        print(f"[ERROR] Found {len(tasks_no_start)} tasks with NO valid start times (duration too long or no time slot). Example: {tasks_no_start[:10]}")
        print("Tip: increase `interval_minutes`, allow splitting, or widen GLOBAL_DAY_START/END.")
        return None

    tasks_no_room_list = [t for (t, req) in tasks_no_room]
    if tasks_no_room_list:
        print(f"[WARN] Found {len(tasks_no_room_list)} tasks with NO matching room types. Forcing TBA assignment for them.")
    
    print("\n[DEBUG] Rooms Loaded:")
    for idx, r in enumerate(rooms):
        print(f"{idx}: {getattr(r, 'roomCode', 'TBA')} - {getattr(r, 'type', 'Any')}")
    print("-" * 50)


    debug_instructor_availability(instructors)

    model = cp_model.CpModel()

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
        
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dur = task_duration_min[t]
        for d in range(7):
            for s in valid_starts.get(t, []):
                for iidx, instr in instructors_by_index.items():
                    day_name = weekday_names[d].upper()
                    start_time = s
                    end_time = s + dur

                    if not is_instructor_available(instr, day_name, start_time, end_time):
                        model.AddBoolOr([
                            p_task_instr[t][iidx].Not(),
                            day_eq[t][d].Not(),
                            start_eq[t][s].Not()
                        ])

        p_task_room[t] = {}

        required_type = "Laboratory" if t.endswith("__lab") else "Lecture"

        valid_room_indices = []
        for r_idx, room in enumerate(rooms):
            pr = model.NewBoolVar(f"p_{t}_r{r_idx}")
            p_task_room[t][r_idx] = pr

            model.Add(task_room[t] == r_idx).OnlyEnforceIf(pr)
            model.Add(task_room[t] != r_idx).OnlyEnforceIf(pr.Not())

            room_type = getattr(room, "type", None)
            room_name = getattr(room, "name", "")

            if room_type and room_type.lower() == required_type.lower():
                valid_room_indices.append(r_idx)

        if not valid_room_indices:
            if tba_idx in p_task_room[t]:
                model.Add(p_task_room[t][tba_idx] == 1)
                model.Add(task_room[t] == tba_idx)
            else:
                pr = model.NewBoolVar(f"p_{t}_r{tba_idx}")
                p_task_room[t][tba_idx] = pr
                model.Add(pr == 1)
                model.Add(task_room[t] == tba_idx)
            for ridx, pr in p_task_room[t].items():
                if ridx != tba_idx:
                    model.Add(pr == 0)
            tasks_no_room.add(t)

        else:

            if tba_idx in p_task_room[t]:
                tba_var = p_task_room[t][tba_idx]
                model.Add(sum(p_task_room[t][r_idx] for r_idx in valid_room_indices) + p_task_room[t][tba_idx] == 1)
            else:
                model.Add(sum(p_task_room[t][r_idx] for r_idx in valid_room_indices) == 1)


    for lec_task, lab_task in lec_lab_pairs:
        model.Add(task_instr[lec_task] == task_instr[lab_task])
        model.Add(task_day[lec_task] != task_day[lab_task])

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


    is_normal = {}
    is_overload = {}


  
    task_start_day_allowed = {}
    for t in tasks:
        dur = task_duration_min[t]
        mapping = {}
        for d in range(7):
            for s in valid_starts.get(t, []):
                base_class = window_name_for_start(s, dur)
                if base_class is None:
                    continue
                if d <= 4:
                    if base_class == "normal":
                        mapping[(d, s)] = "normal"
                    elif base_class == "overload":
                        mapping[(d, s)] = "overload"
                else:
                    if base_class == "normal":
                        mapping[(d, s)] = "overload"
                    elif base_class == "overload":
                        mapping[(d, s)] = "overload"
        task_start_day_allowed[t] = mapping

    for t in tasks:
        bool_norm = model.NewBoolVar(f"is_normal_{t}")
        bool_over = model.NewBoolVar(f"is_over_{t}")

        norm_clauses = []
        over_clauses = []

        for (d, s), typ in task_start_day_allowed.get(t, {}).items():
 
            conj = model.NewBoolVar(f"pair_{t}_d{d}_s{s}")

            model.AddBoolAnd([day_eq[t][d], start_eq[t][s]]).OnlyEnforceIf(conj)
            model.AddBoolOr([day_eq[t][d].Not(), start_eq[t][s].Not()]).OnlyEnforceIf(conj.Not())
            if typ == "normal":
                norm_clauses.append(conj)
            elif typ == "overload":
                over_clauses.append(conj)

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


    for t in tasks:
        for iidx, instr in instructors_by_index.items():
            emp = instr_caps[iidx]["employment"]
            if emp == "overload":
                model.AddImplication(p_task_instr[t][iidx], is_overload[t])
            elif emp == "permanent":
                pass
            elif emp == "part-time":
                pass
            else:
                pass

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


    ROOM_TYPE_MISMATCH_PENALTY = 300
    has_lab_room = any(getattr(r, "type", "").lower() == "laboratory" for r in rooms)
    room_type_penalty_terms = []
    for t in tasks:
        sec_id = task_to_section[t]
        sec_obj = section_by_id.get(sec_id)
        subj = sec_obj.subject if sec_obj else None
        requires_lab = subj.hasLab if subj else False

        for r_idx, room in enumerate(rooms):
            room_type = getattr(room, "type", "").lower()
            is_tba = (r_idx == tba_idx)

            if is_tba:
                continue

            if has_lab_room and requires_lab and room_type not in ["laboratory", "lab"]:
                room_type_penalty_terms.append(
                    ROOM_TYPE_MISMATCH_PENALTY * p_task_room[t][r_idx]
                )

            elif not requires_lab and room_type not in ["lecture"]:
                room_type_penalty_terms.append(
                    ROOM_TYPE_MISMATCH_PENALTY * p_task_room[t][r_idx]
                )

    objective_terms = []

    if room_type_penalty_terms:
        objective_terms.append(-sum(room_type_penalty_terms))


    task_end = {}
    task_interval_for_instr = {}
    task_interval_for_room = {}

    for t in tasks:
        dur = int(task_duration_min[t])
        vs = valid_starts.get(t, [])
        if vs:
            min_s = min(vs)
            max_s = max(vs)
        else:
            min_s = GLOBAL_DAY_START
            max_s = GLOBAL_DAY_END
        task_end[t] = model.NewIntVar(min_s + dur, max_s + dur, f"end_{t}")
        model.Add(task_end[t] == task_start[t] + dur)

        task_interval_for_instr[t] = {}
        task_interval_for_room[t] = {}

        for iidx in instructors_by_index:
            presence = p_task_instr[t].get(iidx)
            if presence is None:
                continue
            iv = model.NewOptionalIntervalVar(task_start[t], dur, task_end[t], presence, f"interval_{t}_i{iidx}")
            task_interval_for_instr[t][iidx] = iv

        for r_idx in range(num_rooms):
            if r_idx == tba_idx:
                continue

            presence = p_task_room[t].get(r_idx)
            if presence is None:
                continue

            ivr = model.NewOptionalIntervalVar(
                task_start[t],
                dur,
                task_end[t],
                presence,
                f"interval_{t}_r{r_idx}"
            )
            task_interval_for_room[t][r_idx] = ivr


    for iidx in instructors_by_index:
        intervals = [task_interval_for_instr[t][iidx] for t in tasks if iidx in task_interval_for_instr[t]]
        if intervals:
            model.AddNoOverlap(intervals)


    for r_idx, room in enumerate(rooms):
        if r_idx == tba_idx:
            continue

        room_intervals = []
        for t in tasks:
            if r_idx in task_interval_for_room.get(t, {}):  
                room_intervals.append(task_interval_for_room[t][r_idx])

        if room_intervals:
            model.AddNoOverlap(room_intervals)


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
            c_norm = model.NewBoolVar(f"c_norm_{t}_i{iidx}")
            model.AddBoolAnd([p_task_instr[t][iidx], is_normal[t]]).OnlyEnforceIf(c_norm)
            model.AddBoolOr([p_task_instr[t][iidx].Not(), is_normal[t].Not()]).OnlyEnforceIf(c_norm.Not())
            normal_terms.append(c_norm * dur)

            c_over = model.NewBoolVar(f"c_over_{t}_i{iidx}")
            model.AddBoolAnd([p_task_instr[t][iidx], is_overload[t]]).OnlyEnforceIf(c_over)
            model.AddBoolOr([p_task_instr[t][iidx].Not(), is_overload[t].Not()]).OnlyEnforceIf(c_over.Not())
            overload_terms.append(c_over * dur)

        total_normal_min = model.NewIntVar(0, MAX_REASONABLE_MIN, f"total_normal_min_i{iidx}")
        total_min = model.NewIntVar(0, MAX_REASONABLE_MIN, f"total_min_i{iidx}")

        if normal_terms:
            model.Add(total_normal_min == sum(normal_terms))
        else:
            model.Add(total_normal_min == 0)
        if total_terms:
            model.Add(total_min == sum(total_terms))
        else:
            model.Add(total_min == 0)

        total_overload_min_var = model.NewIntVar(0, MAX_REASONABLE_MIN, f"total_overload_min_i{iidx}")
        if overload_terms:
            model.Add(total_overload_min_var == sum(overload_terms))
        else:
            model.Add(total_overload_min_var == 0)

        if employment == "permanent":
            model.Add(total_normal_min <= normal_limit_min)
            model.Add(total_overload_min_var <= overload_limit_min)

            model.Add(total_min <= normal_limit_min + overload_limit_min)

        instr_total_normal_minutes[iidx] = total_normal_min
        instr_total_overload_minutes[iidx] = total_overload_min_var
        instr_total_minutes[iidx] = total_min

    perm_normal_gap_terms = []
    for iidx, instr in instructors_by_index.items():
        if instr_caps[iidx]["employment"] == "permanent":
            limit = instr_caps[iidx]["normal_limit_min"]
            gap = model.NewIntVar(0, limit, f"perm_gap_i{iidx}")
            model.Add(gap == limit - instr_total_normal_minutes[iidx])
            perm_normal_gap_terms.append(gap)


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


    overload_excess_vars = []
    for iidx, instr in instructors_by_index.items():
        cap_min = instr_caps[iidx]["overload_limit_min"]
        excess = model.NewIntVar(0, MAX_REASONABLE_MIN, f"overload_excess_i{iidx}")
        model.Add(excess >= instr_total_overload_minutes[iidx] - cap_min)
        overload_excess_vars.append(excess)


    instr_count = len(instructors)
    total_overload_minutes_sum = model.NewIntVar(0, MAX_REASONABLE_MIN, "total_overload_minutes_sum")
    model.Add(total_overload_minutes_sum == sum(instr_total_overload_minutes.values()))

    avg_overload = model.NewIntVar(0, MAX_REASONABLE_MIN, "avg_overload")
    model.AddDivisionEquality(avg_overload, total_overload_minutes_sum, max(1, instr_count))

    deviation_vars = []
    for iidx in instr_total_overload_minutes:
        diff = model.NewIntVar(-MAX_REASONABLE_MIN, MAX_REASONABLE_MIN, f"diff_i{iidx}")
        model.Add(diff == instr_total_overload_minutes[iidx] - avg_overload)
        dev = model.NewIntVar(0, MAX_REASONABLE_MIN, f"deviation_i{iidx}")
        model.AddAbsEquality(dev, diff)
        deviation_vars.append(dev)

    # Prefer normal time slots and days    
    NORMAL_SLOT_REWARD = 10000   # reward per normal minute
    # Penalize overload time slots and days
    OVERLOAD_SLOT_PENALTY = 10000 # penalty per overload minute

    # Severe penalty for each particular day's usage
    DAY_COSTS = {
        0: 0,   # Mon
        1: 0,   # Tue
        2: 0,   # Wed
        3: 0,   # Thu
        4: 0,   # Fri (adjust later if needed)
        5: 300000, # Sat
        6: 300000  # Sun
    }

    # ---- Time + day preference objective terms ----
    for t in tasks:
        dur = task_duration_min[t]

        objective_terms.append(NORMAL_SLOT_REWARD * dur * is_normal[t])
        objective_terms.append(-OVERLOAD_SLOT_PENALTY * dur * is_overload[t])

        for d in range(7):
            objective_terms.append(-DAY_COSTS[d] * day_eq[t][d])

    # ==================================================
    # Strong load priority weights (lexicographic style)
    # ==================================================
    W_PERM_NORMAL_FILL     = 1000000
    W_PERM_NORMAL_GAP      = 900000
    W_AVOID_PT_BEFORE_PERM = 500000
    W_BALANCE_OVERLOAD     = 5000
    # ==================================================

    # Reward permanent normal minutes, discourage PT normal until perms full
    for iidx, instr in instructors_by_index.items():
        employment = instr_caps[iidx]["employment"]
        normal = instr_total_normal_minutes[iidx]

        if employment == "permanent":
            objective_terms.append(W_PERM_NORMAL_FILL * normal)
        else:
            objective_terms.append(-W_AVOID_PT_BEFORE_PERM * normal)

    # Penalize permanent normal load not filled
    if perm_normal_gap_terms:
        objective_terms.append(-W_PERM_NORMAL_GAP * sum(perm_normal_gap_terms))


    if match_score_terms:
        objective_terms.append(sum(match_score_terms))
    if room_priority_terms:
        objective_terms.append(sum(room_priority_terms))

    if overload_excess_vars:
        objective_terms.append(- SOFT_OVERLOAD_PENALTY * sum(overload_excess_vars))
    if deviation_vars:
        objective_terms.append(- W_BALANCE_OVERLOAD * sum(deviation_vars))

    YEAR_TBA_PENALTY = {1: 1000, 2: 500, 3: 200, 4: 50}

    tba_penalty_terms = []
    for t in tasks:
        sec_id = task_to_section[t]
        sec_obj = section_by_id.get(sec_id)
        year = getattr(sec_obj.subject, "yearLevel", None) if sec_obj and getattr(sec_obj, "subject", None) else None
        if year is None:
            year = 4
        pen = YEAR_TBA_PENALTY.get(year, 50)
 
        if tba_idx in p_task_room[t]:
            tba_penalty_terms.append(p_task_room[t][tba_idx] * pen)

    if tba_penalty_terms:
        objective_terms.append(- sum(tba_penalty_terms))

    model.Maximize(sum(objective_terms))



    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 8
    solver.parameters.max_time_in_seconds = 9000
    solver.parameters.random_seed = 42
    solver.parameters.log_search_progress = True
    solver.parameters.cp_model_presolve = True
    solver.parameters.cp_model_probing_level = 0

    print(f"[Solver] Solving {len(tasks)} tasks with {len(instructors)} instructors and {num_rooms} rooms...")

    cb = StopAfterFeasibleSolution() #comment this out to disable early stopping
    status = solver.Solve(model, cb) #this too

    # status = solver.Solve(model) # to run without early stopping use 'solver.parameters.max_time_in_seconds' to control time


    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("[Solver] No feasible solution found.")
        return None

 

    schedules_to_create = []
    section_by_id = {s.sectionId: s for s in sections}
    room_by_index = {idx: r for idx, r in enumerate(rooms)}
    weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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

        typ = task_start_day_allowed.get(t, {}).get((assigned_day, assigned_start), None)
        if typ == "overload":
            is_overtime = True

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


    print("\n[Solver] Per-instructor load summary (limits and assignments):")
    for iidx, instr in instructors_by_index.items():
        normal_limit_min, overload_limit_min, _, _ = resolve_instructor_limits(instr)
        assigned_normal_min = solver.Value(instr_total_normal_minutes[iidx])
        assigned_overload_min = solver.Value(instr_total_overload_minutes[iidx])
        total_min = solver.Value(instr_total_minutes[iidx])
 
        try:
            excess_val = solver.Value(model.GetVarFromProtoName(f"overload_excess_i{iidx}"))
        except Exception:
            excess_val = None


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
