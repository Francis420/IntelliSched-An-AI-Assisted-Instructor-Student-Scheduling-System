from collections import defaultdict
from scheduling.models import (
    Subject, Section, SubjectOffering, Curriculum, ScheduleControl, Room
)
from core.models import Instructor
from aimatching.models import InstructorSubjectMatch


def get_solver_data(semester):
    """
    Returns a dict with normalized solver data:
    - instructor_index: {instructor_id: idx}
    - section_index: {section_id: idx}
    - instructors: [instructor_id,...]
    - sections: [section_id,...]
    - subjects: {subject_id: {has_lab, lecture_hours, lab_hours, is_gened, is_priority_for_rooms}}
    - section_subjects: {section_id: subject_id}
    - gened_sections: set(section_id,...)
    - instructor_availability: {instr_id: {day: [(start_min, end_min), ...]}}
    - instructor_loads: {instr_id: (normal_hours, overload_hours)}
    - matches: {section_id: [(instr_id, score), ...]}
    - section_hours: {section_id: (lecture_hours, lab_hours)}
    - lecture_lab_pairs: [(lecture_section_id, lab_section_id), ...]
    - rooms: [room_id,...]
    - room_index: {room_id: idx}
    - rooms_qs: list of Room instances
    - section_enrollment: {section_id: enrolled_students_count}
    """

    # ==== Instructors ====
    instructors_qs = list(Instructor.objects.all())
    instructors = [i.instructorId for i in instructors_qs]
    instructor_index = {i.instructorId: idx for idx, i in enumerate(instructors_qs)}

    # ==== Sections ====
    sections_qs = list(Section.objects.filter(semester=semester))
    sections = [s.sectionId for s in sections_qs]
    section_index = {s.sectionId: idx for idx, s in enumerate(sections_qs)}

    # ==== Subjects & Properties ====
    subject_ids = {s.subject_id for s in sections_qs}
    subjects_qs = Subject.objects.filter(subjectId__in=subject_ids).select_related("curriculum")
    subjects = {}
    for subj in subjects_qs:
        subjects[subj.subjectId] = {
            "units": getattr(subj, "units", 0),  # 🆕 added
            "lecture_hours": subj.lectureHours,  # computed from durationMinutes / 60
            "lab_hours": subj.labHours,  # computed from labDurationMinutes / 60
            "has_lab": subj.hasLab,
            "is_gened": bool(subj.curriculum.isActive and getattr(subj.curriculum, "is_gened", False))
                        if getattr(subj, "curriculum", None) else False,
            "is_priority_for_rooms": subj.isPriorityForRooms,
            "type": getattr(subj, "type", None),
        }


    section_subjects = {s.sectionId: s.subject_id for s in sections_qs}
    gened_sections = {s.sectionId for s in sections_qs if subjects.get(s.subject_id, {}).get("is_gened", False)}

    # ==== Section hours (lecture, lab, units) ====
    section_hours = {}
    for s in sections_qs:
        subj = subjects.get(s.subject_id, {"lecture_hours": 0, "lab_hours": 0, "units": 0})
        lecture_h = subj.get("lecture_hours", 0)
        lab_h = subj.get("lab_hours", 0) if subj.get("has_lab", False) else 0
        units = subj.get("units", 0)
        section_hours[s.sectionId] = {
            "lecture_hours": lecture_h,
            "lab_hours": lab_h,
            "units": units,  # 🆕 added
        }


    # ==== Section enrollment counts ====
    section_enrollment = {s.sectionId: getattr(s, "enrollment_count", 0) for s in sections_qs}

    # ==== Instructor loads ====
    instructor_loads = {}

    for inst in instructors_qs:
        # --- NORMAL LOAD ---
        # Priority: Designation > Rank > Fallback
        if inst.designation and getattr(inst.designation, "normalLoad", None) is not None:
            normal = inst.designation.normalLoad
        elif inst.rank and getattr(inst.rank, "normalLoad", None) is not None:
            normal = inst.rank.normalLoad
        else:
            normal = 18  # default fallback if neither rank nor designation has one

        # --- OVERLOAD ---
        # Based on Academic Attainment (and may vary if has designation)
        if inst.academicAttainment:
            overload = getattr(inst.academicAttainment, "overLoad", 3)
        else:
            overload = 6 # default if no attainment assigned

        instructor_loads[inst.instructorId] = (int(normal), int(overload))

    # ==== Instructor availability ====
    instructor_availability = defaultdict(lambda: defaultdict(list))
    controls = ScheduleControl.objects.filter(schedule__instructor__in=instructors_qs)

    for c in controls:
        day = int(c.schedule.dayOfWeek) if isinstance(c.schedule.dayOfWeek, int) else \
              {"Monday":0, "Tuesday":1, "Wednesday":2, "Thursday":3, "Friday":4,
               "Saturday":5, "Sunday":6}.get(c.schedule.dayOfWeek, 0)
        start = c.schedule.startTime.hour * 60 + c.schedule.startTime.minute
        end = c.schedule.endTime.hour * 60 + c.schedule.endTime.minute
        instructor_availability[c.schedule.instructor_id][day].append((start, end))

    # ==== Matches (InstructorSubjectMatch) ====
    # Get subject IDs for filtering matches
    subject_ids = {s.subject_id for s in sections_qs}
    match_qs = InstructorSubjectMatch.objects.filter(subject_id__in=subject_ids)
    
    # Build matches dict mapping section_id -> list of (instructor_id, score)
    matches = defaultdict(list)
    # Because InstructorSubjectMatch relates to subject, but we want matches per section,
    # and each section has subject_id, so we assign matches to all sections with matching subject.
    subj_to_section_ids = defaultdict(list)
    for s in sections_qs:
        subj_to_section_ids[s.subject_id].append(s.sectionId)
    
    for m in match_qs.select_related("instructor", "subject"):
        instr_id = m.instructor.instructorId
        subj_id = m.subject.subjectId
        for sec_id in subj_to_section_ids.get(subj_id, []):
            matches[sec_id].append((instr_id, float(m.isRecommended)))  # or m.score if you have score field

    # ==== Lecture/Lab pairs ====
    lecture_lab_pairs = []
    subj_to_sections = defaultdict(list)
    for s in sections_qs:
        subj_to_sections[s.subject_id].append(s.sectionId)

    for subj_id, sec_ids in subj_to_sections.items():
        subj_meta = subjects.get(subj_id, {})
        if not subj_meta.get("has_lab", False):
            continue
        lectures = [sid for sid in sec_ids if section_hours.get(sid, {}).get("lecture_hours", 0) > 0]
        labs = [sid for sid in sec_ids if section_hours.get(sid, {}).get("lab_hours", 0) > 0]
        for lec in lectures:
            for lab in labs:
                if lec != lab:
                    lecture_lab_pairs.append((lec, lab))

    # ==== Rooms ====
    rooms_qs = list(Room.objects.filter(isActive=True))
    rooms = [r.roomId for r in rooms_qs]
    room_index = {r.roomId: idx for idx, r in enumerate(rooms_qs)}

    return {
        "instructor_index": instructor_index,
        "section_index": section_index,
        "instructors": instructors,
        "sections": sections,
        "subjects": subjects,
        "section_hours": section_hours,
        "section_subjects": section_subjects,
        "gened_sections": gened_sections,
        "instructor_availability": {k: dict(v) for k, v in instructor_availability.items()},
        "instructor_loads": instructor_loads,
        "matches": dict(matches),
        "section_hours": section_hours,
        "lecture_lab_pairs": lecture_lab_pairs,
        "rooms": rooms,
        "room_index": room_index,
        "rooms_qs": rooms_qs,
        "section_enrollment": section_enrollment,
    }
