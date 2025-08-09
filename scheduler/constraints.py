# scheduler/constraints.py
# Unified constraint application for CP-SAT scheduling

from ortools.sat.python import cp_model
from itertools import combinations


def apply_constraints(model, sections, section_day, section_start, section_instructor, data, section_room=None):
    """
    Applies all constraints to `model`.

    Expected:
      - sections: iterable/list of section_ids
      - section_day: dict[section_id] -> IntVar (0..4)
      - section_start: dict[section_id] -> IntVar (minutes since midnight)
      - section_instructor: dict[section_id] -> IntVar (0..num_instructors-1)
      - data: output of get_solver_data(semester)
      - section_room (optional): dict[section_id] -> IntVar (0..num_rooms or TBA index)
    """

    instructor_idx = data["instructor_index"]
    availability = data["instructor_availability"]
    loads = data["instructor_loads"]
    section_hours = data["section_hours"]
    gened_sections = data.get("gened_sections", set())
    matches = data.get("matches", {})
    lecture_lab_pairs = data.get("lecture_lab_pairs", [])

    # Precompute durations (minutes)
    section_duration_min = {sid: int(sum(section_hours.get(sid, (0, 0)))) for sid in sections}

    # --- Assigned boolean mapping (reified) ---
    # assigned_bool[(sid, iidx)] == True iff section sid is assigned to instructor index iidx
    assigned_bool = {}
    for sid in sections:
        dur = section_duration_min[sid]
        for instr_id, iidx in instructor_idx.items():
            b = model.NewBoolVar(f"s{sid}_is_i{iidx}")
            model.Add(section_instructor[sid] == iidx).OnlyEnforceIf(b)
            model.Add(section_instructor[sid] != iidx).OnlyEnforceIf(b.Not())
            assigned_bool[(sid, iidx)] = b

            avail = availability.get(instr_id, {})
            if not avail:
                # No availability info, assume full availability Mon-Fri 8:00-20:00
                valid_block_bools = []
                for day in range(5):  # Monday=0 to Friday=4
                    blk_start = 8 * 60
                    blk_end = 20 * 60
                    latest_start = blk_end - dur
                    block_ok = model.NewBoolVar(f"s{sid}_i{iidx}_d{day}_fullavail")
                    model.Add(section_day[sid] == day).OnlyEnforceIf(block_ok)
                    model.Add(section_day[sid] != day).OnlyEnforceIf(block_ok.Not())
                    model.Add(section_start[sid] >= blk_start).OnlyEnforceIf(block_ok)
                    model.Add(section_start[sid] <= latest_start).OnlyEnforceIf(block_ok)
                    valid_block_bools.append(block_ok)
                model.AddBoolOr(valid_block_bools).OnlyEnforceIf(b)
            else:
                # Limited availability - collect valid blocks
                valid_block_bools = []
                for day, blocks in avail.items():
                    for (blk_start, blk_end) in blocks:
                        latest_start = blk_end - dur
                        if latest_start < blk_start:
                            continue
                        block_ok = model.NewBoolVar(f"s{sid}_i{iidx}_d{day}_b{blk_start}-{blk_end}")
                        model.Add(section_day[sid] == day).OnlyEnforceIf(block_ok)
                        model.Add(section_day[sid] != day).OnlyEnforceIf(block_ok.Not())
                        model.Add(section_start[sid] >= blk_start).OnlyEnforceIf(block_ok)
                        model.Add(section_start[sid] <= latest_start).OnlyEnforceIf(block_ok)
                        valid_block_bools.append(block_ok)
                if not valid_block_bools:
                    # No valid availability blocks => cannot assign instructor to this section
                    model.Add(b == 0)
                else:
                    model.AddBoolOr(valid_block_bools).OnlyEnforceIf(b)



    # --- No-overlap per instructor (reified) ---
    # For each pair of sections and each instructor: if both assigned to same instructor,
    # then day different OR non-overlapping times.
    for sid1, sid2 in combinations(sections, 2):
        dur1 = section_duration_min[sid1]
        dur2 = section_duration_min[sid2]
        end1 = model.NewIntVar(0, 24 * 60, f"end_s{sid1}")
        end2 = model.NewIntVar(0, 24 * 60, f"end_s{sid2}")
        model.Add(end1 == section_start[sid1] + dur1)
        model.Add(end2 == section_start[sid2] + dur2)

        for instr_id, iidx in instructor_idx.items():
            b1 = assigned_bool[(sid1, iidx)]
            b2 = assigned_bool[(sid2, iidx)]
            both_assigned = model.NewBoolVar(f"both_s{sid1}_s{sid2}_i{iidx}")
            model.AddBoolAnd([b1, b2]).OnlyEnforceIf(both_assigned)
            model.AddBoolOr([b1.Not(), b2.Not()]).OnlyEnforceIf(both_assigned.Not())

            day_diff = model.NewBoolVar(f"daydiff_s{sid1}_s{sid2}_i{iidx}")
            model.Add(section_day[sid1] != section_day[sid2]).OnlyEnforceIf(day_diff)
            model.Add(section_day[sid1] == section_day[sid2]).OnlyEnforceIf(day_diff.Not())

            sid1_after_sid2 = model.NewBoolVar(f"s{sid1}_after_s{sid2}_i{iidx}")
            sid2_after_sid1 = model.NewBoolVar(f"s{sid2}_after_s{sid1}_i{iidx}")
            model.Add(section_start[sid1] >= end2).OnlyEnforceIf(sid1_after_sid2)
            model.Add(section_start[sid1] < end2).OnlyEnforceIf(sid1_after_sid2.Not())
            model.Add(section_start[sid2] >= end1).OnlyEnforceIf(sid2_after_sid1)
            model.Add(section_start[sid2] < end1).OnlyEnforceIf(sid2_after_sid1.Not())

            model.AddBoolOr([day_diff, sid1_after_sid2, sid2_after_sid1]).OnlyEnforceIf(both_assigned)

    # --- Instructor load limits ---
    for instr_id, iidx in instructor_idx.items():
        terms = []
        for sid in sections:
            b = assigned_bool[(sid, iidx)]
            dur = section_duration_min[sid]
            terms.append(b * dur)
        if not terms:
            continue
        total = model.NewIntVar(0, 10000, f"total_load_i{iidx}")
        model.Add(total == sum(terms))
        normal_h, overload_h = loads.get(instr_id, (0, 0))
        model.Add(total <= (normal_h + overload_h) * 60)

    # --- Time bounds (global) ---
    for sid in sections:
        dur = section_duration_min[sid]
        model.Add(section_start[sid] >= 8 * 60)
        model.Add(section_start[sid] <= 20 * 60 - dur)

    # --- Lecture/Lab pairing: same instructor, different days ---
    for pair in lecture_lab_pairs:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            lec_id, lab_id = pair
        elif isinstance(pair, dict):
            lec_id = pair.get("lecture_section_id") or pair.get("lecture_id") or pair["lecture_var"]["section_id"]
            lab_id = pair.get("lab_section_id") or pair.get("lab_id") or pair["lab_var"]["section_id"]
        else:
            continue

        # same instructor
        model.Add(section_instructor[lec_id] == section_instructor[lab_id])
        # different days
        model.Add(section_day[lec_id] != section_day[lab_id])

        # safety: ensure they don't overlap if somehow same day allowed later
        lec_end = model.NewIntVar(0, 24 * 60, f"end_lec_{lec_id}")
        lab_end = model.NewIntVar(0, 24 * 60, f"end_lab_{lab_id}")
        model.Add(lec_end == section_start[lec_id] + section_duration_min[lec_id])
        model.Add(lab_end == section_start[lab_id] + section_duration_min[lab_id])

        same_day = model.NewBoolVar(f"same_day_lec_{lec_id}_lab_{lab_id}")
        model.Add(section_day[lec_id] == section_day[lab_id]).OnlyEnforceIf(same_day)
        model.Add(section_day[lec_id] != section_day[lab_id]).OnlyEnforceIf(same_day.Not())

        lec_after_lab = model.NewBoolVar(f"lec_after_lab_{lec_id}_{lab_id}")
        lab_after_lec = model.NewBoolVar(f"lab_after_lec_{lec_id}_{lab_id}")
        model.Add(section_start[lec_id] >= lab_end).OnlyEnforceIf(lec_after_lab)
        model.Add(section_start[lab_id] >= lec_end).OnlyEnforceIf(lab_after_lec)
        model.AddBoolOr([lec_after_lab, lab_after_lec]).OnlyEnforceIf(same_day)

    # --- GenEd priority (reified) ---
    for sid in sections:
        if sid in gened_sections:
            continue
        for instr_id, _ in matches.get(sid, []):
            if instr_id not in instructor_idx:
                continue
            iidx = instructor_idx[instr_id]
            b_s = assigned_bool[(sid, iidx)]
            for gs in gened_sections:
                if instr_id not in [iid for (iid, _) in matches.get(gs, [])]:
                    continue
                b_g = assigned_bool[(gs, iidx)]
                both = model.NewBoolVar(f"ged_both_s{sid}_g{gs}_i{iidx}")
                model.AddBoolAnd([b_s, b_g]).OnlyEnforceIf(both)
                model.AddBoolOr([b_s.Not(), b_g.Not()]).OnlyEnforceIf(both.Not())
                model.Add(section_day[gs] <= section_day[sid]).OnlyEnforceIf(both)

    # --- Room constraints ---
    if section_room is not None:
        rooms = data.get("rooms", [])
        room_index = data.get("room_index", {})
        subjects = data.get("subjects", {})
        section_subjects = data.get("section_subjects", {})
        rooms_qs = data.get("rooms_qs", [])
        section_enrollment = data.get("section_enrollment", {})

        no_room_idx = len(rooms)  # Index representing no room assigned ("TBA")

        for sid in sections:
            room_var = section_room[sid]
            subj_id = section_subjects.get(sid)
            subj_meta = subjects.get(subj_id, {})
            enrollment = section_enrollment.get(sid, 0)

            # Room capacity constraints: assigned room capacity >= enrollment OR room is TBA (no room)
            for r_idx, room_id in enumerate(rooms):
                room_obj = next((r for r in rooms_qs if r.roomId == room_id), None)
                if room_obj is None:
                    continue

                b_room_assigned = model.NewBoolVar(f"room_s{sid}_is_{r_idx}")
                model.Add(room_var == r_idx).OnlyEnforceIf(b_room_assigned)
                model.Add(room_var != r_idx).OnlyEnforceIf(b_room_assigned.Not())

                # Capacity must be >= enrollment for assigned rooms
                model.Add(room_obj.capacity >= enrollment).OnlyEnforceIf(b_room_assigned)

                # If subject has type, enforce room.type == subject.type
                subj_type = subj_meta.get("type", None)
                if subj_type is not None and hasattr(room_obj, "type"):
                    model.Add(room_obj.type == subj_type).OnlyEnforceIf(b_room_assigned)

            # No direct constraint needed for TBA room (no_room_idx), allowed fallback


from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def checkInstructorAvailability(instructor, offering):
    """
    Quick availability check used before assigning an instructor to a SubjectOffering.
    - `instructor`: Instructor instance (core.models.Instructor)
    - `offering`: SubjectOffering instance (scheduling.models.SubjectOffering)

    This function is intentionally permissive by default (returns True) so it
    won't block assignments when availability model differs from expectations.
    Replace or tighten with your real InstructorAvailability model logic.

    Behavior implemented:
      - If there's a model named InstructorAvailability in core.models,
        tries to ensure instructor has at least one availability block (otherwise False).
      - If we cannot inspect availability, returns True.
    """
    try:
        # Lazy import to avoid circular imports
        from core.models import InstructorAvailability
    except Exception:
        # If we don't have the model available (or import fails), assume okay.
        logger.debug("InstructorAvailability model not found — skipping detailed availability check.")
        return True

    try:
        # Query availability blocks for this instructor (expected fields: day, start_min, end_min)
        blocks = InstructorAvailability.objects.filter(instructor=instructor)
        if not blocks.exists():
            # No availability defined -> assume instructor is not available (safer)
            logger.debug(f"No availability blocks found for instructor {getattr(instructor, 'instructorId', instructor)}")
            return False

        # If the offering already has a preferred timeslot stored (rare), we could check that.
        # But usually SubjectOffering doesn't have a concrete time yet; so presence of blocks is enough.
        return True
    except Exception as ex:
        logger.exception("Error checking InstructorAvailability — defaulting to True.")
        return True


def checkInstructorLoad(instructor, offering):
    """
    Simple teaching-load check before assigning an instructor to a SubjectOffering.
    - calculates the instructor's current assigned hours from Schedule (if present)
    - adds `offering` subject hours (using expected field names)
    - returns True if total would be <= normal + overload hours

    Expected instructor fields (fallback values used if missing):
      - instructor.designation.normalLoad (hours) OR instructor.normalLoad
      - instructor.academicAttainment.overLoad (hours) OR instructor.overLoad
    Expected offering/subject fields:
      - offering.subject.durationMinutes (lecture total minutes)
      - offering.subject.labDurationMinutes (lab minutes) if any
    """
    try:
        from scheduling.models import Schedule
    except Exception:
        Schedule = None

    # Get instructor limits (use sensible defaults if unknown)
    try:
        normal = getattr(instructor, "normalLoad", None)
        if normal is None and getattr(instructor, "designation", None):
            normal = getattr(instructor.designation, "normalLoad", None)
        if normal is None:
            normal = 12  # fallback hours

        overload = getattr(instructor, "overLoad", None)
        if overload is None and getattr(instructor, "academicAttainment", None):
            overload = getattr(instructor.academicAttainment, "overLoad", None)
        if overload is None:
            overload = 3  # fallback hours
    except Exception:
        normal, overload = 12, 3

    # current load (in minutes)
    current_minutes = 0
    if Schedule is not None:
        try:
            # Sum schedule durations for this instructor (all semesters) — conservative approach
            qs = Schedule.objects.filter(instructor=instructor)
            for s in qs:
                try:
                    if getattr(s, "startTime", None) and getattr(s, "endTime", None):
                        delta = (s.endTime - s.startTime)
                        # delta could be datetime.timedelta or number of minutes; handle both
                        if isinstance(delta, timedelta):
                            current_minutes += int(delta.total_seconds() // 60)
                        else:
                            # fallback: assume integer minutes
                            current_minutes += int(delta)
                except Exception:
                    continue
        except Exception:
            logger.exception("Error computing current Schedule load — assuming 0 current minutes.")
            current_minutes = 0

    # offering minutes
    offering_minutes = 0
    try:
        subj = getattr(offering, "subject", None)
        if subj is not None:
            offering_minutes = int(getattr(subj, "durationMinutes", 0))
            if getattr(subj, "hasLab", False):
                offering_minutes += int(getattr(subj, "labDurationMinutes", 0) or 0)
    except Exception:
        offering_minutes = 0

    total_after = current_minutes + offering_minutes
    allowed_minutes = int((int(normal) + int(overload)) * 60)

    if total_after <= allowed_minutes:
        return True

    logger.debug(
        f"Instructor {getattr(instructor, 'instructorId', instructor)} would be overloaded: "
        f"{total_after/60:.2f}h > allowed {allowed_minutes/60:.2f}h"
    )
    return False

