# scheduler/data_extractors.py
from collections import defaultdict
from scheduling.models import Subject, Section, Room
from core.models import Instructor
from aimatching.models import InstructorSubjectMatch


def get_solver_data(semester):
    """
    Updated 'get_solver_data' (aligned with new solver rules).
    This is optional, meant for diagnostics or pre-solver inspection.

    Returns dict with:
      - instructors_qs, sections_qs, rooms_qs (querysets)
      - instructor_index / section_index / room_index
      - instructor_caps: {instr_id: {normal_limit_min, overload_limit_min, employment, has_designation}}
      - subjects: {subject_id: {durationMinutes, labDurationMinutes, has_lab, ...}}
      - section_hours: {section_id: {lecture_min, lab_min, units}}
      - matches: {section_id: [(instr_id, score), ...]}
      - lecture_lab_pairs: [(lecture_section_id, lab_section_id)]
    """

    # -------------------- Instructors --------------------
    instructors_qs = [
        i for i in Instructor.objects.all()
        if (i.employmentType or "").lower() != "on-leave/retired"
    ]
    instructors = [i.instructorId for i in instructors_qs]
    instructor_index = {i.instructorId: idx for idx, i in enumerate(instructors_qs)}

    # -------------------- Sections --------------------
    sections_qs = list(Section.objects.filter(semester=semester).select_related("subject"))
    sections = [s.sectionId for s in sections_qs]
    section_index = {s.sectionId: idx for idx, s in enumerate(sections_qs)}

    # -------------------- Subjects --------------------
    subject_ids = {s.subject_id for s in sections_qs}
    subjects_qs = Subject.objects.filter(subjectId__in=subject_ids).select_related("curriculum")
    subjects = {}
    for subj in subjects_qs:
        subjects[subj.subjectId] = {
            "durationMinutes": int(getattr(subj, "durationMinutes", 0) or 0),
            "labDurationMinutes": int(getattr(subj, "labDurationMinutes", 0) or 0),
            "has_lab": bool(getattr(subj, "hasLab", False)),
            "is_gened": bool(
                getattr(subj.curriculum, "is_gened", False)
                if getattr(subj, "curriculum", None) else False
            ),
            "is_priority_for_rooms": bool(getattr(subj, "isPriorityForRooms", False)),
            "units": int(getattr(subj, "units", 0) or 0),
            "type": getattr(subj, "type", None),
        }

    # -------------------- Section Hours --------------------
    section_hours = {}
    for s in sections_qs:
        subj = subjects.get(s.subject_id, {})
        section_hours[s.sectionId] = {
            "lecture_min": subj.get("durationMinutes", 0),
            "lab_min": subj.get("labDurationMinutes", 0) if subj.get("has_lab") else 0,
            "units": subj.get("units", 0),
        }

    # -------------------- Instructor Load Caps --------------------
    def resolve_caps(i):
        emp = (i.employmentType or "permanent").lower()
        has_designation = bool(i.designation)
        # Determine normal instruction hours
        normal_h = None
        if i.designation and getattr(i.designation, "instructionHours", None):
            normal_h = i.designation.instructionHours
        elif i.rank and getattr(i.rank, "instructionHours", None):
            normal_h = i.rank.instructionHours
        else:
            normal_h = 18
        # Overload cap
        if emp == "permanent":
            overload_h = 9 if has_designation else 12
        else:
            overload_h = 10_000  # effectively unlimited
        return {
            "normal_limit_min": int(normal_h * 60),
            "overload_limit_min": int(overload_h * 60),
            "employment": emp,
            "has_designation": has_designation,
        }

    instructor_caps = {i.instructorId: resolve_caps(i) for i in instructors_qs}

    # -------------------- Matches --------------------
    match_qs = InstructorSubjectMatch.objects.filter(
        subject_id__in=subject_ids
    ).select_related("instructor", "subject")

    subj_to_section_ids = defaultdict(list)
    for s in sections_qs:
        subj_to_section_ids[s.subject_id].append(s.sectionId)

    matches = defaultdict(list)
    for m in match_qs:
        instr_id = m.instructor.instructorId
        subj_id = m.subject.subjectId
        score = getattr(m, "confidenceScore", None)
        if score is None:
            score = 1.0 if getattr(m, "isRecommended", False) else 0.0
        for sec_id in subj_to_section_ids.get(subj_id, []):
            matches[sec_id].append((instr_id, float(score)))

    # -------------------- Lecture/Lab Pairs --------------------
    lecture_lab_pairs = []
    subj_to_sections = defaultdict(list)
    for s in sections_qs:
        subj_to_sections[s.subject_id].append(s.sectionId)

    for subj_id, sec_ids in subj_to_sections.items():
        subj_meta = subjects.get(subj_id, {})
        if not subj_meta.get("has_lab", False):
            continue
        lectures = [sid for sid in sec_ids if section_hours[sid]["lecture_min"] > 0]
        labs = [sid for sid in sec_ids if section_hours[sid]["lab_min"] > 0]
        for lec in lectures:
            for lab in labs:
                if lec != lab:
                    lecture_lab_pairs.append((lec, lab))

    # -------------------- Rooms --------------------
    rooms_qs = list(Room.objects.filter(isActive=True))
    rooms = [r.roomId for r in rooms_qs]
    room_index = {r.roomId: idx for idx, r in enumerate(rooms_qs)}

    # -------------------- Output --------------------
    return {
        "instructors_qs": instructors_qs,
        "sections_qs": sections_qs,
        "rooms_qs": rooms_qs,
        "instructor_index": instructor_index,
        "section_index": section_index,
        "room_index": room_index,
        "instructor_caps": instructor_caps,
        "subjects": subjects,
        "section_hours": section_hours,
        "matches": dict(matches),
        "lecture_lab_pairs": lecture_lab_pairs,
        "rooms": rooms,
    }
