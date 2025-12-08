# scheduler/data_extractors.py
from collections import defaultdict
from scheduling.models import Section, Room, GenEdSchedule
from core.models import Instructor
from aimatching.models import InstructorSubjectMatch


def get_solver_data(semester):
    # -------------------- Instructors --------------------
    instructors_qs = [
        i for i in Instructor.objects.all()
        if (i.employmentType or "").lower() != "on-leave/retired"
    ]
    instructors = [i.instructorId for i in instructors_qs]
    instructor_index = {i.instructorId: idx for idx, i in enumerate(instructors_qs)}

    # -------------------- Sections --------------------
    sections_qs = list(
        Section.objects.filter(semester=semester)
        .select_related("subject")
    )
    sections = [s.sectionId for s in sections_qs]

    section_priority_map = {s.sectionId: s.isPriorityForRooms for s in sections_qs}
    section_num_students = {s.sectionId: (s.numberOfStudents or 0) for s in sections_qs}

    # -------------------- Section Hours --------------------
    section_hours = {
        s.sectionId: {
            "lecture_min": int(s.lectureMinutes or 0),
            "lab_min": int((s.labMinutes or 0) if s.hasLab else 0),
            "units": int(s.units or 0),
        }
        for s in sections_qs
    }

    # -------------------- Instructor Load Caps --------------------
    def resolve_caps(i):
        emp = (i.employmentType or "permanent").lower()
        has_designation = bool(i.designation)

        # Normal instruction hours
        if i.designation and getattr(i.designation, "instructionHours", None):
            normal_h = i.designation.instructionHours
        elif i.rank and getattr(i.rank, "instructionHours", None):
            normal_h = i.rank.instructionHours
        else:
            normal_h = 40

        # Overload hours
        if emp == "permanent":
            overload_h = 9 if has_designation else 12
        else:
            overload_h = 27

        return {
            "normal_limit_min": int(normal_h * 60),
            "overload_limit_min": int(overload_h * 60),
            "employment": emp,
            "has_designation": has_designation,
        }

    instructor_caps = {i.instructorId: resolve_caps(i) for i in instructors_qs}

    # -------------------- Matches --------------------
    subject_ids = {s.subject_id for s in sections_qs}

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
        lectures = [sid for sid in sec_ids if section_hours[sid]["lecture_min"] > 0]
        labs = [sid for sid in sec_ids if section_hours[sid]["lab_min"] > 0]
        for lec in lectures:
            for lab in labs:
                if lec != lab:
                    lecture_lab_pairs.append((lec, lab))

    # -------------------- Rooms --------------------
    raw_rooms = list(Room.objects.filter(isActive=True))
    
    room_types = {} 
    room_capacities = {}
    
    rooms_list = [r.roomId for r in raw_rooms]
    for idx, r in enumerate(raw_rooms):
        room_types[idx] = r.type.lower() if r.type else 'lecture'
        room_capacities[idx] = r.capacity or 0

    # Add TBA Room
    rooms_list.append("TBA")
    TBA_ROOM_IDX = len(rooms_list) - 1
    room_types[TBA_ROOM_IDX] = 'universal' 
    room_capacities[TBA_ROOM_IDX] = 999999

    # -------------------- GenEd blocks --------------------
    gened_qs = list(GenEdSchedule.objects.filter(
        semester=semester,
        status='active'
    ))
    gened_blocks = []
    day_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2,
        "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
    }

    for g in gened_qs:
        gday = day_map.get(g.dayOfWeek, 0)
        gstart = g.startTime.hour * 60 + g.startTime.minute
        gend = g.endTime.hour * 60 + g.endTime.minute
        gened_blocks.append((gday, gstart, gend))

     # -------------------- Employment Separation --------------------
    permanent_instructors = [
        i for i in instructors_qs if (i.employmentType or "").lower() == "permanent"
    ]
    non_permanent_instructors = [
        i for i in instructors_qs if (i.employmentType or "").lower() != "permanent"
    ]

    permanent_ids = [i.instructorId for i in permanent_instructors]
    non_permanent_ids = [i.instructorId for i in non_permanent_instructors]

    # -------------------- Output (Immutable Structures) --------------------
    return {
        "instructors": tuple(instructors),
        "sections": tuple(sections),
        "rooms": tuple(rooms_list),
        "room_types": room_types,
        "room_capacities": room_capacities,
        "instructor_index": instructor_index,
        "section_priority_map": section_priority_map,
        "section_num_students": section_num_students,
        "instructor_caps": instructor_caps,
        "section_hours": section_hours,
        "matches": {k: tuple(v) for k, v in matches.items()},
        "lecture_lab_pairs": tuple(lecture_lab_pairs),

        "permanent_instructors": tuple(permanent_ids),
        "non_permanent_instructors": tuple(non_permanent_ids),

        "TBA_ROOM_IDX": TBA_ROOM_IDX,
        "gened_blocks": tuple(gened_blocks),
    }
