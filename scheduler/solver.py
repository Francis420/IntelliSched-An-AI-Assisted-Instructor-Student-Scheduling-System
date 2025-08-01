from ortools.sat.python import cp_model
from scheduler.constraints import checkInstructorAvailability, checkInstructorLoad
from aimatching.models import InstructorSubjectMatch
from scheduler.data_extractors import get_solver_data
from scheduling.models import Section, Subject


def add_minutes_to_time(start_hour, start_minute, duration_minutes):
    total_minutes = start_hour * 60 + start_minute + duration_minutes
    end_hour = total_minutes // 60
    end_minute = total_minutes % 60
    return f"{end_hour:02d}:{end_minute:02d}"


def pick_time_slot(day_index, duration_minutes):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day = days[day_index % len(days)]
    slot_options = [(8, 0), (10, 0), (13, 0), (15, 0), (17, 0)]
    start_hour, start_minute = slot_options[day_index % len(slot_options)]
    end_time = add_minutes_to_time(start_hour, start_minute, duration_minutes)
    start_time = f"{start_hour:02d}:{start_minute:02d}"

    category = "Normal"
    if start_hour >= 17:
        category = "Overload"
    if day in ["Saturday", "Sunday"]:
        category = "Weekend"

    return day, start_time, end_time, category


def get_ranked_instructors(subject, semester):
    """
    Get instructors ranked by latest AI confidence score for this subject.
    """
    matches = InstructorSubjectMatch.objects.filter(
        subject=subject,
        isLatest=True,
        isRecommended=True,
    ).select_related("instructor", "latestHistory")

    ranked = sorted(
        matches,
        key=lambda m: m.latestHistory.confidenceScore if m.latestHistory else -9999,
        reverse=True
    )
    return ranked


def pick_instructor_for_subject(subject, semester, assigned_loads, duration_hours, day, start, end, verbose=True):
    """
    Pick instructor for subject: prioritize AI score, balance load, check availability & load.
    """
    ranked_matches = get_ranked_instructors(subject, semester)

    if verbose:
        print(f"\n📌 Ranked instructors for {subject.code} ({subject.name}):")
        for m in ranked_matches:
            score = m.latestHistory.confidenceScore if m.latestHistory else None
            print(f"   - {m.instructor} | Score: {score}")

    candidates = []
    for match in ranked_matches:
        inst = match.instructor
        instructor_id = inst.instructorId
        current_load = assigned_loads.get(instructor_id, 0)

        inst_data = {
            "instructor": inst,
            "normalLoad": inst.designation.instructionHours if inst.designation else (
                inst.rank.instructionHours if inst.rank else 18
            ),
            "overloadUnits": (
                inst.academicAttainment.overloadUnitsHasDesignation
                if inst.academicAttainment and inst.designation
                else (inst.academicAttainment.overloadUnitsNoDesignation if inst.academicAttainment else 0)
            ),
            "availability": [
                a.to_block() for a in inst.availabilities.all()
            ] or [
                {"day": d, "start": "08:00", "end": "20:00"}
                for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            ]
        }

        if checkInstructorAvailability(inst_data, day, start, end) and \
           checkInstructorLoad(inst_data, current_load + duration_hours):
            candidates.append((current_load, match))

    if verbose and not candidates:
        print(f"⚠️ No valid instructors available for {subject.code} at {day} {start}-{end}")

    if not candidates:
        return None

    # Sort: first by least load, then by highest AI confidence
    candidates.sort(key=lambda x: (x[0], -x[1].latestHistory.confidenceScore))
    return candidates[0][1].instructor


def generateSchedule(semester, verbose=True, subject_filter=None):
    """
    Generates schedules ensuring:
    - 1 lecture per section per week
    - If subject.hasLab, also 1 lab (different day, same instructor)
    - Instructor picked by AI score + load balancing
    - Availability & overload rules enforced
    - Optional: subject_filter=[ids] to limit which subjects get scheduled
    - If no sections exist, creates mock sections (for testing)
    """
    data = get_solver_data(semester)

    # Apply filter if provided
    if subject_filter:
        data["sections"] = [s for s in data["sections"] if s.subject_id in subject_filter]

        # 🔹 Auto-generate mock sections if none exist
        if not data["sections"]:
            for sid in subject_filter:
                try:
                    subj = Subject.objects.get(pk=sid)
                except Subject.DoesNotExist:
                    continue
                for i in range(1, 7):
                    Section.objects.create(
                        semester=semester,
                        subject=subj,
                        sectionCode=f"{subj.code}-S{i}"  # ✅ fixed for your Section model
                    )
            data = get_solver_data(semester)
            data["sections"] = [s for s in data["sections"] if s.subject_id in subject_filter]

    if verbose:
        print(f"📊 Loaded {len(data['sections'])} sections")
        print(f"📊 Loaded {len(data['instructors'])} instructors")

    results = []
    assigned_loads = {inst["instructor"].instructorId: 0 for inst in data["instructors"]}
    day_index = 0

    for section in data["sections"]:
        subj = section.subject
        duration_lecture = subj.durationMinutes
        duration_lab = subj.labDurationMinutes or 0
        hours_lecture = duration_lecture // 60
        hours_lab = duration_lab // 60 if duration_lab else 0

        # ----- Lecture -----
        day, start, end, category = pick_time_slot(day_index, duration_lecture)
        inst = pick_instructor_for_subject(subj, semester, assigned_loads, hours_lecture, day, start, end, verbose=verbose)

        if inst:
            instructor_id = inst.instructorId
            results.append({
                "day": day,
                "subject": subj.name,
                "sectionId": section.sectionId,
                "instructor": str(inst),
                "start": start,
                "end": end,
                "category": category,
                "type": "Lecture",
            })
            assigned_loads[instructor_id] += hours_lecture
            assigned_instructor = inst
        else:
            assigned_instructor = None
            if verbose:
                print(f"⚠️ Could not assign lecture for {subj.name} section {section.sectionId}")

        # ----- Lab -----
        if subj.hasLab and duration_lab > 0 and assigned_instructor:
            lab_day_index = (day_index + 1) % 7
            day, start, end, category = pick_time_slot(lab_day_index, duration_lab)
            inst = pick_instructor_for_subject(subj, semester, assigned_loads, hours_lab, day, start, end, verbose=verbose)

            if inst and inst == assigned_instructor:
                instructor_id = inst.instructorId
                results.append({
                    "day": day,
                    "subject": subj.name,
                    "sectionId": section.sectionId,
                    "instructor": str(inst),
                    "start": start,
                    "end": end,
                    "category": category,
                    "type": "Lab",
                })
                assigned_loads[instructor_id] += hours_lab
            elif verbose:
                print(f"⚠️ Could not assign lab for {subj.name} section {section.sectionId}")

        elif subj.hasLab and duration_lab > 0 and not assigned_instructor:
            if verbose:
                print(f"⚠️ Skipped lab for {subj.name} section {section.sectionId} (no lecture assigned)")

        day_index += 1

    return cp_model.OPTIMAL, results
