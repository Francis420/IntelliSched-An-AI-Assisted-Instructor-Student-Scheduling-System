# scheduler/solver.py  — rewritten: separate lecture + lab interval variables per Section
import math
from collections import defaultdict
from itertools import combinations

from ortools.sat.python import cp_model
from django.db import transaction
from datetime import datetime, timedelta

from scheduling.models import Section, Semester, Schedule, Room, GenEdSchedule
from core.models import Instructor
from scheduler.data_extractors import get_solver_data

# -------------------- Configuration --------------------
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
INTERVAL_MINUTES = 30
WEEK_MINUTES = 7 * 24 * 60

# Tuning weights (adjust to taste)
MATCH_WEIGHT_SCALE = 100       # match score * this
TBA_PENALTY = 50               # penalty per task assigned to TBA
REAL_ROOM_REWARD = 10          # small reward for non-TBA room
OVERLOAD_PENALTY_PER_MIN = 5   # penalty per minute of overload (scaled)

# -------------------- Timeslot metadata (same mapping as earlier generator) --------------------
def generate_timeslot_meta():
    timeslots = []
    slot_meta = []  # (label, day_idx, minute_of_day, minute_of_week)
    slot_index = 0

    MORNING_RANGE = (8, 12)
    AFTERNOON_RANGE = (13, 17)
    OVERLOAD_RANGE_WEEKDAYS = (17.5, 20)
    OVERLOAD_RANGE_WEEKENDS = [(8, 12), (13, 20)]

    for day_idx, day in enumerate(DAYS):
        if day_idx <= 4:  # Mon-Fri
            for hour in range(MORNING_RANGE[0], MORNING_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    slot_index += 1
            for hour in range(AFTERNOON_RANGE[0], AFTERNOON_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    slot_index += 1
            hour = int(OVERLOAD_RANGE_WEEKDAYS[0])
            minute = 30
            while hour + minute / 60 < OVERLOAD_RANGE_WEEKDAYS[1] - 1e-9:
                minute_of_day = hour * 60 + minute
                label = f"{day} {hour:02d}:{minute:02d}"
                minute_of_week = day_idx * 1440 + minute_of_day
                slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                minute += INTERVAL_MINUTES
                if minute == 60:
                    minute = 0
                    hour += 1
                slot_index += 1
        else:  # Sat-Sun
            for start_h, end_h in OVERLOAD_RANGE_WEEKENDS:
                hour = int(start_h)
                minute = 0
                while hour + minute / 60 < end_h - 1e-9:
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    minute += INTERVAL_MINUTES
                    if minute == 60:
                        minute = 0
                        hour += 1
                    slot_index += 1

    timeslots = [m[0] for m in slot_meta]
    return timeslots, slot_meta

TIMESLOTS, SLOT_META = generate_timeslot_meta()
NUM_SLOTS = len(TIMESLOTS)
SLOT_TO_DAY = {i: SLOT_META[i][1] for i in range(NUM_SLOTS)}
SLOT_TO_GLOBAL_MIN = {i: SLOT_META[i][3] for i in range(NUM_SLOTS)}

# ----------------- Main solver -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=600):
    # Resolve semester
    if semester is None:
        semester = Semester.objects.order_by('-createdAt').first()
        if not semester:
            print("[Solver] No semesters found.")
            return []
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Semester: {semester}")
    Schedule.objects.filter(semester=semester, status='active').update(status='archived')

    data = get_solver_data(semester)
    sections = list(data["sections"])
    rooms = list(data["rooms"])
    instructors = list(data["instructors"])

    num_rooms = len(rooms)
    num_instructors = len(instructors)
    TBA_ROOM_IDX = data.get("TBA_ROOM_IDX", num_rooms - 1)

    # Build CP model
    model = cp_model.CpModel()

    # Tasks: we will create one or two tasks per Section.
    # Each task will have ids like f"{sec}_LECT" and f"{sec}_LAB"
    tasks = []  # list of dicts: {id, sectionId, kind('lecture'/'lab'), dur}
    for s in sections:
        sec_hours = data["section_hours"].get(s, {"lecture_min": 0, "lab_min": 0})
        lecture_d = int(sec_hours.get("lecture_min", 0) or 0)
        lab_d = int(sec_hours.get("lab_min", 0) or 0)
        # If Section has lab flag but durations missing, try fallback to subject defaults done in data_extractors
        # Create lecture task if lecture_d > 0
        if lecture_d > 0:
            tasks.append({"task_id": f"{s}_LECT", "section": s, "kind": "lecture", "dur": lecture_d})
        # Create lab task if lab_d > 0
        if lab_d > 0:
            tasks.append({"task_id": f"{s}_LAB", "section": s, "kind": "lab", "dur": lab_d})

    # Decision vars per task
    task_start = {}
    task_end = {}
    task_slot = {}
    task_day = {}
    task_interval = {}

    # For mapping assignments to instructors/rooms
    task_instr_var = {}
    task_room_var = {}

    # For optional intervals per (task,instructor) and per (task,room)
    assigned_instr = {}   # (task_id, i_idx) -> BoolVar
    instr_intervals = defaultdict(list)  # i_idx -> list of optional intervals
    assigned_room = {}    # (task_id, r_idx) -> BoolVar
    room_intervals = defaultdict(list)   # r_idx -> list of optional intervals (exclude TBA)

    # Build allowed (slot, start) and (slot, day) pairs for AddAllowedAssignments
    allowed_slot_start_pairs = [(i, SLOT_TO_GLOBAL_MIN[i]) for i in range(NUM_SLOTS)]
    allowed_slot_day_pairs = [(i, SLOT_TO_DAY[i]) for i in range(NUM_SLOTS)]

    # ---------------------------------------------------------
    # BUILD ALLOWED START SLOTS PER TASK BASED ON DURATION + RULES
    # ---------------------------------------------------------

    def slot_allowed_for_duration(slot_idx, duration_min):
        """
        Returns True if starting at this slot with this duration is legal.
        Must:
        - avoid lunch break 12:00–13:00
        - end <= 20:00
        - timeslot must respect actual allowed windows of the day
        """
        day = SLOT_META[slot_idx][1]
        minute_of_day = SLOT_META[slot_idx][2]

        start = minute_of_day
        end = minute_of_day + duration_min

        # Hard cutoff: cannot end after 20:00
        if end > 20*60:
            return False

        # Reject if crossing lunch break.
        # If ANY overlap with 12:00–13:00 → invalid
        if not (end <= 12*60 or start >= 13*60):
            return False

        # Check allowed windows for each day
        if day <= 4:
            # Monday–Friday
            # Allowed:
            #   8–12, 13–17 (normal)
            #   17–20 (overload)
            # = 8:00–12:00 AND 13:00–20:00
            if start < 8*60:
                return False
            if start >= 12*60 and start < 13*60:  # lunch handled above but still block
                return False
            if start >= 20*60:
                return False
            # If it passed here → okay.
        else:
            # Saturday/Sunday
            # Allowed 8–12, 13–20
            if start < 8*60:
                return False
            if start >= 12*60 and start < 13*60:
                return False
            if start >= 20*60:
                return False

        return True


    # Precompute allowed slots for each duration type
    allowed_slots_for_duration = {}

    def get_allowed_slots(dur):
        if dur not in allowed_slots_for_duration:
            lst = []
            for i in range(NUM_SLOTS):
                if slot_allowed_for_duration(i, dur):
                    lst.append(i)
            allowed_slots_for_duration[dur] = lst
        return allowed_slots_for_duration[dur]


    # (put this dictionary OUTSIDE the loop — once only)
    latest_end_by_day = {
        0: 20*60,  # Monday 8:00 PM
        1: 20*60,  # Tuesday
        2: 20*60,  # Wednesday
        3: 20*60,  # Thursday
        4: 20*60,  # Friday
        5: 20*60,  # Saturday
        6: 20*60,  # Sunday
    }


    for t in tasks:
        tid = t["task_id"]
        dur = t["dur"]
        # start and end in global minute-of-week
        allowed_slots = get_allowed_slots(dur)

        # Slot variable restricted only to allowed start slots
        task_slot[tid] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(allowed_slots),
            f"slot_{tid}"
        )

        # AllowedAssignments only for start/linking
        allowed_slot_start_pairs_filtered = [
            (i, SLOT_TO_GLOBAL_MIN[i]) for i in allowed_slots
        ]

        allowed_slot_day_pairs_filtered = [
            (i, SLOT_TO_DAY[i]) for i in allowed_slots
        ]
        task_start[tid] = model.NewIntVar(0, WEEK_MINUTES - 1, f"start_{tid}")
        task_end[tid] = model.NewIntVar(0, WEEK_MINUTES, f"end_{tid}")
        task_day[tid] = model.NewIntVar(0, 6, f"day_{tid}")
        # Link slot<->start and slot<->day
        model.AddAllowedAssignments([task_slot[tid], task_start[tid]], allowed_slot_start_pairs_filtered)
        model.AddAllowedAssignments([task_slot[tid], task_day[tid]], allowed_slot_day_pairs_filtered)
        # duration relation
        model.Add(task_end[tid] == task_start[tid] + dur)

        # ---- ENFORCE TASK MUST FINISH WITHIN ALLOWED HOURS ----
        for day_idx in range(7):
            cond = model.NewBoolVar(f"{tid}_day{day_idx}")

            # If task_day == day_idx → cond = True
            model.Add(task_day[tid] == day_idx).OnlyEnforceIf(cond)
            model.Add(task_day[tid] != day_idx).OnlyEnforceIf(cond.Not())

            # Compute the allowed global end time
            allowed_end_global = day_idx*1440 + latest_end_by_day[day_idx]

            # Enforce: end time ≤ allowed daily limit
            model.Add(task_end[tid] <= allowed_end_global).OnlyEnforceIf(cond)

        # Interval (mandatory)
        task_interval[tid] = model.NewIntervalVar(task_start[tid], dur, task_end[tid], f"iv_{tid}")

        # instructor & room choice vars
        task_instr_var[tid] = model.NewIntVar(0, max(0, num_instructors - 1), f"instr_{tid}")
        task_room_var[tid] = model.NewIntVar(0, max(0, num_rooms - 1), f"room_{tid}")

        # Create assignment booleans and optional intervals per instructor
        for i_idx in range(num_instructors):
            b = model.NewBoolVar(f"assign_{tid}_instr{i_idx}")
            assigned_instr[(tid, i_idx)] = b
            # link equality
            model.Add(task_instr_var[tid] == i_idx).OnlyEnforceIf(b)
            model.Add(task_instr_var[tid] != i_idx).OnlyEnforceIf(b.Not())
            # optional interval for NoOverlap
            iv = model.NewOptionalIntervalVar(task_start[tid], dur, task_end[tid], b, f"iv_{tid}_instr{i_idx}")
            instr_intervals[i_idx].append(iv)
        # Exactly one instructor must be assigned
        model.Add(sum(assigned_instr[(tid, i_idx)] for i_idx in range(num_instructors)) == 1)

        # Rooms
        for r_idx in range(num_rooms):
            b = model.NewBoolVar(f"assign_{tid}_room{r_idx}")
            assigned_room[(tid, r_idx)] = b
            model.Add(task_room_var[tid] == r_idx).OnlyEnforceIf(b)
            model.Add(task_room_var[tid] != r_idx).OnlyEnforceIf(b.Not())
            # if not TBA create optional interval
            if r_idx != TBA_ROOM_IDX:
                iv = model.NewOptionalIntervalVar(task_start[tid], dur, task_end[tid], b, f"iv_{tid}_room{r_idx}")
                room_intervals[r_idx].append(iv)
        # Exactly one room must be assigned
        model.Add(sum(assigned_room[(tid, r_idx)] for r_idx in range(num_rooms)) == 1)

    # NoOverlap per instructor and per real room
    for i_idx, ivs in instr_intervals.items():
        if ivs:
            model.AddNoOverlap(ivs)
    for r_idx, ivs in room_intervals.items():
        if ivs:
            model.AddNoOverlap(ivs)

    # Lecture/Lab pairing constraints: same instructor, different day
    # find tasks grouped by section
    section_to_tasks = defaultdict(list)
    for t in tasks:
        section_to_tasks[t["section"]].append(t)
    for sec, tlist in section_to_tasks.items():
        # if both lecture and lab tasks exist, enforce constraints
        id_map = {t["kind"]: t["task_id"] for t in tlist}
        if "lecture" in id_map and "lab" in id_map:
            lect = id_map["lecture"]
            lab = id_map["lab"]
            model.Add(task_instr_var[lect] == task_instr_var[lab])
            model.Add(task_day[lect] != task_day[lab])

    # GenEd blocks
    for g_day, g_start_min, g_end_min in data.get("gened_blocks", []):
        g_start_global = g_day * 1440 + g_start_min
        g_end_global = g_day * 1440 + g_end_min
        for t in tasks:
            tid = t["task_id"]
            cond_day_not = model.NewBoolVar(f"{tid}_not_gened_day_{g_day}")
            model.Add(task_day[tid] != g_day).OnlyEnforceIf(cond_day_not)
            model.Add(task_day[tid] == g_day).OnlyEnforceIf(cond_day_not.Not())

            cond_before = model.NewBoolVar(f"{tid}_before_gened_{g_day}")
            model.Add(task_end[tid] <= g_start_global).OnlyEnforceIf(cond_before)
            model.Add(task_end[tid] > g_start_global).OnlyEnforceIf(cond_before.Not())

            cond_after = model.NewBoolVar(f"{tid}_after_gened_{g_day}")
            model.Add(task_start[tid] >= g_end_global).OnlyEnforceIf(cond_after)
            model.Add(task_start[tid] < g_end_global).OnlyEnforceIf(cond_after.Not())

            model.AddBoolOr([cond_day_not, cond_before, cond_after])

    # Instructor load & overload calculation
    instructor_caps = data["instructor_caps"]
    instr_total_min = {}   # keyed by instr_id (string)
    instr_overload = {}

    # Build linear sums using assignment booleans
    for i_idx, instr_id in enumerate(instructors):
        total_min = model.NewIntVar(0, WEEK_MINUTES * 10, f"total_min_instr{i_idx}")
        instr_total_min[instr_id] = total_min
        # sum of assigned durations for that instructor
        terms = []
        for t in tasks:
            tid = t["task_id"]
            dur = t["dur"]
            b = assigned_instr[(tid, i_idx)]
            if dur > 0:
                terms.append((b, dur))
        if terms:
            model.Add(total_min == sum(b * dur for (b, dur) in terms))
        else:
            model.Add(total_min == 0)

        caps = instructor_caps.get(instr_id, {})
        normal_limit = caps.get("normal_limit_min", 40 * 60)
        overload_limit = caps.get("overload_limit_min", 0)
        ov = model.NewIntVar(0, max(0, overload_limit), f"overload_instr{i_idx}")
        instr_overload[instr_id] = ov
        # ov >= total - normal_limit
        model.Add(total_min - normal_limit <= ov)
        model.Add(ov >= 0)
        model.Add(ov <= overload_limit)

    # OBJECTIVE: reward matches, penalize TBA & overload, reward real room
    objective_terms = []

    # Matches per section (apply reward to either lecture or lab task assignment)
    matches = data.get("matches", {})
    instr_index_map = data.get("instructor_index", {})
    for sec_id, match_list in matches.items():
        # apply to both tasks of section
        sec_tasks = section_to_tasks.get(sec_id, [])
        for (instr_id, score) in match_list:
            if instr_id not in instr_index_map:
                continue
            i_idx = instr_index_map[instr_id]
            weight = int(round(score * MATCH_WEIGHT_SCALE))
            for t in sec_tasks:
                b = assigned_instr[(t["task_id"], i_idx)]
                if weight != 0:
                    objective_terms.append(b * weight)

    # TBA penalties & real-room rewards
    for t in tasks:
        tid = t["task_id"]
        # is_tba boolean
        is_tba = model.NewBoolVar(f"is_tba_{tid}")
        model.Add(task_room_var[tid] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(task_room_var[tid] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        objective_terms.append(is_tba * (-TBA_PENALTY))
        # reward real room
        is_real = model.NewBoolVar(f"is_real_{tid}")
        model.Add(task_room_var[tid] != TBA_ROOM_IDX).OnlyEnforceIf(is_real)
        model.Add(task_room_var[tid] == TBA_ROOM_IDX).OnlyEnforceIf(is_real.Not())
        objective_terms.append(is_real * REAL_ROOM_REWARD)

    # Overload penalties
    for instr_id, ov in instr_overload.items():
        # penalize overload minutes
        objective_terms.append(ov * (-OVERLOAD_PENALTY_PER_MIN))

    model.Maximize(sum(objective_terms))

    # Solver parameters
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    solver.parameters.log_search_progress = True
    solver.parameters.max_memory_in_mb = 8192

    print(f"[Solver] Starting solve: {len(tasks)} tasks (derived from {len(sections)} sections), {len(instructors)} instructors, {len(rooms)} rooms, {NUM_SLOTS} slots.")
    status = solver.Solve(model)
    print(f"[Solver] Status: {solver.StatusName(status)}")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"[Solver] Objective: {solver.ObjectiveValue()}")
        # Prepare DB objects
        section_objs = {s.sectionId: s for s in Section.objects.filter(sectionId__in=sections)}
        instructor_objs = {i.instructorId: i for i in Instructor.objects.filter(instructorId__in=instructors)}
        room_objs = {r.roomId: r for r in Room.objects.filter(roomId__in=[r for r in rooms if r != "TBA"])}

        weekday_names = DAYS
        schedules_to_create = []

        for t in tasks:
            tid = t["task_id"]
            sec_id = t["section"]
            sec_obj = section_objs[sec_id]

            instr_idx = solver.Value(task_instr_var[tid])
            room_idx = solver.Value(task_room_var[tid])
            start_min = solver.Value(task_start[tid])
            # compute start time/day
            day_idx = start_min // 1440
            minute_of_day = start_min % 1440
            hour = minute_of_day // 60
            minute = minute_of_day % 60
            start_time = datetime(2000, 1, 1, hour, minute).time()

            # choose duration for saving — use authoritative data
            dur_min = t["dur"]
            end_dt = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=dur_min)
            end_time = end_dt.time()

            instructor = instructor_objs.get(instructors[instr_idx])
            room = None if room_idx == TBA_ROOM_IDX else room_objs.get(rooms[room_idx])

            schedule_type = t["kind"]
            is_overtime = False  # optional: compute from minute_of_day ranges if desired

            schedules_to_create.append(Schedule(
                subject=sec_obj.subject,
                instructor=instructor,
                section=sec_obj,
                room=room,
                semester=semester,
                dayOfWeek=weekday_names[day_idx],
                startTime=start_time,
                endTime=end_time,
                scheduleType=schedule_type,
                isOvertime=is_overtime,
                status='active'
            ))

        with transaction.atomic():
            Schedule.objects.filter(semester=semester, status='active').update(status='archived')
            Schedule.objects.bulk_create(schedules_to_create, ignore_conflicts=True)
            print(f"[Solver] Saved {len(schedules_to_create)} schedules for semester {semester} (status='active').")

        return schedules_to_create

    else:
        print("[Solver] No feasible solution found.")
        return []

def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=600)
