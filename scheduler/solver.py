# scheduler/solver.py  (REWRITE using OR-Tools interval variables)
import math
from collections import defaultdict
from itertools import combinations

from ortools.sat.python import cp_model
from django.db import transaction
from datetime import datetime, timedelta

from scheduling.models import (
    Section, Semester, Schedule, Room, GenEdSchedule
)
from core.models import Instructor
from scheduler.data_extractors import get_solver_data

# -------------------- Configuration --------------------
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
INTERVAL_MINUTES = 30  # granularity used by timeslot generator in data_extractors
WEEK_MINUTES = 7 * 24 * 60

# -------------------- Helper: create timeslot metadata --------------------
# We'll reconstruct the same TIMESLOTS logic as before, but produce
# a mapping: slot_idx -> (day_index, minute_of_day, minute_of_week)
def generate_timeslot_meta():
    timeslots = []
    slot_meta = []  # list of tuples: (slot_label, day_idx, minute_of_day, minute_of_week)
    slot_index = 0

    # Match previous generator ranges
    MORNING_RANGE = (8, 12)          # 08:00 - 11:30 slots (skip 12:00)
    AFTERNOON_RANGE = (13, 17)       # 13:00 - 16:30 slots
    OVERLOAD_RANGE_WEEKDAYS = (17.5, 20)  # 17:30 - 20:00 (note fractional)
    OVERLOAD_RANGE_WEEKENDS = [(8, 12), (13, 20)]

    for day_idx, day in enumerate(DAYS):
        if day_idx <= 4:  # weekdays
            # Morning
            for hour in range(MORNING_RANGE[0], MORNING_RANGE[1]):
                for minute in (0, 30):
                    # skip 12:00 - 13:00 handled by ranges
                    if hour == 12:
                        continue
                    minute_of_day = hour * 60 + minute
                    start = f"{hour:02d}:{minute:02d}"
                    label = f"{day} {start}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    timeslots.append(label)
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    slot_index += 1

            # Afternoon
            for hour in range(AFTERNOON_RANGE[0], AFTERNOON_RANGE[1]):
                for minute in (0, 30):
                    minute_of_day = hour * 60 + minute
                    start = f"{hour:02d}:{minute:02d}"
                    label = f"{day} {start}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    timeslots.append(label)
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    slot_index += 1

            # Overload (5:30pm - 8:00pm)
            hour = int(OVERLOAD_RANGE_WEEKDAYS[0])
            minute = 30
            while hour + minute / 60 < OVERLOAD_RANGE_WEEKDAYS[1] - 1e-9:
                minute_of_day = hour * 60 + minute
                start = f"{hour:02d}:{minute:02d}"
                label = f"{day} {start}"
                minute_of_week = day_idx * 1440 + minute_of_day
                timeslots.append(label)
                slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                minute += INTERVAL_MINUTES
                if minute == 60:
                    minute = 0
                    hour += 1
                slot_index += 1

        else:  # weekend
            for (start_h, end_h) in OVERLOAD_RANGE_WEEKENDS:
                hour = int(start_h)
                minute = 0
                while hour + minute / 60 < end_h - 1e-9:
                    minute_of_day = hour * 60 + minute
                    start = f"{hour:02d}:{minute:02d}"
                    label = f"{day} {start}"
                    minute_of_week = day_idx * 1440 + minute_of_day
                    timeslots.append(label)
                    slot_meta.append((label, day_idx, minute_of_day, minute_of_week))
                    minute += INTERVAL_MINUTES
                    if minute == 60:
                        minute = 0
                        hour += 1
                    slot_index += 1

    return timeslots, slot_meta

TIMESLOTS, SLOT_META = generate_timeslot_meta()
SLOT_INDEX = {label: idx for idx, (label, *_ ) in enumerate(SLOT_META)}
NUM_SLOTS = len(TIMESLOTS)
# helpful maps
SLOT_TO_DAY = {i: meta[1] for i, meta in enumerate(SLOT_META)}
SLOT_TO_MINUTE_OF_DAY = {i: meta[2] for i, meta in enumerate(SLOT_META)}
SLOT_TO_GLOBAL_MIN = {i: meta[3] for i, meta in enumerate(SLOT_META)}


# ----------------- Main scheduling function -----------------
def solve_schedule_for_semester(semester=None, time_limit_seconds=600):
    # Resolve semester
    if semester is None:
        semester = Semester.objects.order_by('-createdAt').first()
        if not semester:
            print("[Solver] No semesters found in the DB — cannot proceed.")
            return []
    elif isinstance(semester, int):
        semester = Semester.objects.get(pk=semester)

    print(f"[Solver] Semester: {semester}")

    # Archive old active schedules (pre-emptive)
    Schedule.objects.filter(semester=semester, status='active').update(status='archived')

    # Build CP-SAT model
    model = cp_model.CpModel()

    data = get_solver_data(semester)

    sections = list(data["sections"])
    rooms = list(data["rooms"])
    instructors = list(data["instructors"])

    num_rooms = len(rooms)
    num_instructors = len(instructors)
    TBA_ROOM_IDX = data.get("TBA_ROOM_IDX", num_rooms - 1)

    # Per-section constants
    section_duration_minutes = {}
    for s in sections:
        dur = data["section_hours"][s]["lecture_min"] + data["section_hours"][s]["lab_min"]
        # if dur == 0 fallback to 30 to avoid zero-length intervals (should be validated upstream)
        section_duration_minutes[s] = max(0, int(dur))

    # Decision variables
    section_slot = {s: model.NewIntVar(0, NUM_SLOTS - 1, f"slot_{s}") for s in sections}
    section_start_min = {s: model.NewIntVar(0, WEEK_MINUTES - 1, f"start_min_{s}") for s in sections}
    section_end_min = {s: model.NewIntVar(0, WEEK_MINUTES - 1, f"end_min_{s}") for s in sections}
    section_instructor = {s: model.NewIntVar(0, max(0, num_instructors - 1), f"instr_{s}") for s in sections}
    section_room = {s: model.NewIntVar(0, max(0, num_rooms - 1), f"room_{s}") for s in sections}
    section_day = {s: model.NewIntVar(0, 6, f"day_{s}") for s in sections}

    # Link slot <-> start_min <-> day via allowed assignments
    # For every slot index we have a global minute-of-week and day.
    allowed_slot_start_pairs = [(slot_idx, SLOT_TO_GLOBAL_MIN[slot_idx]) for slot_idx in range(NUM_SLOTS)]
    allowed_slot_day_pairs = [(slot_idx, SLOT_TO_DAY[slot_idx]) for slot_idx in range(NUM_SLOTS)]

    for s in sections:
        # require the (slot, start_min) pair to match slot metadata
        model.AddAllowedAssignments([section_slot[s], section_start_min[s]], allowed_slot_start_pairs)
        # require (slot, day) to match
        model.AddAllowedAssignments([section_slot[s], section_day[s]], allowed_slot_day_pairs)

        dur = section_duration_minutes[s]
        # end = start + duration
        model.Add(section_end_min[s] == section_start_min[s] + dur)

        # Bound start/end to avoid week overflow (end must be within week)
        model.Add(section_start_min[s] >= 0)
        model.Add(section_end_min[s] <= WEEK_MINUTES)

    # Optional intervals per (section, instructor) and per (section, room)
    # We'll create assigned booleans for each combination and optional intervals to feed NoOverlap
    assigned_instr = {}
    instr_intervals = {instr_id: [] for instr_id in range(num_instructors)}
    for s in sections:
        dur = section_duration_minutes[s]
        for i_idx in range(num_instructors):
            b = model.NewBoolVar(f"assign_sec{s}_instr{i_idx}")
            assigned_instr[(s, i_idx)] = b
            # link boolean to equality of section_instructor
            # model.Add(section_instructor == i_idx).OnlyEnforceIf(b)
            # model.Add(section_instructor != i_idx).OnlyEnforceIf(b.Not())
            # Above pattern causes a lot of linear constraints; instead use half-reified pattern:
            model.Add(section_instructor[s] == i_idx).OnlyEnforceIf(b)
            model.Add(section_instructor[s] != i_idx).OnlyEnforceIf(b.Not())

            if dur > 0:
                iv = model.NewOptionalIntervalVar(section_start_min[s], dur, section_end_min[s], b,
                                                  f"iv_sec{s}_instr{i_idx}")
                instr_intervals[i_idx].append(iv)

    # NoOverlap per instructor
    for i_idx, intervals in instr_intervals.items():
        if intervals:
            model.AddNoOverlap(intervals)

    # Rooms: create optional intervals for real rooms only (exclude TBA from overlap)
    assigned_room = {}
    room_intervals = defaultdict(list)
    for s in sections:
        dur = section_duration_minutes[s]
        for r_idx, r_id in enumerate(rooms):
            b = model.NewBoolVar(f"assign_sec{s}_room{r_idx}")
            assigned_room[(s, r_idx)] = b
            model.Add(section_room[s] == r_idx).OnlyEnforceIf(b)
            model.Add(section_room[s] != r_idx).OnlyEnforceIf(b.Not())

            # Only create NoOverlap entries for real rooms (not TBA)
            if r_idx != TBA_ROOM_IDX and dur > 0:
                iv = model.NewOptionalIntervalVar(section_start_min[s], dur, section_end_min[s], b,
                                                  f"iv_sec{s}_room{r_idx}")
                room_intervals[r_idx].append(iv)

    for r_idx, intervals in room_intervals.items():
        if intervals:
            model.AddNoOverlap(intervals)

    # Lecture/Lab pairing: same instructor, different day
    for lec_sec, lab_sec in data["lecture_lab_pairs"]:
        if lec_sec not in sections or lab_sec not in sections:
            continue
        model.Add(section_instructor[lec_sec] == section_instructor[lab_sec])
        model.Add(section_day[lec_sec] != section_day[lab_sec])

    # GenEd blocks: convert to minute-of-week fixed intervals and forbid overlap
    # For each gened block we enforce for each section: day != g_day OR end <= g_start OR start >= g_end
    for g_day, g_start_min, g_end_min in data.get("gened_blocks", []):
        g_start_global = g_day * 1440 + g_start_min
        g_end_global = g_day * 1440 + g_end_min
        for s in sections:
            # create reified comparisons
            cond_day_not = model.NewBoolVar(f"sec{s}_notday_{g_day}")
            model.Add(section_day[s] != g_day).OnlyEnforceIf(cond_day_not)
            model.Add(section_day[s] == g_day).OnlyEnforceIf(cond_day_not.Not())

            cond_before = model.NewBoolVar(f"sec{s}_before_{g_day}")
            model.Add(section_end_min[s] <= g_start_global).OnlyEnforceIf(cond_before)
            model.Add(section_end_min[s] > g_start_global).OnlyEnforceIf(cond_before.Not())

            cond_after = model.NewBoolVar(f"sec{s}_after_{g_day}")
            model.Add(section_start_min[s] >= g_end_global).OnlyEnforceIf(cond_after)
            model.Add(section_start_min[s] < g_end_global).OnlyEnforceIf(cond_after.Not())

            # At least one of the three must hold
            model.AddBoolOr([cond_day_not, cond_before, cond_after])

    # Instructor load caps and overload calculation
    instructor_caps = data["instructor_caps"]
    # Create total minutes var per instructor (indexed by instructorId string)
    instr_total_min = {}
    instr_overload = {}
    overload_penalty_terms = []

    # Build linear expressions for total minutes as sum(assign_sec_i * duration)
    for i_idx, instr_id in enumerate(instructors):
        total_min = model.NewIntVar(0, WEEK_MINUTES * 10, f"total_min_instr{i_idx}")
        instr_total_min[instr_id] = total_min

        # sum assigned * duration
        assigned_terms = []
        for s in sections:
            dur = section_duration_minutes[s]
            b = assigned_instr[(s, i_idx)]
            if dur > 0:
                # linear term handled by Add(total == sum(...))
                assigned_terms.append((b, dur))
        if assigned_terms:
            # build sum via linear expression: total_min == sum(b * dur)
            model.Add(total_min == sum([b * dur for (b, dur) in assigned_terms]))
        else:
            model.Add(total_min == 0)

        # overload var: overload = max(0, total_min - normal_limit)
        caps = instructor_caps.get(instr_id, {})
        normal_limit = caps.get("normal_limit_min", 40 * 60)
        overload_limit = caps.get("overload_limit_min", 0)

        ov = model.NewIntVar(0, max(0, overload_limit), f"overload_instr{i_idx}")
        instr_overload[instr_id] = ov

        # Enforce ov >= total - normal_limit  and ov >= 0; also ov <= overload_limit
        # Note: CP-SAT requires linear constraints; this is standard modeling of max(0,x)
        model.Add(total_min - normal_limit <= ov)
        model.Add(ov >= 0)
        model.Add(ov <= overload_limit)

        # Penalty weight for overload (tunable)
        overload_penalty_terms.append(ov * 5)  # 5 points penalty per minute of overload (scale as needed)

    # Objective construction: maximize matches, minimize penalties (we'll maximize reward - penalties)
    objective_terms = []

    # Instructor match rewards
    matches = data.get("matches", {})
    instructor_index_map = data.get("instructor_index", {})

    for sec_id, match_list in matches.items():
        if sec_id not in sections:
            continue
        for instr_id, score in match_list:
            if instr_id not in instructor_index_map:
                continue
            i_idx = instructor_index_map[instr_id]
            b = assigned_instr[(sec_id, i_idx)]
            weight = int(round(score * 100))
            if weight != 0:
                objective_terms.append(b * weight)

    # TBA penalty: if section assigned to TBA room, penalize
    tba_penalty_terms = []
    for s in sections:
        is_tba = model.NewBoolVar(f"is_tba_sec{s}")
        model.Add(section_room[s] == TBA_ROOM_IDX).OnlyEnforceIf(is_tba)
        model.Add(section_room[s] != TBA_ROOM_IDX).OnlyEnforceIf(is_tba.Not())
        # Penalty weight (tunable)
        tba_penalty_terms.append(is_tba * 50)

    # Combine overload penalties
    objective_terms.extend([-term for term in overload_penalty_terms])  # negative because we maximize overall
    objective_terms.extend([-term for term in tba_penalty_terms])

    # Reward real room assignments (small reward) - encourage real room usage
    # (we'll reward section_room != TBA)
    for s in sections:
        is_real_room = model.NewBoolVar(f"is_real_room_sec{s}")
        model.Add(section_room[s] != TBA_ROOM_IDX).OnlyEnforceIf(is_real_room)
        model.Add(section_room[s] == TBA_ROOM_IDX).OnlyEnforceIf(is_real_room.Not())
        objective_terms.append(is_real_room * 10)

    # Final: maximize sum(objective_terms)
    # Because objective_terms may mix positive and negative, use model.Maximize
    model.Maximize(sum(objective_terms))

    # Solver params
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    solver.parameters.log_search_progress = True

    # Export debug model if needed
    try:
        model.ExportToFile("debug_model_interval.pbtxt")
        print("[Solver] Exported debug_model_interval.pbtxt")
    except Exception:
        pass

    print(f"[Solver] Starting solve: {len(sections)} sections, {num_instructors} instructors, {num_rooms} rooms, {NUM_SLOTS} slots.")
    status = solver.Solve(model)
    print(f"[Solver] Status: {solver.StatusName(status)}")
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"[Solver] Objective value: {solver.ObjectiveValue()}")

        # Build schedule objects to save
        section_objs = {s.sectionId: s for s in Section.objects.filter(sectionId__in=sections)}
        instructor_objs = {i.instructorId: i for i in Instructor.objects.filter(instructorId__in=instructors)}
        room_objs = {r.roomId: r for r in Room.objects.filter(roomId__in=[r for r in rooms if r != "TBA"])}

        weekday_names = DAYS

        schedules_to_create = []

        for s in sections:
            sec_obj = section_objs[s]
            instr_idx = solver.Value(section_instructor[s])
            room_idx = solver.Value(section_room[s])
            start_min = solver.Value(section_start_min[s])
            end_min = solver.Value(section_end_min[s])

            # Derive day and time-of-day
            day_idx = start_min // 1440
            minute_of_day = start_min % 1440
            hour = minute_of_day // 60
            minute = minute_of_day % 60

            start_time = (datetime(2000, 1, 1, hour, minute)).time()

            # duration: use lecture or lab depending on section type
            if sec_obj.hasLab:
                dur_min = data["section_hours"][s]["lab_min"]
            else:
                dur_min = data["section_hours"][s]["lecture_min"]
            end_dt = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=dur_min)
            end_time = end_dt.time()

            instructor = instructor_objs.get(instructors[instr_idx])
            room = None if room_idx == TBA_ROOM_IDX else room_objs.get(rooms[room_idx])

            schedule_type = "lab" if sec_obj.hasLab else "lecture"
            is_overtime = False  # optional: can determine by checking minute_of_day ranges

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
