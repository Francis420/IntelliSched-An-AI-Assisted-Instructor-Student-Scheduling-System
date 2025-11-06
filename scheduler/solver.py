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
from datetime import time, timedelta, datetime
from scheduler.data_extractors import get_solver_data



# -------------------- Configuration --------------------
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Time ranges in hours (24h format)
MORNING_RANGE = (8, 12)          # 8:00am – 12:00nn
AFTERNOON_RANGE = (13, 17)       # 1:00pm – 5:00pm
OVERLOAD_RANGE_WEEKDAYS = (17.5, 20)  # 5:30pm – 8:00pm
OVERLOAD_RANGE_WEEKENDS = [(8, 12), (13, 20)]  # 8am–12nn, 1pm–8pm

INTERVAL_MINUTES = 30

# --------------------Time Slot Generator --------------------
def generate_timeslots():
    timeslots = []
    window_map = {}  # {index: "morning"/"afternoon"/"overload"}

    slot_index = 0
    for day in DAYS:
        # Weekday (Mon–Fri)
        if day in DAYS[:5]:
            # Morning
            for hour in range(MORNING_RANGE[0], MORNING_RANGE[1]):
                for minute in (0, 30):
                    start = f"{hour:02d}:{minute:02d}"
                    end_time = datetime.strptime(start, "%H:%M") + timedelta(minutes=INTERVAL_MINUTES)
                    end = end_time.strftime("%H:%M")
                    timeslots.append(f"{day} {start}–{end}")
                    window_map[slot_index] = "morning"
                    slot_index += 1

            # Afternoon
            for hour in range(AFTERNOON_RANGE[0], AFTERNOON_RANGE[1]):
                for minute in (0, 30):
                    start = f"{hour:02d}:{minute:02d}"
                    end_time = datetime.strptime(start, "%H:%M") + timedelta(minutes=INTERVAL_MINUTES)
                    end = end_time.strftime("%H:%M")
                    timeslots.append(f"{day} {start}–{end}")
                    window_map[slot_index] = "afternoon"
                    slot_index += 1

            # Overload (5:30pm–8:00pm)
            hour = int(OVERLOAD_RANGE_WEEKDAYS[0])
            minute = 30
            while hour + minute / 60 < OVERLOAD_RANGE_WEEKDAYS[1]:
                start = f"{hour:02d}:{minute:02d}"
                end_time = datetime.strptime(start, "%H:%M") + timedelta(minutes=INTERVAL_MINUTES)
                end = end_time.strftime("%H:%M")
                timeslots.append(f"{day} {start}–{end}")
                window_map[slot_index] = "overload"

                minute += INTERVAL_MINUTES
                if minute == 60:
                    minute = 0
                    hour += 1
                slot_index += 1

        # Weekend (Sat–Sun)
        else:
            for (start_h, end_h) in OVERLOAD_RANGE_WEEKENDS:
                hour = int(start_h)
                minute = 0
                while hour + minute / 60 < end_h:
                    start = f"{hour:02d}:{minute:02d}"
                    end_time = datetime.strptime(start, "%H:%M") + timedelta(minutes=INTERVAL_MINUTES)
                    end = end_time.strftime("%H:%M")
                    timeslots.append(f"{day} {start}–{end}")
                    window_map[slot_index] = "overload"

                    minute += INTERVAL_MINUTES
                    if minute == 60:
                        minute = 0
                        hour += 1
                    slot_index += 1

    return timeslots, window_map


# -------------------- Build CP-SAT-friendly mappings --------------------
TIMESLOTS, WINDOW_MAP = generate_timeslots()
TIMESLOT_INDEX = {slot: idx for idx, slot in enumerate(TIMESLOTS)}

def window_name_for_slot(slot_index: int):
    """Returns 'morning', 'afternoon', or 'overload' for the given slot index."""
    return WINDOW_MAP.get(slot_index, None)


# ----------------- Main scheduling function -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=30, interval_minutes=30):

    # Resolve semester
    if semester is None:
        semester = Semester.objects.order_by('-createdAt').first()
        if not semester:
            print("[Solver] No semesters found in the DB — cannot proceed.")
            return []
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Semester: {semester}")


    # Archive old active schedules
    archived = Schedule.objects.filter(semester=semester, status='active').update(status='archived')
    print(f"[Solver] Archived {archived} old active schedules for semester {semester}")


    # -------------------- Build model --------------------
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    objective_terms = []

    # Decision variables
    section_day = {}         # Which day (Mon–Sun)
    section_slot = {}        # Which timeslot index
    section_room = {}        # Which room
    section_instructor = {}  # Which instructor

    from scheduler.data_extractors import get_solver_data


    data = get_solver_data(semester)

    sections = data["sections"] # Aliases from data
    rooms = data["rooms"]
    instructors = data["instructors"]
    timeslots = TIMESLOTS  # from your timeslot generator

    num_timeslots = len(timeslots)
    num_rooms = len(rooms)
    TBA_ROOM_IDX = data.get("TBA_ROOM_IDX", len(rooms) - 1)  # safe fallback
    num_instructors = len(instructors)

    # Build per-section variables
    for sec_id in sections:
        # Day: 0–6 (Mon–Sun)
        section_day[sec_id] = model.NewIntVar(0, 6, f"day_{sec_id}")

        # Timeslot: discrete 30-minute blocks
        section_slot[sec_id] = model.NewIntVar(0, num_timeslots - 1, f"slot_{sec_id}")

        # Room assignment (including optional TBA slot)
        section_room[sec_id] = model.NewIntVar(0, num_rooms - 1, f"room_{sec_id}")

        # Instructor assignment (index from data["instructor_index"])
        section_instructor[sec_id] = model.NewIntVar(0, num_instructors - 1, f"instr_{sec_id}")
    
    
    # Optional: helper dicts for readability
    vars_by_section = {
        "day": section_day,
        "slot": section_slot,
        "room": section_room,
        "instructor": section_instructor,
    }

    print(f"[Solver] Created {len(sections)} section variables "
        f"({num_instructors} instructors, {num_rooms} rooms, {num_timeslots} slots)")


    # Constraints

    # -------------------- Lecture/Lab pairing constraints --------------------
    for lec_sec, lab_sec in data["lecture_lab_pairs"]:
        # Same instructor for lecture and lab
        model.Add(section_instructor[lec_sec] == section_instructor[lab_sec])

        # Must be on different days
        model.Add(section_day[lec_sec] != section_day[lab_sec])

    

    # -------------------- GenEd blocking constraints --------------------
    for g_day, g_start_min, g_end_min in data.get("gened_blocks", []):
        for sec_id in sections:
            sec_minutes = data["section_hours"][sec_id]["lecture_min"] + data["section_hours"][sec_id]["lab_min"]
            slot_start_min = section_slot[sec_id] * INTERVAL_MINUTES
            slot_end_min = slot_start_min + sec_minutes

            model.AddBoolOr([
                section_day[sec_id] != g_day,
                slot_end_min <= g_start_min,
                slot_start_min >= g_end_min,
            ])


    # -------------------- Room-type + TBA fallback constraints --------------------
    room_types = data["room_types"]
    TBA_ROOM_IDX = data["TBA_ROOM_IDX"]

    # Map real rooms by type for efficient lookup
    rooms_by_type = {}
    for r_id, r_type in room_types.items():
        rooms_by_type.setdefault(r_type, []).append(data["room_index"][r_id])

    for sec_id in sections:
        sec = Section.objects.get(pk=sec_id)
        required_type = "laboratory" if sec.hasLab else "lecture"
        valid_room_idxs = rooms_by_type.get(required_type.lower(), [])

        if not valid_room_idxs:
            # No rooms of that type exist → force TBA
            model.Add(section_room[sec_id] == TBA_ROOM_IDX)
            continue

        # Constraint: Section can only use valid rooms *or* TBA
        allowed_rooms = valid_room_idxs + [TBA_ROOM_IDX]
        model.AddAllowedAssignments([section_room[sec_id]], [[r] for r in allowed_rooms])

        # Soft constraint: discourage using TBA unless necessary
        is_tba = model.NewBoolVar(f"is_tba_{sec_id}")
        model.Add(section_room[sec_id] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(section_room[sec_id] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())

        # Add small penalty to objective for using TBA
        objective_terms.append(is_tba * 20)  # adjust weight as needed


        # -------------------- Room Priority (Optional soft reward) --------------------
    for sec_id in sections:
        is_tba = model.NewBoolVar(f"is_tba_obj_{sec_id}")
        model.Add(section_room[sec_id] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(section_room[sec_id] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())

        # Reward having a *real* room instead of TBA
        objective_terms.append(is_tba.Not() * 20)  # adjust reward weight as needed


    # -------------------- Instructor Match Score (Soft Objective) --------------------
    matches = data["matches"]
    instructor_index = data["instructor_index"]

    for sec_id, match_list in matches.items():
        for instr_id, score in match_list:
            if instr_id not in instructor_index:
                continue
            i_idx = instructor_index[instr_id]
            matched = model.NewBoolVar(f"match_{sec_id}_i{i_idx}")
            model.Add(section_instructor[sec_id] == i_idx).OnlyEnforceIf(matched)
            model.Add(section_instructor[sec_id] != i_idx).OnlyEnforceIf(matched.Not())

            # Higher score = more preferred match → reward it
            weight = int(round(score * 100))  # scale for integer optimization
            objective_terms.append(matched * weight)


    is_tba_section = {}
    for sec_id in sections:
        is_tba = model.NewBoolVar(f"is_tba_{sec_id}")
        model.Add(section_room[sec_id] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(section_room[sec_id] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        is_tba_section[sec_id] = is_tba

    # -------------------- No-overlap Constraints --------------------
    # Enforces that no instructor or room handles overlapping sections on the same day.

    import math
    section_ids = list(sections)
    num_sections = len(section_ids)

    # Helper: duration in minutes (lecture + lab)
    section_duration = {
        s: data["section_hours"][s]["lecture_min"] + data["section_hours"][s]["lab_min"]
        for s in section_ids
    }

    for i1, i2 in combinations(section_ids, 2):
        dur1 = section_duration[i1]
        dur2 = section_duration[i2]
        if dur1 <= 0 or dur2 <= 0:
            continue  # skip invalid durations

        # Instructor overlap prevention
        same_instr = model.NewBoolVar(f"same_instr_{i1}_{i2}")
        model.Add(section_instructor[i1] == section_instructor[i2]).OnlyEnforceIf(same_instr)
        model.Add(section_instructor[i1] != section_instructor[i2]).OnlyEnforceIf(same_instr.Not())

        # Room overlap prevention
        same_room = model.NewBoolVar(f"same_room_{i1}_{i2}")
        model.Add(section_room[i1] == section_room[i2]).OnlyEnforceIf(same_room)
        model.Add(section_room[i1] != section_room[i2]).OnlyEnforceIf(same_room.Not())

        # Same day check
        same_day = model.NewBoolVar(f"same_day_{i1}_{i2}")
        model.Add(section_day[i1] == section_day[i2]).OnlyEnforceIf(same_day)
        model.Add(section_day[i1] != section_day[i2]).OnlyEnforceIf(same_day.Not())

        # Define interval overlap reified constraints (simplified no-overlap logic)
        i1_after_i2 = model.NewBoolVar(f"{i1}_after_{i2}")
        i2_after_i1 = model.NewBoolVar(f"{i2}_after_{i1}")

        model.Add(section_slot[i1] >= section_slot[i2] + math.ceil(dur2 / INTERVAL_MINUTES)).OnlyEnforceIf(i1_after_i2)
        model.Add(section_slot[i2] >= section_slot[i1] + math.ceil(dur1 / INTERVAL_MINUTES)).OnlyEnforceIf(i2_after_i1)

        # Combine conditions — no overlap if same instructor & same day
        model.AddBoolOr([
            same_instr.Not(),
            same_day.Not(),
            i1_after_i2,
            i2_after_i1
        ])

        # Combine conditions — no overlap if same room & same day
        model.AddBoolOr([
            same_room.Not(),
            same_day.Not(),
            i1_after_i2,
            i2_after_i1,
            is_tba_section[i1],
            is_tba_section[i2],
        ])

    
    # --- Instructor Load Tracking ---
    instructor_caps = data["instructor_caps"]
    section_hours = data["section_hours"]

    instructor_total_minutes = {i: model.NewIntVar(0, 99999, f"load_{i}") for i in instructors}

    for i_idx, instr_id in enumerate(instructors):
        normal_limit = instructor_caps[instr_id]["normal_limit_min"]
        overload_limit = instructor_caps[instr_id]["overload_limit_min"]

        load_terms = []
        for sec_id in sections:
            dur = section_hours[sec_id]["lecture_min"] + section_hours[sec_id]["lab_min"]
            # Binary var: section_instructor == i_idx
            assigned = model.NewBoolVar(f"assign_{sec_id}_i{i_idx}")
            model.Add(section_instructor[sec_id] == i_idx).OnlyEnforceIf(assigned)
            model.Add(section_instructor[sec_id] != i_idx).OnlyEnforceIf(assigned.Not())
            load_terms.append(assigned * dur)

        # Total minutes taught
        model.Add(instructor_total_minutes[instr_id] == sum(load_terms))

        # Hard limit (normal + overload)
        model.Add(instructor_total_minutes[instr_id] <= normal_limit + overload_limit)

    

    # -------------------- Balance Overload --------------------
    instructor_overload = {}
    for instr_id in instructors:
        caps = data["instructor_caps"][instr_id]
        normal_limit = caps["normal_limit_min"]
        overload_limit = caps["overload_limit_min"]

        total_min = instructor_total_minutes[instr_id]
        overload_min = model.NewIntVar(0, overload_limit, f"overload_min_{instr_id}")
        over_excess = model.NewIntVar(-99999, 99999, f"tmp_over_{instr_id}")

        model.Add(over_excess == total_min - normal_limit)
        model.AddMaxEquality(overload_min, [over_excess, model.NewConstant(0)])
        instructor_overload[instr_id] = overload_min

    num_instr = len(instructors)
    total_overload = model.NewIntVar(0, 999999, "total_overload")
    model.Add(total_overload == sum(instructor_overload.values()))

    avg_overload = model.NewIntVar(0, 999999, "avg_overload")
    model.AddDivisionEquality(avg_overload, total_overload, max(1, num_instr))

    for instr_id, ov in instructor_overload.items():
        diff = model.NewIntVar(-99999, 99999, f"diff_over_{instr_id}")
        dev = model.NewIntVar(0, 99999, f"dev_over_{instr_id}")
        model.Add(diff == ov - avg_overload)
        model.AddAbsEquality(dev, diff)
        objective_terms.append(dev * 2)  # penalty weight for imbalance

    # -------------------- Final Objective --------------------
    # By convention: maximize desirable traits, minimize penalties via negative weights
    model.Maximize(sum(objective_terms))


    # -------------------- Solve --------------------
    solver = cp_model.CpSolver()

    # --- Recommended parameters for scheduling ---
    solver.parameters.max_time_in_seconds = 600  # or adjust as needed
    solver.parameters.num_search_workers = 8      # parallel threads
    solver.parameters.random_seed = 42            # reproducibility
    solver.parameters.symmetry_level = 0          # avoid redundant exploration
    solver.parameters.log_search_progress = True  # useful for debugging
    solver.parameters.max_memory_in_mb = 8192     # optional, safety cap
    solver.parameters.cp_model_presolve = True
    # solver.parameters.use_optional_variables = True #skip variables/constraints that are not active
    solver.parameters.linearization_level = 0     # disables automatic linearization of some constraints into linear forms
    model.ExportToFile("debug_model.pbtxt")
    print("[Solver] Model exported to debug_model.pbtxt")

    print(
    f"[Solver] Starting solve: {len(sections)} sections, "
    f"{len(instructors)} instructors, {len(rooms)} rooms, "
    f"{len(TIMESLOTS)} timeslots."
    )

    status = solver.Solve(model)

    # Optional: print final solver status summary
    print(f"[Solver] Status: {solver.StatusName(status)}")
    print(f"[Solver] Objective value: {solver.ObjectiveValue() if status in [cp_model.OPTIMAL, cp_model.FEASIBLE] else 'N/A'}")
    print(f"[Solver] Wall time: {solver.WallTime():.2f} seconds")


    # ---------- Extract & Save schedule ----------
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("[Solver] Building Schedule objects from solution...")

        section_objs = {s.sectionId: s for s in Section.objects.filter(sectionId__in=data["sections"])}
        instructor_objs = {i.instructorId: i for i in Instructor.objects.filter(instructorId__in=data["instructors"])}
        room_objs = {r.roomId: r for r in Room.objects.filter(roomId__in=[r for r in data["rooms"] if r != "TBA"])}
        weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        schedules_to_create = []

        for sec_id in data["sections"]:
            sec_obj = section_objs[sec_id]
            instr_idx = solver.Value(section_instructor[sec_id])
            room_idx = solver.Value(section_room[sec_id])
            day_idx = solver.Value(section_day[sec_id])
            slot_idx = solver.Value(section_slot[sec_id])

            instructor = instructor_objs[data["instructors"][instr_idx]]
            room = None if room_idx == data["TBA_ROOM_IDX"] else room_objs[data["rooms"][room_idx]]

            # Parse timeslot label (e.g., "Mon 08:00–08:30")
            slot_label = TIMESLOTS[slot_idx]
            _, time_range = slot_label.split(" ")
            start_str, end_str = time_range.split("–")
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            schedule_type = "lab" if sec_obj.hasLab else "lecture"
            is_overtime = WINDOW_MAP[slot_idx] == "overload"

            schedules_to_create.append(Schedule(
                subject=sec_obj.subject,
                instructor=instructor,
                section=sec_obj,
                room=room,
                semester=semester,
                dayOfWeek=weekday[day_idx],
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
        print("[Solver] No feasible solution found; skipping schedule save.")
        return []




def generateSchedule():
    return solve_schedule_for_semester(time_limit_seconds=3600, interval_minutes=30)



if __name__ == "__main__":
    import django, os
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project_name.settings")
        django.setup()

    print("Running generateSchedule() from scheduler/solver.py...")
    try:
        schedules = generateSchedule()
        if schedules:
            print(f"Generated {len(schedules)} schedules.")
        else:
            print("No schedules generated.")
    except Exception as e:
        print(f"Solver failed: {e}")

