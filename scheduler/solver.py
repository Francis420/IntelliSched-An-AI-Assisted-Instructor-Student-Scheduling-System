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

# <--- CHANGED: Increased penalties to force Normal Load utilization first
WEEKEND_TIME_PENALTY_PER_MINUTE = 10000   # Huge penalty for Weekends
WEEKDAY_EVENING_PENALTY_PER_MINUTE = 500  # High penalty for Weekday Evenings (prev. 100)
GLOBAL_OVERLOAD_COST_PER_MIN = 1000       # NEW: Direct penalty for every minute in the "Overload" bucket

# -------------------- Timeslot metadata --------------------
def generate_timeslot_meta():
    slot_meta = []
    MORNING_RANGE = (8, 12)
    AFTERNOON_RANGE = (13, 17)
    
    # Overload ranges
    OVERLOAD_RANGE_WEEKDAYS = (17, 20) 
    OVERLOAD_RANGE_WEEKENDS = [(8, 12), (13, 20)]

    for day_idx, day in enumerate(DAYS):
        if day_idx <= 4:  # Mon-Fri
            # Normal Morning
            for hour in range(MORNING_RANGE[0], MORNING_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
            
            # Normal Afternoon
            for hour in range(AFTERNOON_RANGE[0], AFTERNOON_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    label = f"{day} {hour:02d}:{minute:02d}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))

            # Overload period: 17:00-20:00
            start_h = int(OVERLOAD_RANGE_WEEKDAYS[0])
            end_h = int(OVERLOAD_RANGE_WEEKDAYS[1])
            
            hour = start_h
            minute = 0
            while hour * 60 + minute + INTERVAL_MINUTES <= end_h * 60 + 1e-9:
                minute_of_day = hour * 60 + minute
                label = f"{day} {hour:02d}:{minute:02d}"
                minute_of_week = day_idx * 1440 + minute_of_day
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

    model = cp_model.CpModel()

    # Tasks creation
    tasks = []
    for s in sections:
        sec_hours = data["section_hours"].get(s, {"lecture_min": 0, "lab_min": 0})
        lecture_d = int(sec_hours.get("lecture_min", 0) or 0)
        lab_d = int(sec_hours.get("lab_min", 0) or 0)

        if lecture_d > 120:
            half = lecture_d // 2
            other_half = lecture_d - half
            tasks.append({
                "task_id": f"{s}_LECT_A", "section": s, "kind": "lecture", "dur": half
            })
            tasks.append({
                "task_id": f"{s}_LECT_B", "section": s, "kind": "lecture", "dur": other_half
            })
        else:
            tasks.append({
                "task_id": f"{s}_LECT", "section": s, "kind": "lecture", "dur": lecture_d
            })
        if lab_d > 0:
            tasks.append({
                "task_id": f"{s}_LAB", "section": s, "kind": "lab", "dur": lab_d
            })

    # Decision vars
    task_start = {}
    task_end = {}
    task_slot = {}
    task_day = {}
    task_interval = {}
    task_instr_var = {}
    task_room_var = {}

    assigned_instr = {}
    instr_intervals = defaultdict(list)
    assigned_room = {}
    room_intervals = defaultdict(list)

    # Allowed slots helper
    allowed_slots_for_duration = {}
    def slot_allowed_for_duration(slot_idx, duration_min):
        day = SLOT_META[slot_idx][1]
        minute_of_day = SLOT_META[slot_idx][2]
        start = minute_of_day
        end = minute_of_day + duration_min
        if end > 20*60: return False 
        if not (end <= 12*60 or start >= 13*60): return False # Lunch break
        if start < 8*60 or (12*60 <= start < 13*60): return False
        return True

    def get_allowed_slots(dur):
        if dur not in allowed_slots_for_duration:
            lst = []
            for i in range(NUM_SLOTS):
                if slot_allowed_for_duration(i, dur):
                    lst.append(i)
            allowed_slots_for_duration[dur] = lst
        return allowed_slots_for_duration[dur]

    latest_end_by_day = {d: 20*60 for d in range(7)}

    for t in tasks:
        tid = t["task_id"]
        dur = int(t["dur"])
        allowed_slots = get_allowed_slots(dur)

        task_slot[tid] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(allowed_slots), f"slot_{tid}"
        )
        allowed_slot_start_pairs_filtered = [(i, SLOT_TO_GLOBAL_MIN[i]) for i in allowed_slots]
        allowed_slot_day_pairs_filtered = [(i, SLOT_TO_DAY[i]) for i in allowed_slots]
        
        task_start[tid] = model.NewIntVar(0, WEEK_MINUTES - 1, f"start_{tid}")
        task_end[tid] = model.NewIntVar(0, WEEK_MINUTES, f"end_{tid}")
        task_day[tid] = model.NewIntVar(0, 6, f"day_{tid}")

        model.AddAllowedAssignments([task_slot[tid], task_start[tid]], allowed_slot_start_pairs_filtered)
        model.AddAllowedAssignments([task_slot[tid], task_day[tid]], allowed_slot_day_pairs_filtered)
        model.Add(task_end[tid] == task_start[tid] + dur)

        # Enforce finish by 20:00
        for day_idx in range(7):
            cond = model.NewBoolVar(f"{tid}_day{day_idx}")
            model.Add(task_day[tid] == day_idx).OnlyEnforceIf(cond)
            model.Add(task_day[tid] != day_idx).OnlyEnforceIf(cond.Not())
            allowed_end_global = day_idx*1440 + latest_end_by_day[day_idx]
            model.Add(task_end[tid] <= allowed_end_global).OnlyEnforceIf(cond)

        # "No Straddle" Constraint
        is_weekday = model.NewBoolVar(f"{tid}_is_weekday")
        model.Add(task_day[tid] <= 4).OnlyEnforceIf(is_weekday)
        model.Add(task_day[tid] >= 5).OnlyEnforceIf(is_weekday.Not())

        start_min_of_day = model.NewIntVar(0, 1440, f"{tid}_start_mod")
        model.AddModuloEquality(start_min_of_day, task_start[tid], 1440)
        
        end_min_of_day = model.NewIntVar(0, 1440, f"{tid}_end_mod")
        model.AddModuloEquality(end_min_of_day, task_end[tid], 1440)

        ends_early = model.NewBoolVar(f"{tid}_ends_early")
        model.Add(end_min_of_day <= 1020).OnlyEnforceIf(ends_early) # <= 17:00
        model.Add(end_min_of_day > 1020).OnlyEnforceIf(ends_early.Not())

        starts_late = model.NewBoolVar(f"{tid}_starts_late")
        model.Add(start_min_of_day >= 1020).OnlyEnforceIf(starts_late) # >= 17:00
        model.Add(start_min_of_day < 1020).OnlyEnforceIf(starts_late.Not())

        model.AddBoolOr([ends_early, starts_late]).OnlyEnforceIf(is_weekday)

        task_interval[tid] = model.NewIntervalVar(task_start[tid], dur, task_end[tid], f"iv_{tid}")
        task_instr_var[tid] = model.NewIntVar(0, max(0, num_instructors - 1), f"instr_{tid}")
        task_room_var[tid] = model.NewIntVar(0, max(0, num_rooms - 1), f"room_{tid}")

        # Assignment Logic
        for i_idx in range(num_instructors):
            b = model.NewBoolVar(f"assign_{tid}_instr{i_idx}")
            assigned_instr[(tid, i_idx)] = b
            model.Add(task_instr_var[tid] == i_idx).OnlyEnforceIf(b)
            model.Add(task_instr_var[tid] != i_idx).OnlyEnforceIf(b.Not())
            iv = model.NewOptionalIntervalVar(task_start[tid], dur, task_end[tid], b, f"iv_{tid}_instr{i_idx}")
            instr_intervals[i_idx].append(iv)
        model.Add(sum(assigned_instr[(tid, i_idx)] for i_idx in range(num_instructors)) == 1)

        # Rooms
        for r_idx in range(num_rooms):
            b = model.NewBoolVar(f"assign_{tid}_room{r_idx}")
            assigned_room[(tid, r_idx)] = b
            model.Add(task_room_var[tid] == r_idx).OnlyEnforceIf(b)
            model.Add(task_room_var[tid] != r_idx).OnlyEnforceIf(b.Not())
            if r_idx != TBA_ROOM_IDX:
                iv = model.NewOptionalIntervalVar(task_start[tid], dur, task_end[tid], b, f"iv_{tid}_room{r_idx}")
                room_intervals[r_idx].append(iv)
        model.Add(sum(assigned_room[(tid, r_idx)] for r_idx in range(num_rooms)) == 1)

    # No Overlap
    for i_idx, ivs in instr_intervals.items():
        if ivs: model.AddNoOverlap(ivs)
    # UNCOMMENT TO FIX ROOM OVERLAPS
    # for r_idx, ivs in room_intervals.items():
    #     if ivs: model.AddNoOverlap(ivs)

    # Links & Gaps
    section_to_tasks = defaultdict(list)
    for t in tasks: section_to_tasks[t["section"]].append(t)

    for sec, tlist in section_to_tasks.items():
        lectures = [t for t in tlist if t["kind"] == "lecture"]
        labs = [t for t in tlist if t["kind"] == "lab"]
        for lab_task in labs:
            for lect_task in lectures:
                model.Add(task_instr_var[lect_task["task_id"]] == task_instr_var[lab_task["task_id"]])
        
        split_lects = [t for t in lectures if t["task_id"].endswith("_LECT_A") or t["task_id"].endswith("_LECT_B")]
        if len(split_lects) == 2:
            lectA, lectB = split_lects
            model.Add(task_instr_var[lectA["task_id"]] == task_instr_var[lectB["task_id"]])
            
            # <--- CHANGED: True Gap Logic (EndA -> StartB >= 30 mins)
            # This is equivalent to |StartA - StartB| >= Duration + 30
            # (Assuming A and B have roughly same duration, which is true for split halves)
            durA = lectA["dur"]
            min_gap_start = durA + 30
            
            diff = model.NewIntVar(0, WEEK_MINUTES, f"diff_{lectA['task_id']}_{lectB['task_id']}")
            model.AddAbsEquality(diff, task_start[lectA["task_id"]] - task_start[lectB["task_id"]])
            model.Add(diff >= min_gap_start)

    # GenEd Blocks
    for g_day, g_start_min, g_end_min in data.get("gened_blocks", []):
        g_start_global = g_day * 1440 + g_start_min
        g_end_global = g_day * 1440 + g_end_min
        for t in tasks:
            tid = t["task_id"]
            diff_day = model.NewBoolVar(f"{tid}_diffday_g{g_day}")
            model.Add(task_day[tid] != g_day).OnlyEnforceIf(diff_day)
            model.Add(task_day[tid] == g_day).OnlyEnforceIf(diff_day.Not())
            before = model.NewBoolVar(f"{tid}_before_g{g_day}")
            model.Add(task_end[tid] <= g_start_global).OnlyEnforceIf(before)
            model.Add(task_end[tid] > g_start_global).OnlyEnforceIf(before.Not())
            after = model.NewBoolVar(f"{tid}_after_g{g_day}")
            model.Add(task_start[tid] >= g_end_global).OnlyEnforceIf(after)
            model.Add(task_start[tid] < g_end_global).OnlyEnforceIf(after.Not())
            model.AddBoolOr([diff_day, before, after])

    # -------------------- Load & Objectives --------------------
    instructor_caps = data["instructor_caps"]
    objective_terms = []
    
    task_is_overtime = {} 
    
    for t in tasks:
        tid = t["task_id"]
        # Rule: Weekend OR (Weekday AND Start >= 17:00)
        is_weekend = model.NewBoolVar(f"{tid}_is_weekend")
        model.Add(task_day[tid] >= 5).OnlyEnforceIf(is_weekend)
        model.Add(task_day[tid] < 5).OnlyEnforceIf(is_weekend.Not())
        
        start_min_of_day = model.NewIntVar(0, 1440, f"{tid}_start_mod_ot")
        model.AddModuloEquality(start_min_of_day, task_start[tid], 1440)
        
        is_evening = model.NewBoolVar(f"{tid}_is_evening")
        model.Add(start_min_of_day >= 1020).OnlyEnforceIf(is_evening)
        model.Add(start_min_of_day < 1020).OnlyEnforceIf(is_evening.Not())
        
        is_ot_var = model.NewBoolVar(f"{tid}_is_ot")
        model.AddBoolOr([is_weekend, is_evening]).OnlyEnforceIf(is_ot_var)
        model.AddBoolAnd([is_weekend.Not(), is_evening.Not()]).OnlyEnforceIf(is_ot_var.Not())
        task_is_overtime[tid] = is_ot_var

    for i_idx, instr_id in enumerate(instructors):
        caps = instructor_caps.get(instr_id, {})
        normal_limit = caps.get("normal_limit_min", 40 * 60)
        overload_limit = caps.get("overload_limit_min", 0)

        total_normal_min = model.NewIntVar(0, normal_limit, f"load_norm_{instr_id}")
        total_overload_min = model.NewIntVar(0, overload_limit, f"load_ot_{instr_id}")
        
        normal_terms = []
        overload_terms = []
        
        for t in tasks:
            tid = t["task_id"]
            dur = int(t["dur"])
            assigned = assigned_instr[(tid, i_idx)]
            is_ot = task_is_overtime[tid]
            
            assigned_ot = model.NewBoolVar(f"assign_ot_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot]).OnlyEnforceIf(assigned_ot)
            model.AddBoolOr([assigned.Not(), is_ot.Not()]).OnlyEnforceIf(assigned_ot.Not())
            
            assigned_norm = model.NewBoolVar(f"assign_norm_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot.Not()]).OnlyEnforceIf(assigned_norm)
            model.AddBoolOr([assigned.Not(), is_ot]).OnlyEnforceIf(assigned_norm.Not())
            
            overload_terms.append(assigned_ot * dur)
            normal_terms.append(assigned_norm * dur)
            
        model.Add(total_normal_min == sum(normal_terms))
        model.Add(total_overload_min == sum(overload_terms))

        # <--- CHANGED: Penalize Overload Bucket Usage 
        # This ensures we prefer filling Normal bucket first.
        objective_terms.append(total_overload_min * -GLOBAL_OVERLOAD_COST_PER_MIN)

        # <--- CHANGED: Better Spreading (Sum of Squares)
        # Instead of a soft limit, we minimize sum(daily_minutes^2).
        # This mathematically forces spreading (e.g., 2,2,2,2 is better than 8,0,0,0)
        for d_idx in range(7):
            daily_dur_terms = []
            for t in tasks:
                tid = t["task_id"]
                dur = int(t["dur"])
                assigned = assigned_instr[(tid, i_idx)]
                on_this_day = model.NewBoolVar(f"{tid}_on_day_{d_idx}")
                model.Add(task_day[tid] == d_idx).OnlyEnforceIf(on_this_day)
                model.Add(task_day[tid] != d_idx).OnlyEnforceIf(on_this_day.Not())
                
                active_on_day = model.NewBoolVar(f"{tid}_active_{d_idx}_{i_idx}")
                model.AddBoolAnd([assigned, on_this_day]).OnlyEnforceIf(active_on_day)
                model.AddBoolOr([assigned.Not(), on_this_day.Not()]).OnlyEnforceIf(active_on_day.Not())
                daily_dur_terms.append(active_on_day * dur)
            
            daily_total = model.NewIntVar(0, 1440, f"daily_load_{instr_id}_{d_idx}")
            model.Add(daily_total == sum(daily_dur_terms))
            
            # Quadratic Penalty: cost += (daily_total * daily_total)
            # Scaling: Since 360^2 is big, we can scale down or just apply small weight.
            sq = model.NewIntVar(0, 1440*1440, f"sq_load_{instr_id}_{d_idx}")
            model.AddMultiplicationEquality(sq, [daily_total, daily_total])
            # Weight 1 is usually enough for quadratic terms to dominate peaks
            objective_terms.append(sq * -1)

    # Objectives
    matches = data.get("matches", {})
    instr_index_map = data.get("instructor_index", {})
    for sec_id, match_list in matches.items():
        sec_tasks = section_to_tasks.get(sec_id, [])
        for (instr_id, score) in match_list:
            if instr_id not in instr_index_map: continue
            i_idx = instr_index_map[instr_id]
            weight = int(round(score * MATCH_WEIGHT_SCALE))
            for t in sec_tasks:
                b = assigned_instr[(t["task_id"], i_idx)]
                if weight != 0: objective_terms.append(b * weight)

    for t in tasks:
        tid = t["task_id"]
        # TBA penalty
        is_tba = model.NewBoolVar(f"is_tba_{tid}")
        model.Add(task_room_var[tid] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(task_room_var[tid] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        objective_terms.append(is_tba * (-TBA_PENALTY))
        
        is_real = model.NewBoolVar(f"is_real_{tid}")
        model.Add(task_room_var[tid] != TBA_ROOM_IDX).OnlyEnforceIf(is_real)
        model.Add(task_room_var[tid] == TBA_ROOM_IDX).OnlyEnforceIf(is_real.Not())
        objective_terms.append(is_real * REAL_ROOM_REWARD)
        
        # Weekend Penalty 
        is_weekend = model.NewBoolVar(f"is_weekend_pen_{tid}")
        model.Add(task_day[tid] >= 5).OnlyEnforceIf(is_weekend) 
        model.Add(task_day[tid] < 5).OnlyEnforceIf(is_weekend.Not()) 
        objective_terms.append(is_weekend * t["dur"] * -WEEKEND_TIME_PENALTY_PER_MINUTE)

        # Weekday Evening Penalty
        is_weekday = model.NewBoolVar(f"is_weekday_pen_{tid}")
        model.Add(task_day[tid] <= 4).OnlyEnforceIf(is_weekday) 
        
        start_mod_pen = model.NewIntVar(0, 1439, f"start_mod_pen_{tid}")
        model.AddModuloEquality(start_mod_pen, task_start[tid], 1440)
        is_evening_start = model.NewBoolVar(f"is_evening_start_{tid}")
        model.Add(start_mod_pen >= 1020).OnlyEnforceIf(is_evening_start)
        
        is_weekday_overload = model.NewBoolVar(f"is_weekday_overload_{tid}")
        model.AddBoolAnd([is_weekday, is_evening_start]).OnlyEnforceIf(is_weekday_overload)
        
        objective_terms.append(is_weekday_overload * t["dur"] * -WEEKDAY_EVENING_PENALTY_PER_MINUTE)

    objective = model.NewIntVar(-10000000000000, 10000000000000, "objective") 
    model.Add(objective == sum(objective_terms))
    model.Maximize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    
    print(f"[Solver] Starting solve...")
    status = solver.Solve(model)
    print(f"[Solver] Status: {solver.StatusName(status)}")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        section_objs = {s.sectionId: s for s in Section.objects.filter(sectionId__in=sections)}
        instructor_objs = {i.instructorId: i for i in Instructor.objects.filter(instructorId__in=instructors)}
        room_objs = {r.roomId: r for r in Room.objects.filter(roomId__in=[r for r in rooms if r != "TBA"])}
        weekday_names = DAYS
        schedules_to_create = []

        for t in tasks:
            tid = t["task_id"]
            sec_obj = section_objs[t["section"]]
            instr_idx = solver.Value(task_instr_var[tid])
            room_idx = solver.Value(task_room_var[tid])
            start_min = solver.Value(task_start[tid])
            
            day_idx = start_min // 1440
            minute_of_day = start_min % 1440
            hour = minute_of_day // 60
            minute = minute_of_day % 60
            start_time = datetime(2000, 1, 1, hour, minute).time()
            end_dt = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=t["dur"])
            end_time = end_dt.time()

            instructor = instructor_objs.get(instructors[instr_idx])
            room = None if room_idx == TBA_ROOM_IDX else room_objs.get(rooms[room_idx])
            
            is_weekend_bool = (day_idx >= 5)
            is_evening_bool = (minute_of_day >= 1020)
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
                scheduleType=t["kind"],
                isOvertime=final_is_overtime,
                status='active'
            ))

        with transaction.atomic():
            Schedule.objects.filter(semester=semester, status='active').update(status='archived')
            Schedule.objects.bulk_create(schedules_to_create, ignore_conflicts=True)
            print(f"[Solver] Saved {len(schedules_to_create)} schedules.")

        return schedules_to_create
    else:
        print("[Solver] No feasible solution found.")
        return []

def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=600)