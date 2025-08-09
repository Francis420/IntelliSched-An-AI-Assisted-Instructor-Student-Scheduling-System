from ortools.sat.python import cp_model
from scheduler.data_extractors import get_solver_data
from scheduler import constraints


def solve_schedule_from_data(data, time_limit_seconds=30):
    """
    Same solver logic as before but accepts a prepared `data` dict (from get_solver_data
    or a hand-constructed dict). Returns the same schedule list.
    """
    model = cp_model.CpModel()

    instructors = data["instructors"]
    sections = data["sections"]
    rooms = data.get("rooms", [])
    room_index = data.get("room_index", {})

    instructor_index = data["instructor_index"]
    section_index = data["section_index"]

    num_instructors = len(instructors)
    num_rooms = len(rooms)
    no_room_idx = num_rooms  # extra index for "TBA"

    if num_instructors == 0 or len(sections) == 0:
        return []

    time_blocks = list(range(8 * 60, 20 * 60 + 1, 15))

    # Decision variables
    section_day = {}
    section_start = {}
    section_instructor = {}
    section_room = {}

    for sid in sections:
        section_day[sid] = model.NewIntVar(0, 4, f"day_s{sid}")
        section_start[sid] = model.NewIntVarFromDomain(cp_model.Domain.FromValues(time_blocks), f"start_s{sid}")
        section_instructor[sid] = model.NewIntVar(0, num_instructors - 1, f"instr_s{sid}")
        # Room variable includes actual rooms plus a TBA option (no_room_idx)
        section_room[sid] = model.NewIntVar(0, no_room_idx, f"room_s{sid}")

    constraints.apply_constraints(model, sections, section_day, section_start, section_instructor, data, section_room)

    # Objective: maximize instructor matching and priority subjects assigned rooms
    match_terms = []
    room_priority_terms = []

    for sid in sections:
        for instr_id, score in data.get("matches", {}).get(sid, []):
            if instr_id not in instructor_index:
                continue
            iidx = instructor_index[instr_id]
            b = model.NewBoolVar(f"assign_s{sid}_i{iidx}")
            model.Add(section_instructor[sid] == iidx).OnlyEnforceIf(b)
            model.Add(section_instructor[sid] != iidx).OnlyEnforceIf(b.Not())
            match_terms.append(b * int(round(score * 1000)))

        subj = data["subjects"].get(data["section_subjects"][sid], {})
        if subj.get("is_priority_for_rooms", False) or subj.get("isPriorityForRooms", False):
            room_assigned = model.NewBoolVar(f"room_assigned_s{sid}")
            model.Add(section_room[sid] != no_room_idx).OnlyEnforceIf(room_assigned)
            model.Add(section_room[sid] == no_room_idx).OnlyEnforceIf(room_assigned.Not())
            room_priority_terms.append(room_assigned * 100000)

    if match_terms or room_priority_terms:
        model.Maximize(sum(match_terms) + sum(room_priority_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    schedule = []
    for sid in sections:
        assigned_idx = solver.Value(section_instructor[sid])
        assigned_instructor_id = instructors[assigned_idx]
        assigned_room_idx = solver.Value(section_room[sid])
        assigned_room_id = None
        if assigned_room_idx != no_room_idx:
            assigned_room_id = rooms[assigned_room_idx]

        # Use integer minutes directly from data["section_hours"]
        duration_min = sum(data["section_hours"].get(sid, (0, 0)))

        schedule.append({
            "section_id": sid,
            "instructor_id": assigned_instructor_id,
            "room_id": assigned_room_id,
            "day": int(solver.Value(section_day[sid])),
            "start_minute": int(solver.Value(section_start[sid])),
            "duration_min": int(duration_min),
        })

    return schedule


def solve_schedule_for_semester(semester, time_limit_seconds=30):
    """
    Backwards-compatible wrapper for existing code: gathers data from DB then calls
    the `solve_schedule_from_data` function.
    """
    data = get_solver_data(semester)
    return solve_schedule_from_data(data, time_limit_seconds=time_limit_seconds)
