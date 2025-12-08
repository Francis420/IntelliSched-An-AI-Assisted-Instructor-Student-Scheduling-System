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

# Weights & Rewards
MATCH_WEIGHT_SCALE = 100
REAL_ROOM_REWARD = 10          

# Penalties & Tuning
TBA_PENALTY_NORMAL = 50        
TBA_PENALTY_PRIORITY = 100000  

WEEKEND_TIME_PENALTY_PER_MINUTE = 5000 
WEEKDAY_EVENING_PENALTY_PER_MINUTE = 100

# --- TUNING FOR BALANCE (The "Fix") ---

# 1. SATURATION REWARD (Maximize Normal Load)
# High reward: Solver will fight to reach exactly 18.0 hours normal load.
NORMAL_LOAD_REWARD_PER_MIN = 500            

# 2. FAIRNESS PENALTY (Balance the Overload)
# Quadratic (Squaring): Punishes the "11.5 vs 3.5" gap severely.
OVERLOAD_FAIRNESS_PENALTY = 50000 

# 3. DAILY SPREAD PENALTY (Linear)
# We reverted this to Linear (Simple) to fix the "UNKNOWN" timeout error.
DAILY_SPREAD_PENALTY = 50
MAX_DESIRED_DAILY_MIN = 360 # 6 hours

# 4. Base Overload Cost
GLOBAL_OVERLOAD_COST_PER_MIN = 10         

# -------------------- Timeslot metadata --------------------
def generate_timeslot_meta():
    slot_meta = []
    MORNING_RANGE = (8, 12)
    AFTERNOON_RANGE = (13, 17)
    OVERLOAD_RANGE_WEEKDAYS = (17, 20) 
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
            
            # Overload
            start_h, end_h = OVERLOAD_RANGE_WEEKDAYS
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
            return []
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Semester: {semester}")
    Schedule.objects.filter(semester=semester, status='active').update(status='archived')

    data = get_solver_data(semester)
    sections = list(data["sections"])
    rooms = list(data["rooms"])
    instructors = list(data["instructors"])
    instructor_caps = data["instructor_caps"]
    
    room_types = data.get("room_types", {i: 'lecture' for i in range(len(rooms))}) 
    room_capacities = data.get("room_capacities", {i: 999 for i in range(len(rooms))}) 
    section_priority_map = data.get("section_priority_map", {}) 
    section_num_students = data.get("section_num_students", {})
    
    num_rooms = len(rooms)
    num_instructors = len(instructors)
    
    if "TBA_ROOM_IDX" in data:
        TBA_ROOM_IDX = data["TBA_ROOM_IDX"]
    else:
        TBA_ROOM_IDX = num_rooms - 1 

    # --- Robust Room Domains ---
    lecture_base_indices = {TBA_ROOM_IDX}
    lab_base_indices = {TBA_ROOM_IDX}

    for i in range(num_rooms):
        rtype = room_types.get(i, 'lecture')
        if rtype in ('lecture', 'universal'):
            lecture_base_indices.add(i)
        if rtype in ('laboratory', 'universal'):
            lab_base_indices.add(i)

    model = cp_model.CpModel()

    # --- Task Generation ---
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

    # --- Variables ---
    task_vars = {} 
    assigned_instr = defaultdict(list)
    assigned_room = defaultdict(list)
    instr_intervals = defaultdict(list)
    room_intervals = defaultdict(list) 

    allowed_slots_for_duration = {}
    def get_allowed_slots(dur):
        if dur not in allowed_slots_for_duration:
            lst = []
            for i in range(NUM_SLOTS):
                day = SLOT_META[i][1]
                minute_of_day = SLOT_META[i][2]
                end = minute_of_day + dur
                
                if end > 20*60: continue
                if not (end <= 12*60 or minute_of_day >= 13*60): continue 
                if minute_of_day < 8*60 or (12*60 <= minute_of_day < 13*60): continue
                
                lst.append(i)
            allowed_slots_for_duration[dur] = lst
        return allowed_slots_for_duration[dur]

    latest_end_by_day = {d: 20*60 for d in range(7)}

    for t in tasks:
        tid = t["task_id"]
        dur = int(t["dur"])
        allowed_slots = get_allowed_slots(dur)

        if not allowed_slots:
            print(f"[Solver] ERROR: Task {tid} fits NO time slots! Skipping.")
            continue 

        # Time
        slot_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_slots), f"slot_{tid}")
        start_var = model.NewIntVar(0, WEEK_MINUTES - 1, f"start_{tid}")
        end_var = model.NewIntVar(0, WEEK_MINUTES, f"end_{tid}")
        day_var = model.NewIntVar(0, 6, f"day_{tid}")

        model.AddAllowedAssignments([slot_var, start_var], [(i, SLOT_TO_GLOBAL_MIN[i]) for i in allowed_slots])
        model.AddAllowedAssignments([slot_var, day_var], [(i, SLOT_TO_DAY[i]) for i in allowed_slots])
        model.Add(end_var == start_var + dur)

        for d in range(7):
            cond = model.NewBoolVar(f"{tid}_day{d}")
            model.Add(day_var == d).OnlyEnforceIf(cond)
            model.Add(day_var != d).OnlyEnforceIf(cond.Not())
            allowed_end = d*1440 + latest_end_by_day[d]
            model.Add(end_var <= allowed_end).OnlyEnforceIf(cond)

        # No Straddle
        is_weekday = model.NewBoolVar(f"{tid}_is_weekday")
        model.Add(day_var <= 4).OnlyEnforceIf(is_weekday)
        model.Add(day_var >= 5).OnlyEnforceIf(is_weekday.Not())

        start_mod = model.NewIntVar(0, 1440, f"{tid}_start_mod")
        model.AddModuloEquality(start_mod, start_var, 1440)
        end_mod = model.NewIntVar(0, 1440, f"{tid}_end_mod")
        model.AddModuloEquality(end_mod, end_var, 1440)

        ends_early = model.NewBoolVar(f"{tid}_ends_early")
        model.Add(end_mod <= 1020).OnlyEnforceIf(ends_early) 
        model.Add(end_mod > 1020).OnlyEnforceIf(ends_early.Not())
        starts_late = model.NewBoolVar(f"{tid}_starts_late")
        model.Add(start_mod >= 1020).OnlyEnforceIf(starts_late)
        model.Add(start_mod < 1020).OnlyEnforceIf(starts_late.Not())

        model.AddBoolOr([ends_early, starts_late]).OnlyEnforceIf(is_weekday)

        # Room (Capacity + Type)
        base_indices = lab_base_indices if t["kind"] == "lab" else lecture_base_indices
        required_students = section_num_students.get(t["section"], 0)
        valid_indices = []
        for r_idx in base_indices:
            if r_idx == TBA_ROOM_IDX:
                valid_indices.append(r_idx)
                continue
            cap = room_capacities.get(r_idx, 0)
            if cap >= required_students:
                valid_indices.append(r_idx)
        if not valid_indices: valid_indices = [TBA_ROOM_IDX]

        room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(sorted(valid_indices)), f"room_{tid}")
        
        # Instructor
        instr_var = model.NewIntVar(0, max(0, num_instructors - 1), f"instr_{tid}")

        task_vars[tid] = {
            "start": start_var, "end": end_var, "day": day_var, 
            "room": room_var, "instr": instr_var, "dur": dur,
            "kind": t["kind"], "section": t["section"]
        }

        # Intervals
        for i_idx in range(num_instructors):
            b = model.NewBoolVar(f"assign_{tid}_instr{i_idx}")
            assigned_instr[(tid, i_idx)] = b 
            model.Add(instr_var == i_idx).OnlyEnforceIf(b)
            model.Add(instr_var != i_idx).OnlyEnforceIf(b.Not())
            iv = model.NewOptionalIntervalVar(start_var, dur, end_var, b, f"iv_i_{tid}")
            instr_intervals[i_idx].append(iv)
        model.Add(sum(assigned_instr[(tid, i)] for i in range(num_instructors)) == 1)

        for r_idx in range(num_rooms):
            b = model.NewBoolVar(f"assign_{tid}_room{r_idx}")
            assigned_room[(tid, r_idx)] = b
            model.Add(room_var == r_idx).OnlyEnforceIf(b)
            model.Add(room_var != r_idx).OnlyEnforceIf(b.Not())
            if r_idx != TBA_ROOM_IDX:
                iv = model.NewOptionalIntervalVar(start_var, dur, end_var, b, f"iv_r_{tid}")
                room_intervals[r_idx].append(iv)
        model.Add(sum(assigned_room[(tid, r)] for r in range(num_rooms)) == 1)

        # Weekend Lockout
        is_weekend_check = model.NewBoolVar(f"{tid}_check_weekend")
        model.Add(day_var >= 5).OnlyEnforceIf(is_weekend_check)
        model.Add(day_var < 5).OnlyEnforceIf(is_weekend_check.Not())
        model.Add(room_var == TBA_ROOM_IDX).OnlyEnforceIf(is_weekend_check)

    # Overlaps
    for i_idx, ivs in instr_intervals.items():
        if ivs: model.AddNoOverlap(ivs)
    for r_idx, ivs in room_intervals.items():
        if ivs: model.AddNoOverlap(ivs)

    # Links
    section_to_tasks = defaultdict(list)
    for t in tasks:
        if t["task_id"] in task_vars:
            section_to_tasks[t["section"]].append(t)

    for sec, tlist in section_to_tasks.items():
        lects = [t for t in tlist if t["kind"] == "lecture"]
        labs = [t for t in tlist if t["kind"] == "lab"]
        for l_task in labs:
            for lect_task in lects:
                model.Add(task_vars[l_task["task_id"]]["instr"] == task_vars[lect_task["task_id"]]["instr"])
        
        split_lects = [t for t in lects if "_LECT_A" in t["task_id"] or "_LECT_B" in t["task_id"]]
        if len(split_lects) == 2:
            lA, lB = split_lects
            vA = task_vars[lA["task_id"]]
            vB = task_vars[lB["task_id"]]
            model.Add(vA["instr"] == vB["instr"])
            durA = lA["dur"]
            min_gap = durA + 30
            diff = model.NewIntVar(0, WEEK_MINUTES, f"gap_{sec}")
            model.AddAbsEquality(diff, vA["start"] - vB["start"])
            model.Add(diff >= min_gap)

    # GenEd
    for g_day, g_start, g_end in data.get("gened_blocks", []):
        g_s_glob = g_day * 1440 + g_start
        g_e_glob = g_day * 1440 + g_end
        for tid, tv in task_vars.items():
            diff_day = model.NewBoolVar(f"gen_diff_{tid}")
            model.Add(tv["day"] != g_day).OnlyEnforceIf(diff_day)
            model.Add(tv["day"] == g_day).OnlyEnforceIf(diff_day.Not())
            before = model.NewBoolVar(f"gen_before_{tid}")
            model.Add(tv["end"] <= g_s_glob).OnlyEnforceIf(before)
            model.Add(tv["end"] > g_s_glob).OnlyEnforceIf(before.Not())
            after = model.NewBoolVar(f"gen_after_{tid}")
            model.Add(tv["start"] >= g_e_glob).OnlyEnforceIf(after)
            model.Add(tv["start"] < g_e_glob).OnlyEnforceIf(after.Not())
            model.AddBoolOr([diff_day, before, after])

    # -------------------- Load Calculation & Objectives --------------------
    objective_terms = []
    
    # Precompute Status
    task_is_overtime = {} 
    for tid, tv in task_vars.items():
        is_weekend = model.NewBoolVar(f"{tid}_is_we")
        model.Add(tv["day"] >= 5).OnlyEnforceIf(is_weekend)
        model.Add(tv["day"] < 5).OnlyEnforceIf(is_weekend.Not())
        
        start_mod = model.NewIntVar(0, 1440, f"{tid}_st_mod_ot")
        model.AddModuloEquality(start_mod, tv["start"], 1440)
        is_evening = model.NewBoolVar(f"{tid}_is_eve")
        model.Add(start_mod >= 1020).OnlyEnforceIf(is_evening)
        model.Add(start_mod < 1020).OnlyEnforceIf(is_evening.Not())
        
        is_ot = model.NewBoolVar(f"{tid}_is_ot")
        model.AddBoolOr([is_weekend, is_evening]).OnlyEnforceIf(is_ot)
        model.AddBoolAnd([is_weekend.Not(), is_evening.Not()]).OnlyEnforceIf(is_ot.Not())
        task_is_overtime[tid] = is_ot

    # Instructor Totals
    for i_idx, instr_id in enumerate(instructors):
        caps = instructor_caps.get(instr_id, {})
        n_lim = caps.get("normal_limit_min", 40 * 60)
        o_lim = caps.get("overload_limit_min", 0)

        tot_norm = model.NewIntVar(0, n_lim, f"load_n_{i_idx}")
        tot_over = model.NewIntVar(0, o_lim, f"load_o_{i_idx}")
        
        norm_terms = []
        over_terms = []
        
        for t in tasks:
            tid = t["task_id"]
            if tid not in task_vars: continue 
            dur = t["dur"]
            assigned = assigned_instr[(tid, i_idx)]
            is_ot = task_is_overtime[tid]
            
            as_ot = model.NewBoolVar(f"as_ot_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot]).OnlyEnforceIf(as_ot)
            model.AddBoolOr([assigned.Not(), is_ot.Not()]).OnlyEnforceIf(as_ot.Not())
            
            as_nm = model.NewBoolVar(f"as_nm_{tid}_{i_idx}")
            model.AddBoolAnd([assigned, is_ot.Not()]).OnlyEnforceIf(as_nm)
            model.AddBoolOr([assigned.Not(), is_ot]).OnlyEnforceIf(as_nm.Not())
            
            over_terms.append(as_ot * dur)
            norm_terms.append(as_nm * dur)
        
        model.Add(tot_norm == sum(norm_terms))
        model.Add(tot_over == sum(over_terms))
        
        # --- BALANCED OBJECTIVES ---
        
        # 1. Base Cost (Keep Low)
        objective_terms.append(tot_over * -GLOBAL_OVERLOAD_COST_PER_MIN)

        # 2. Saturation Reward (High) - Fill to 18.0 hrs
        objective_terms.append(tot_norm * NORMAL_LOAD_REWARD_PER_MIN)

        # 3. Overload Fairness (Quadratic) - Balance the overtime
        # We KEEP this one quadratic because it's the most critical for your specific request
        sq_over = model.NewIntVar(0, o_lim * o_lim, f"sq_over_{i_idx}")
        model.AddMultiplicationEquality(sq_over, [tot_over, tot_over])
        objective_terms.append(sq_over * -OVERLOAD_FAIRNESS_PENALTY)
        
        # 4. Daily Spreading (Simplified to Linear)
        # Replaces the complex daily squares that caused UNKNOWN
        for d in range(7):
            d_terms = []
            for t in tasks:
                tid = t["task_id"]
                if tid not in task_vars: continue
                dur = t["dur"]
                assigned = assigned_instr[(tid, i_idx)]
                day_match = model.NewBoolVar(f"{tid}_on_{d}")
                model.Add(task_vars[tid]["day"] == d).OnlyEnforceIf(day_match)
                model.Add(task_vars[tid]["day"] != d).OnlyEnforceIf(day_match.Not())
                active = model.NewBoolVar(f"{tid}_act_{d}_{i_idx}")
                model.AddBoolAnd([assigned, day_match]).OnlyEnforceIf(active)
                model.AddBoolOr([assigned.Not(), day_match.Not()]).OnlyEnforceIf(active.Not())
                d_terms.append(active * dur)
            
            daily_sum = model.NewIntVar(0, 1440, f"ds_{i_idx}_{d}")
            model.Add(daily_sum == sum(d_terms))
            
            # Linear Soft Limit (Fast)
            excess = model.NewIntVar(0, 1440, f"exc_{i_idx}_{d}")
            # excess >= daily_sum - 360
            model.Add(excess >= daily_sum - MAX_DESIRED_DAILY_MIN)
            objective_terms.append(excess * -DAILY_SPREAD_PENALTY)

    # --- Other Objectives ---
    matches = data.get("matches", {})
    i_map = data.get("instructor_index", {})
    for sec_id, m_list in matches.items():
        sec_tasks = section_to_tasks.get(sec_id, [])
        for (i_id, score) in m_list:
            if i_id not in i_map: continue
            idx = i_map[i_id]
            w = int(round(score * MATCH_WEIGHT_SCALE))
            for t in sec_tasks:
                if t["task_id"] not in task_vars: continue
                b = assigned_instr[(t["task_id"], idx)]
                if w != 0: objective_terms.append(b * w)

    for t in tasks:
        tid = t["task_id"]
        if tid not in task_vars: continue
        is_priority = section_priority_map.get(t["section"], False)
        room_var = task_vars[tid]["room"]
        
        is_tba = model.NewBoolVar(f"{tid}_is_tba")
        model.Add(room_var == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(room_var != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        
        if is_priority:
            objective_terms.append(is_tba * -TBA_PENALTY_PRIORITY)
        else:
            objective_terms.append(is_tba * -TBA_PENALTY_NORMAL)
        objective_terms.append(is_tba.Not() * REAL_ROOM_REWARD)

    for t in tasks:
        tid = t["task_id"]
        if tid not in task_vars: continue
        is_we = model.NewBoolVar(f"pen_we_{tid}")
        model.Add(task_vars[tid]["day"] >= 5).OnlyEnforceIf(is_we)
        model.Add(task_vars[tid]["day"] < 5).OnlyEnforceIf(is_we.Not())
        objective_terms.append(is_we * t["dur"] * -WEEKEND_TIME_PENALTY_PER_MINUTE)
        
        start_mod = model.NewIntVar(0, 1440, f"pen_st_{tid}")
        model.AddModuloEquality(start_mod, task_vars[tid]["start"], 1440)
        is_eve = model.NewBoolVar(f"pen_eve_{tid}")
        model.Add(start_mod >= 1020).OnlyEnforceIf(is_eve)
        
        is_wd = model.NewBoolVar(f"pen_wd_{tid}")
        model.Add(task_vars[tid]["day"] <= 4).OnlyEnforceIf(is_wd)
        is_wd_eve = model.NewBoolVar(f"pen_wd_eve_{tid}")
        model.AddBoolAnd([is_wd, is_eve]).OnlyEnforceIf(is_wd_eve)
        objective_terms.append(is_wd_eve * t["dur"] * -WEEKDAY_EVENING_PENALTY_PER_MINUTE)

    # --- Solve ---
    model.Maximize(sum(objective_terms))
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
            if tid not in task_vars: continue
            sec_obj = section_objs[t["section"]]
            i_idx = solver.Value(task_vars[tid]["instr"])
            r_idx = solver.Value(task_vars[tid]["room"])
            start_val = solver.Value(task_vars[tid]["start"])
            
            day_idx = start_val // 1440
            min_day = start_val % 1440
            h = min_day // 60
            m = min_day % 60
            
            start_time = datetime(2000, 1, 1, h, m).time()
            end_dt = datetime(2000, 1, 1, h, m) + timedelta(minutes=t["dur"])
            end_time = end_dt.time()

            instructor = instructor_objs.get(instructors[i_idx])
            room = None if r_idx == TBA_ROOM_IDX else room_objs.get(rooms[r_idx])
            
            is_weekend_bool = (day_idx >= 5)
            is_evening_bool = (min_day >= 1020)
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