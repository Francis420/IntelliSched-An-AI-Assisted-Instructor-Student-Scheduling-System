# scheduler/solver.py
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
OVERLOAD_PENALTY_PER_MIN = 100000000000   # penalty per minute of overload (scaled)
WEEKEND_TIME_PENALTY_PER_MINUTE = 10000  # penalty per minute scheduled on weekends
WEEKDAY_EVENING_PENALTY_PER_MINUTE = 5000 # penalty per minute scheduled on weekday evenings (after 5 PM)

# -------------------- Timeslot metadata (same mapping as earlier generator)
def generate_timeslot_meta():
    slot_meta = []
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
            for hour in range(AFTERNOON_RANGE[0], AFTERNOON_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))

            # Overload period: 17:30-20:00
            hour = int(OVERLOAD_RANGE_WEEKDAYS[0])
            minute = 30
            while hour*60 + minute + INTERVAL_MINUTES <= OVERLOAD_RANGE_WEEKDAYS[1]*60 + 1e-9:
                minute_of_day = hour*60 + minute
                label = f"{day} {hour:02d}:{minute:02d}"
                minute_of_week = day_idx*1440 + minute_of_day
                slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                minute += INTERVAL_MINUTES
                if minute == 60:
                    minute = 0
                    hour += 1

        else:  # Sat-Sun
            for start_h, end_h in OVERLOAD_RANGE_WEEKENDS:
                hour = int(start_h)
                minute = 0
                while hour*60 + minute + INTERVAL_MINUTES <= end_h*60 + 1e-9:
                    minute_of_day = hour*60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx*1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    minute += INTERVAL_MINUTES
                    if minute == 60:
                        minute = 0
                        hour += 1

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
    tasks = []  # list of dicts: {task_id, section, kind('lecture'/'lab'), dur}
    for s in sections:
        sec_hours = data["section_hours"].get(s, {"lecture_min": 0, "lab_min": 0})
        lecture_d = int(sec_hours.get("lecture_min", 0) or 0)
        lab_d = int(sec_hours.get("lab_min", 0) or 0)

        # --- Lecture splitting rule ---
        if lecture_d > 120:  # more than 2 hours
            # Split equally
            half = lecture_d // 2
            other_half = lecture_d - half
            tasks.append({
                "task_id": f"{s}_LECT_A",
                "section": s,
                "kind": "lecture",
                "dur": half
            })
            tasks.append({
                "task_id": f"{s}_LECT_B",
                "section": s,
                "kind": "lecture",
                "dur": other_half
            })
        else:
            # Normal (≤ 2 hours)
            tasks.append({
                "task_id": f"{s}_LECT",
                "section": s,
                "kind": "lecture",
                "dur": lecture_d
            })
        if lab_d > 0:
            tasks.append({
                "task_id": f"{s}_LAB",
                "section": s,
                "kind": "lab",
                "dur": lab_d
            })

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

    # NEW: Initialize weekend time penalty
    total_overload_penalty = model.NewIntVar(0, WEEK_MINUTES * OVERLOAD_PENALTY_PER_MIN, "total_overload_penalty")
    total_weekend_time_penalty = model.NewIntVar(0, WEEK_MINUTES * WEEKEND_TIME_PENALTY_PER_MINUTE, "total_weekend_time_penalty")

    # ---------------------------------------------------------
    # BUILD ALLOWED START SLOTS PER TASK BASED ON DURATION + RULES
    # ---------------------------------------------------------

    def slot_allowed_for_duration(slot_idx, duration_min):
        day = SLOT_META[slot_idx][1]
        minute_of_day = SLOT_META[slot_idx][2]
        start = minute_of_day
        end = minute_of_day + duration_min

        # Must finish by 20:00
        if end > 20*60:
            return False

        # No lunch overlap
        if not (end <= 12*60 or start >= 13*60):
            return False

        # Daily allowed hours
        if day <= 4:  # Mon-Fri
            if start < 8*60 or (12*60 <= start < 13*60):
                return False
        else:  # Sat-Sun
            if start < 8*60 or (12*60 <= start < 13*60):
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
        dur = int(t["dur"])
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
    # IMPORTANT: fix this part dont forget, no overlap for rooms
    # for r_idx, ivs in room_intervals.items():
    #     if ivs:
    #         model.AddNoOverlap(ivs)

    # Lecture/Lab pairing constraints: same instructor
    # find tasks grouped by section
    section_to_tasks = defaultdict(list)
    for t in tasks:
        section_to_tasks[t["section"]].append(t)

    for sec, tlist in section_to_tasks.items():
        # Separate by kind
        lectures = [t for t in tlist if t["kind"] == "lecture"]
        labs = [t for t in tlist if t["kind"] == "lab"]

        # Pair all lectures with the same instructor as lab
        for lab_task in labs:
            for lect_task in lectures:
                model.Add(task_instr_var[lect_task["task_id"]] == task_instr_var[lab_task["task_id"]])
                # If you want them on different days uncomment the next line
                # model.Add(task_day[lect_task["task_id"]] != task_day[lab_task["task_id"]])

        # Handle split lectures (LECT_A / LECT_B) if present
        split_lects = [t for t in lectures if t["task_id"].endswith("_LECT_A") or t["task_id"].endswith("_LECT_B")]
        if len(split_lects) == 2:
            lectA, lectB = split_lects
            # Same instructor for split lectures
            model.Add(task_instr_var[lectA["task_id"]] == task_instr_var[lectB["task_id"]])
            # Minimum gap between split lectures
            gap = model.NewIntVar(0, 4620, f"gap_{lectA['task_id']}_{lectB['task_id']}")
            model.AddAbsEquality(gap, task_start[lectA["task_id"]] - task_start[lectB["task_id"]])
            model.Add(gap >= 30)

    # GenEd blocks
    for g_day, g_start_min, g_end_min in data.get("gened_blocks", []):
        g_start_global = g_day * 1440 + g_start_min
        g_end_global = g_day * 1440 + g_end_min

        for t in tasks:
            tid = t["task_id"]

            # Boolean: 1 if this task is NOT scheduled on the GenEd day
            diff_day = model.NewBoolVar(f"{tid}_diffday_g{g_day}")
            model.Add(task_day[tid] != g_day).OnlyEnforceIf(diff_day)
            model.Add(task_day[tid] == g_day).OnlyEnforceIf(diff_day.Not())

            # Boolean: 1 if task ends before GENED starts
            before = model.NewBoolVar(f"{tid}_before_g{g_day}")
            model.Add(task_end[tid] <= g_start_global).OnlyEnforceIf(before)
            model.Add(task_end[tid] > g_start_global).OnlyEnforceIf(before.Not())

            # Boolean: 1 if task starts after GENED ends
            after = model.NewBoolVar(f"{tid}_after_g{g_day}")
            model.Add(task_start[tid] >= g_end_global).OnlyEnforceIf(after)
            model.Add(task_start[tid] < g_end_global).OnlyEnforceIf(after.Not())

            # At least ONE of the 3 must be true → valid
            model.AddBoolOr([diff_day, before, after])


    # Instructor load & overload calculation
    instructor_caps = data["instructor_caps"]
    instr_total_min = {}   # keyed by instr_id (string)
    instr_overload = {}

    # OBJECTIVE terms (collect all terms here)
    objective_terms = []

    # Configuration for spreading
    MAX_DESIRED_DAILY_MINUTES = 360  # 6 hours per day max preferred
    DAILY_OVERLOAD_PENALTY = 50      # Penalty per minute over the daily 6-hour soft limit

    # We need to map tasks to their specific time characteristics first
    task_is_overtime = {} # (tid) -> BoolVar
    
    for t in tasks:
        tid = t["task_id"]
        
        # 1. Detect if this task is effectively "Overtime" based on rules
        # Rule: Weekend (Days 5,6) OR Weekday (0-4) >= 17:00 (1020 mins)
        
        # Is it a weekend?
        is_weekend = model.NewBoolVar(f"{tid}_is_weekend")
        model.Add(task_day[tid] >= 5).OnlyEnforceIf(is_weekend)
        model.Add(task_day[tid] < 5).OnlyEnforceIf(is_weekend.Not())
        
        # Is it evening? (Start >= 17:00 / 1020 minutes)
        # We need start minute within the day
        start_min_of_day = model.NewIntVar(0, 1440, f"{tid}_start_mod")
        model.AddModuloEquality(start_min_of_day, task_start[tid], 1440)
        
        is_evening = model.NewBoolVar(f"{tid}_is_evening")
        model.Add(start_min_of_day >= 1020).OnlyEnforceIf(is_evening)
        model.Add(start_min_of_day < 1020).OnlyEnforceIf(is_evening.Not())
        
        # Final "Is Overtime" definition
        # overtime = weekend OR (weekday AND evening)
        # Since weekend implies NOT weekday, we can just say: overtime = weekend OR evening
        # (Assuming evening implies time >= 17:00 regardless of day, but on weekend ALL time is overtime)
        
        # Let's be explicit:
        # If weekend -> True
        # If weekday AND evening -> True
        # Else -> False
        
        is_ot_var = model.NewBoolVar(f"{tid}_is_ot")
        
        # Logic: is_ot <==> is_weekend OR is_evening
        # Note: This simplifies "Weekday Evening" to just "Evening". 
        # Since 17:00+ on a Weekend is ALSO overtime, this logic holds for both cases.
        model.AddBoolOr([is_weekend, is_evening]).OnlyEnforceIf(is_ot_var)
        model.AddBoolAnd([is_weekend.Not(), is_evening.Not()]).OnlyEnforceIf(is_ot_var.Not())
        
        task_is_overtime[tid] = is_ot_var


    # Now apply limits and spreading per instructor
    for i_idx, instr_id in enumerate(instructors):
        caps = instructor_caps.get(instr_id, {})
        normal_limit = caps.get("normal_limit_min", 40 * 60)
        overload_limit = caps.get("overload_limit_min", 0)

        # --- A. SEPARATE NORMAL VS OVERLOAD BUCKETS ---
        
        # Variables for this instructor
        total_normal_min = model.NewIntVar(0, normal_limit, f"load_norm_{instr_id}")
        total_overload_min = model.NewIntVar(0, overload_limit, f"load_ot_{instr_id}")
        
        normal_terms = []
        overload_terms = []
        
        for t in tasks:
            tid = t["task_id"]
            dur = int(t["dur"])
            assigned = assigned_instr[(tid, i_idx)] # Bool: is assigned to this instr
            is_ot = task_is_overtime[tid]           # Bool: is this task OT?
            
            # We need the intersection: assigned AND is_ot
            # assigned_ot = assigned AND is_ot
            assigned_ot = model.NewBoolVar(f"assign_ot_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot]).OnlyEnforceIf(assigned_ot)
            model.AddBoolOr([assigned.Not(), is_ot.Not()]).OnlyEnforceIf(assigned_ot.Not())
            
            # assigned_normal = assigned AND (NOT is_ot)
            assigned_norm = model.NewBoolVar(f"assign_norm_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot.Not()]).OnlyEnforceIf(assigned_norm)
            model.AddBoolOr([assigned.Not(), is_ot]).OnlyEnforceIf(assigned_norm.Not())
            
            overload_terms.append(assigned_ot * dur)
            normal_terms.append(assigned_norm * dur)
            
        # Sum them up
        model.Add(total_normal_min == sum(normal_terms))
        model.Add(total_overload_min == sum(overload_terms))
        
        # Note: We do NOT need to penalize "overload" usage here anymore if it falls within 
        # the allowable overload_limit. The penalty should only be for using TBA or Bad Times.
        # However, if you want to discourage overload usage generally, add a small penalty:
        # objective_terms.append(total_overload_min * -10) 

        # --- B. SPREAD THE LOAD (Daily Limits) ---
        
        # We need to calculate how many minutes this instructor works on EACH day (0..6)
        for d_idx in range(7):
            daily_dur_terms = []
            
            for t in tasks:
                tid = t["task_id"]
                dur = int(t["dur"])
                
                # assigned to this instr?
                assigned = assigned_instr[(tid, i_idx)]
                
                # is on this day?
                # We need a bool: on_this_day = (task_day == d_idx)
                on_this_day = model.NewBoolVar(f"{tid}_on_day_{d_idx}")
                model.Add(task_day[tid] == d_idx).OnlyEnforceIf(on_this_day)
                model.Add(task_day[tid] != d_idx).OnlyEnforceIf(on_this_day.Not())
                
                # Active if assigned AND on_this_day
                active_on_day = model.NewBoolVar(f"{tid}_active_{d_idx}_{i_idx}")
                model.AddBoolAnd([assigned, on_this_day]).OnlyEnforceIf(active_on_day)
                model.AddBoolOr([assigned.Not(), on_this_day.Not()]).OnlyEnforceIf(active_on_day.Not())
                
                daily_dur_terms.append(active_on_day * dur)
            
            # Total minutes for this instructor on this day
            daily_total = model.NewIntVar(0, 1440, f"daily_load_{instr_id}_{d_idx}")
            model.Add(daily_total == sum(daily_dur_terms))
            
            # Soft Constraint: Prefer <= MAX_DESIRED_DAILY_MINUTES (e.g., 6 hours)
            # excess = max(0, daily_total - 360)
            daily_excess = model.NewIntVar(0, 1440, f"daily_excess_{instr_id}_{d_idx}")
            
            # Implementation of max(0, val) in CP-SAT
            # daily_excess >= daily_total - limit
            model.Add(daily_excess >= daily_total - MAX_DESIRED_DAILY_MINUTES)
            # daily_excess >= 0 (implicit in definition)
            
            # Apply penalty to objective
            objective_terms.append(daily_excess * -DAILY_OVERLOAD_PENALTY)


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
        # -------------------- NEW: Weekend Time Penalty (Tier 2/Highest) --------------------
        # Penalty for Sat/Sun use (Day 5 or 6)

        # Boolean: True if the task is scheduled on Saturday or Sunday
        is_weekend = model.NewBoolVar(f"is_weekend_{tid}")
        model.Add(task_day[tid] >= 5).OnlyEnforceIf(is_weekend) 

        # Penalty term: is_weekend * duration * WEEKEND_TIME_PENALTY_PER_MINUTE
        weekend_penalty_term = is_weekend * t["dur"] * WEEKEND_TIME_PENALTY_PER_MINUTE

        # Add the penalty term (as a negative value) to the objective
        objective_terms.append(weekend_penalty_term * -1)

        # -------------------- NEW: Weekday Evening Penalty (Tier 1/Lower) --------------------
        # Penalty for M-F 17:00-20:00 (outside of core normal window)

        # 1. Boolean: Is it a weekday (Mon-Fri, Day 0-4)?
        is_weekday = model.NewBoolVar(f"is_weekday_{tid}")
        model.Add(task_day[tid] <= 4).OnlyEnforceIf(is_weekday) 

        # 2. Calculate the task's start minute within the day (0-1439). Necessary for time check.
        # task_start[tid] is a global minute, 1440 is the minutes in a day.
        minute_of_day_start = model.NewIntVar(0, 1439, f"min_day_start_{tid}")
        model.AddModuloEquality(minute_of_day_start, task_start[tid], 1440)

        # 3. Boolean: Does it start at or after 17:00 (1020 minutes)?
        # 17 * 60 = 1020. Since 20:00 is the hard stop, this is sufficient.
        is_evening_start = model.NewBoolVar(f"is_evening_start_{tid}")
        model.Add(minute_of_day_start >= 1020).OnlyEnforceIf(is_evening_start)

        # 4. Final condition: Is it a Weekday AND an Evening Start?
        is_weekday_overload = model.NewBoolVar(f"is_weekday_overload_{tid}")
        model.AddBoolAnd([is_weekday, is_evening_start]).OnlyEnforceIf(is_weekday_overload)

        # 5. Apply penalty and add to objective_terms
        weekday_overload_penalty_term = is_weekday_overload * t["dur"] * WEEKDAY_EVENING_PENALTY_PER_MINUTE
        objective_terms.append(weekday_overload_penalty_term * -1)

    # Overload penalties
    for instr_id, ov in instr_overload.items():
        # penalize overload minutes
        objective_terms.append(ov * (-OVERLOAD_PENALTY_PER_MIN))

    objective = model.NewIntVar(-1000000000, 1000000000, "objective") 
    model.Add(objective == sum(objective_terms))
    model.Maximize(objective)

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
            is_weekend_bool = (day_idx >= 5)
            is_evening_bool = (minute_of_day >= 1020)

            schedule_type = t["kind"]
            final_is_overtime = is_weekend_bool or is_evening_bool

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
                isOvertime=final_is_overtime,
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
