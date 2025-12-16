# scheduler/solver.py
import math
from collections import defaultdict
from datetime import datetime, timedelta

from ortools.sat.python import cp_model
from django.db import transaction
from django.utils import timezone

from scheduling.models import Section, Semester, Schedule, Room
from core.models import Instructor
from scheduler.data_extractors import get_solver_data


# -------------------- Configuration --------------------
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
INTERVAL_MINUTES = 30
WEEK_MINUTES = 7 * 24 * 60

# --- WEIGHTS & TUNING ---
MATCH_WEIGHT_SCALE = 5          
REAL_ROOM_REWARD = 20           # Increased: Prefer real rooms over TBA strongly

# Penalties
TBA_PENALTY_NORMAL = 50         
TBA_PENALTY_PRIORITY = 5000     

# Time Preference Penalties (Soft)
# These are small tie-breakers. The heavy lifting is done in the Load Balancing section.
WEEKEND_TIME_PENALTY_PER_MINUTE = 1     
WEEKDAY_EVENING_PENALTY_PER_MINUTE = 1  

# --- CRITICAL LOAD BALANCING WEIGHTS ---

# 1. THE GOLD STANDARD (Normal Load Reward)
# Every minute assigned Mon-Fri (7am-5pm) gives huge points.
# This creates a "Vacuum" that sucks classes into weekdays.
STANDARD_LOAD_REWARD = 50 

# 2. THE DEBT (Premium/Overload Penalty)
# Every minute assigned Sat/Sun/Eve costs points.
# This forces the solver to move these to weekdays if a slot is available.
PREMIUM_LOAD_PENALTY = 50

# 3. THE EQUALIZER (Total Load Squared)
# We square the TOTAL load of the instructor. 
# Cost of 20 hours (20^2=400) is much worse than two people at 10 hours (10^2+10^2=200).
# This forces the 20-hour people to give classes to the 5-hour people.
TOTAL_LOAD_SQUARED_PENALTY = 10 

# 4. Underload Penalty
# If you are below 18 hours, we apply a penalty to urge the solver to give you *something*.
UNDERLOAD_PENALTY = 10

# 5. Daily Spread (Burnout prevention)
DAILY_SPREAD_PENALTY = 5
MAX_DESIRED_DAILY_MIN = 360     # 6 hours preference


# -------------------- Timeslot Generation --------------------
def generate_timeslot_meta():
    slot_meta = []
    # Standard blocks: 07:00 to 21:00
    start_h = 7
    end_h = 21
    
    for day_idx, day in enumerate(DAYS):
        hour = start_h
        minute = 0
        while hour < end_h:
            minute_of_day = hour * 60 + minute
            label = f"{day} {hour:02d}:{minute:02d}"
            minute_of_week = day_idx * 1440 + minute_of_day
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


# ----------------- Main Solver -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=300):
    if semester is None:
        semester = Semester.objects.filter(isActive=True).order_by('-createdAt').first()
        if not semester:
            print("[Solver] Error: No active semester found.")
            return []
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Starting Optimization for: {semester}")
    
    # 1. Fetch Data
    data = get_solver_data(semester)
    sections = list(data["sections"])
    rooms = list(data["rooms"])
    instructors = list(data["instructors"])
    instructor_caps = data["instructor_caps"]
    
    room_types = data.get("room_types", {})
    room_capacities = data.get("room_capacities", {}) 
    section_num_students = data.get("section_num_students", {})
    
    num_rooms = len(rooms)
    num_instructors = len(instructors)
    
    TBA_ROOM_IDX = data.get("TBA_ROOM_IDX", num_rooms - 1)

    # Room Groupings
    lecture_base_indices = {TBA_ROOM_IDX}
    lab_base_indices = {TBA_ROOM_IDX}
    for i in range(num_rooms):
        rtype = room_types.get(i, 'lecture')
        if rtype in ('lecture', 'universal'): lecture_base_indices.add(i)
        if rtype in ('laboratory', 'universal'): lab_base_indices.add(i)

    # 2. Build Model
    model = cp_model.CpModel()

    # --- Task Generation ---
    tasks = []
    for s in sections:
        sec_hours = data["section_hours"].get(s, {"lecture_min": 0, "lab_min": 0})
        lecture_d = int(sec_hours.get("lecture_min", 0) or 0)
        lab_d = int(sec_hours.get("lab_min", 0) or 0)

        # Split long lectures (> 3 hours)
        if lecture_d > 180:
            half = (lecture_d // 2 // 30) * 30 
            other = lecture_d - half
            tasks.append({"task_id": f"{s}_LECT_A", "section": s, "kind": "lecture", "dur": half})
            tasks.append({"task_id": f"{s}_LECT_B", "section": s, "kind": "lecture", "dur": other})
        elif lecture_d > 0:
            tasks.append({"task_id": f"{s}_LECT", "section": s, "kind": "lecture", "dur": lecture_d})
            
        if lab_d > 0:
            tasks.append({"task_id": f"{s}_LAB", "section": s, "kind": "lab", "dur": lab_d})

    # --- Variables ---
    task_vars = {} 
    assigned_instr = defaultdict(list)
    assigned_room = defaultdict(list)
    instr_intervals = defaultdict(list)
    room_intervals = defaultdict(list) 
    
    # Track "Premium" status of tasks (Weekend/Evening)
    task_is_premium = {} 

    allowed_slots_cache = {}
    def get_allowed_slots_for_duration(dur):
        if dur not in allowed_slots_cache:
            slots = []
            for i in range(NUM_SLOTS):
                day = SLOT_META[i][1]
                min_day = SLOT_META[i][2]
                end = min_day + dur
                if end > 21*60: continue 
                if not (end <= 12*60 or min_day >= 13*60): continue
                slots.append(i)
            allowed_slots_cache[dur] = slots
        return allowed_slots_cache[dur]

    print(f"[Solver] Building constraints for {len(tasks)} tasks...")

    for t in tasks:
        tid = t["task_id"]
        dur = int(t["dur"])
        allowed_slots = get_allowed_slots_for_duration(dur)

        # Time
        slot_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_slots), f"slot_{tid}")
        start_var = model.NewIntVar(0, WEEK_MINUTES, f"start_{tid}")
        end_var = model.NewIntVar(0, WEEK_MINUTES, f"end_{tid}")
        day_var = model.NewIntVar(0, 6, f"day_{tid}")

        model.AddAllowedAssignments([slot_var, start_var], [(i, SLOT_TO_GLOBAL_MIN[i]) for i in allowed_slots])
        model.AddAllowedAssignments([slot_var, day_var], [(i, SLOT_TO_DAY[i]) for i in allowed_slots])
        model.Add(end_var == start_var + dur)
        
        # --- Identify Standard vs Premium Time ---
        # Standard: Mon-Fri (0-4) AND Start < 17:00 (5 PM)
        
        is_weekend = model.NewBoolVar(f"{tid}_is_we")
        model.Add(day_var >= 5).OnlyEnforceIf(is_weekend)
        model.Add(day_var < 5).OnlyEnforceIf(is_weekend.Not())

        start_mod = model.NewIntVar(0, 1440, f"{tid}_start_mod")
        model.AddModuloEquality(start_mod, start_var, 1440)
        
        is_evening = model.NewBoolVar(f"{tid}_is_eve")
        # Start >= 17:00 (1020 min) is Evening
        model.Add(start_mod >= 1020).OnlyEnforceIf(is_evening)
        model.Add(start_mod < 1020).OnlyEnforceIf(is_evening.Not())

        is_premium = model.NewBoolVar(f"{tid}_is_prem")
        model.AddBoolOr([is_weekend, is_evening]).OnlyEnforceIf(is_premium)
        model.AddBoolAnd([is_weekend.Not(), is_evening.Not()]).OnlyEnforceIf(is_premium.Not())
        
        task_is_premium[tid] = is_premium

        # Room
        base_indices = lab_base_indices if t["kind"] == "lab" else lecture_base_indices
        req_students = section_num_students.get(t["section"], 0)
        valid_rooms = [TBA_ROOM_IDX]
        for r_idx in base_indices:
            if r_idx == TBA_ROOM_IDX: continue
            if room_capacities.get(r_idx, 0) >= req_students:
                valid_rooms.append(r_idx)
        
        room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(sorted(valid_rooms)), f"room_{tid}")
        
        # Instructor
        instr_var = model.NewIntVar(0, num_instructors - 1, f"instr_{tid}")

        task_vars[tid] = {
            "start": start_var, "end": end_var, "day": day_var, 
            "room": room_var, "instr": instr_var, "dur": dur,
            "kind": t["kind"], "section": t["section"]
        }

        # Assignments
        for i_idx in range(num_instructors):
            b = model.NewBoolVar(f"as_{tid}_i{i_idx}")
            assigned_instr[(tid, i_idx)] = b
            model.Add(instr_var == i_idx).OnlyEnforceIf(b)
            model.Add(instr_var != i_idx).OnlyEnforceIf(b.Not())
            iv = model.NewOptionalIntervalVar(start_var, dur, end_var, b, f"iv_i_{tid}_{i_idx}")
            instr_intervals[i_idx].append(iv)
        
        model.Add(sum(assigned_instr[(tid, i)] for i in range(num_instructors)) == 1)

        for r_idx in range(num_rooms):
            b = model.NewBoolVar(f"as_{tid}_r{r_idx}")
            assigned_room[(tid, r_idx)] = b
            model.Add(room_var == r_idx).OnlyEnforceIf(b)
            model.Add(room_var != r_idx).OnlyEnforceIf(b.Not())
            if r_idx != TBA_ROOM_IDX:
                iv = model.NewOptionalIntervalVar(start_var, dur, end_var, b, f"iv_r_{tid}")
                room_intervals[r_idx].append(iv)
        model.Add(sum(assigned_room[(tid, r)] for r in range(num_rooms)) == 1)

    # No Overlap
    for i_idx, ivs in instr_intervals.items():
        if ivs: model.AddNoOverlap(ivs)
    for r_idx, ivs in room_intervals.items():
        if ivs: model.AddNoOverlap(ivs)

    # Links
    section_to_tasks = defaultdict(list)
    for t in tasks:
        section_to_tasks[t["section"]].append(t)
    
    for sec, tlist in section_to_tasks.items():
        if len(tlist) > 1:
            for k in range(len(tlist) - 1):
                t1 = tlist[k]
                t2 = tlist[k+1]
                model.Add(task_vars[t1["task_id"]]["instr"] == task_vars[t2["task_id"]]["instr"])

    # -------------------- OBJECTIVES & LOAD BALANCING --------------------
    objective_terms = []

    for i_idx, instr_id in enumerate(instructors):
        caps = instructor_caps.get(instr_id, {})
        reg_limit = caps.get("normal_limit_min", 18 * 60)
        
        my_standard_minutes_vars = []
        my_premium_minutes_vars = []
        my_total_minutes_vars = []
        
        for t in tasks:
            tid = t["task_id"]
            dur = t["dur"]
            assigned_to_me = assigned_instr[(tid, i_idx)]
            is_prem = task_is_premium[tid] 
            
            # Reify: Assigned AND Not Premium (Standard Task)
            is_standard = model.NewBoolVar(f"std_{tid}_{i_idx}")
            model.AddBoolAnd([assigned_to_me, is_prem.Not()]).OnlyEnforceIf(is_standard)
            model.AddBoolOr([assigned_to_me.Not(), is_prem]).OnlyEnforceIf(is_standard.Not())
            
            # Reify: Assigned AND Premium (Premium Task)
            is_premium_task = model.NewBoolVar(f"prem_{tid}_{i_idx}")
            model.AddBoolAnd([assigned_to_me, is_prem]).OnlyEnforceIf(is_premium_task)
            model.AddBoolOr([assigned_to_me.Not(), is_prem.Not()]).OnlyEnforceIf(is_premium_task.Not())

            my_standard_minutes_vars.append(is_standard * dur)
            my_premium_minutes_vars.append(is_premium_task * dur)
            my_total_minutes_vars.append(assigned_to_me * dur)
        
        # --- 1. Total Load Calculation ---
        total_assigned_min = model.NewIntVar(0, 6000, f"tot_min_{i_idx}")
        model.Add(total_assigned_min == sum(my_total_minutes_vars))
        
        # --- 2. Standard Load Calculation ---
        standard_assigned_min = model.NewIntVar(0, 6000, f"std_min_{i_idx}")
        model.Add(standard_assigned_min == sum(my_standard_minutes_vars))

        # --- 3. Premium Load Calculation ---
        premium_assigned_min = model.NewIntVar(0, 6000, f"prem_min_{i_idx}")
        model.Add(premium_assigned_min == sum(my_premium_minutes_vars))
        
        # --- OBJECTIVE: VACUUM STRATEGY ---
        
        # A. Fill Regular Load (Linear Reward)
        # Reward Standard Minutes up to the Limit
        reg_filled = model.NewIntVar(0, reg_limit, f"reg_fill_{i_idx}")
        model.Add(reg_filled <= standard_assigned_min)
        objective_terms.append(reg_filled * STANDARD_LOAD_REWARD)
        
        # B. Penalize Premium Hours (Linear Penalty)
        # This acts as "Debt". Solver hates this.
        objective_terms.append(premium_assigned_min * -PREMIUM_LOAD_PENALTY)

        # C. Equalizer (Quadratic Penalty on TOTAL Load)
        # We square the TOTAL load. This is the main fairness driver.
        # It punishes having 20 hours (400 cost) much more than 15 hours (225 cost).
        sq_total = model.NewIntVar(0, 6000 * 6000, f"sq_tot_{i_idx}")
        model.AddMultiplicationEquality(sq_total, [total_assigned_min, total_assigned_min])
        objective_terms.append(sq_total * -TOTAL_LOAD_SQUARED_PENALTY)

        # D. Underload Penalty
        underload = model.NewIntVar(0, reg_limit, f"under_{i_idx}")
        model.Add(underload == reg_limit - reg_filled)
        objective_terms.append(underload * -UNDERLOAD_PENALTY)
        
        # 4. Daily Spread (Linear)
        for d in range(7):
            d_durations = []
            for t in tasks:
                tid = t["task_id"]
                # Reify (Assigned AND Day==d)
                is_on_day = model.NewBoolVar(f"{tid}_is_day_{d}_{i_idx}")
                model.Add(task_vars[tid]["day"] == d).OnlyEnforceIf(is_on_day)
                model.Add(task_vars[tid]["day"] != d).OnlyEnforceIf(is_on_day.Not())

                active_on_day = model.NewBoolVar(f"act_{tid}_{i_idx}_{d}")
                model.AddBoolAnd([assigned_instr[(tid, i_idx)], is_on_day]).OnlyEnforceIf(active_on_day)
                model.AddBoolOr([assigned_instr[(tid, i_idx)].Not(), is_on_day.Not()]).OnlyEnforceIf(active_on_day.Not())

                d_durations.append(active_on_day * t["dur"])
            
            day_sum = model.NewIntVar(0, 1440, f"ds_{i_idx}_{d}")
            model.Add(day_sum == sum(d_durations))
            
            excess = model.NewIntVar(0, 1440, f"exc_{i_idx}_{d}")
            model.Add(excess >= day_sum - MAX_DESIRED_DAILY_MIN)
            objective_terms.append(excess * -DAILY_SPREAD_PENALTY)

    # --- Other Costs ---
    for t in tasks:
        tid = t["task_id"]
        # Matches
        for i_idx, instr_id in enumerate(instructors):
            matches = data.get("matches", {})
            score = 0
            if t["section"] in matches:
                for (cand_id, sc) in matches[t["section"]]:
                    if cand_id == instr_id:
                        score = sc
                        break
            if score > 0:
                objective_terms.append(assigned_instr[(tid, i_idx)] * int(score * MATCH_WEIGHT_SCALE))

        # TBA
        is_tba = model.NewBoolVar(f"{tid}_tba")
        model.Add(task_vars[tid]["room"] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(task_vars[tid]["room"] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        objective_terms.append(is_tba * -TBA_PENALTY_NORMAL)
        objective_terms.append(is_tba.Not() * REAL_ROOM_REWARD)
        
    # --- Solve ---
    model.Maximize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True

    print(f"[Solver] Starting solve (Time limit: {time_limit_seconds}s)...")
    status = solver.Solve(model)
    print(f"[Solver] Status: {solver.StatusName(status)}")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        section_objs = {s.sectionId: s for s in Section.objects.filter(sectionId__in=sections)}
        instructor_objs = {i.instructorId: i for i in Instructor.objects.filter(instructorId__in=instructors)}
        room_objs = {r.roomId: r for r in Room.objects.filter(roomId__in=[r for r in rooms if r != "TBA"])}
        
        schedules_to_create = []
        for t in tasks:
            tid = t["task_id"]
            i_idx = solver.Value(task_vars[tid]["instr"])
            r_idx = solver.Value(task_vars[tid]["room"])
            start_val = solver.Value(task_vars[tid]["start"])
            
            day_idx = start_val // 1440
            min_day = start_val % 1440
            h = min_day // 60
            m = min_day % 60
            
            naive_dt = datetime(2000, 1, 1, h, m)
            try:
                aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            except:
                aware_dt = naive_dt
            
            end_dt = aware_dt + timedelta(minutes=t["dur"])
            
            instructor = instructor_objs.get(instructors[i_idx])
            room = None if r_idx == TBA_ROOM_IDX else room_objs.get(rooms[r_idx])
            
            is_ot = False 
            if day_idx >= 5 or min_day >= 17*60: is_ot = True

            schedules_to_create.append(Schedule(
                subject=section_objs[t["section"]].subject,
                instructor=instructor,
                section=section_objs[t["section"]],
                room=room,
                semester=semester,
                dayOfWeek=DAYS[day_idx],
                startTime=aware_dt.time(),
                endTime=end_dt.time(),
                scheduleType=t["kind"],
                isOvertime=is_ot,
                status='active'
            ))

        with transaction.atomic():
            Schedule.objects.filter(semester=semester, status='active').update(status='archived')
            Schedule.objects.bulk_create(schedules_to_create)
            print(f"[Solver] Saved {len(schedules_to_create)} schedules.")
        return schedules_to_create

    else:
        print("[Solver] No solution found.")
        return []

def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=300)