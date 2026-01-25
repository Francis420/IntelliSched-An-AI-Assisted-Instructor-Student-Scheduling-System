# scheduler/data_extractors.py
from collections import defaultdict
from scheduling.models import Section, Room, GenEdSchedule, InstructorSchedulingConfiguration
from core.models import Instructor
from aimatching.models import InstructorSubjectMatch
import re


def get_solver_data(semester):
    # -------------------- Instructors --------------------
    instructors_qs = list(
        Instructor.objects.filter(
            employmentType__in=['permanent', 'part-time', 'overload']
        ).select_related('rank', 'designation'
        ).order_by('instructorId')
        
    )
    
    instructors = [i.instructorId for i in instructors_qs]
    instructor_index = {i.instructorId: idx for idx, i in enumerate(instructors_qs)}

    # -------------------- Sections --------------------
    sections_qs = list(
        Section.objects.filter(semester=semester, status='active')
        .select_related("subject")
        .order_by('sectionId')
    )
    sections = [s.sectionId for s in sections_qs]

    section_priority_map = {s.sectionId: s.isPriorityForRooms for s in sections_qs}
    section_num_students = {s.sectionId: (s.numberOfStudents or 0) for s in sections_qs}

    def get_block_name(section):
        year = section.subject.yearLevel

        code = (section.sectionCode or "").strip()
        match = re.search(r'-\s*([A-Z])$', code)
        if match:
            letter = match.group(1)
            return f"{year}{letter}"
        return f"UNKNOWN_{code}"

    section_to_group = {
        s.sectionId: get_block_name(s) 
        for s in sections_qs
    }

    # -------------------- Section Hours --------------------
    section_hours = {
        s.sectionId: {
            "lecture_min": int(s.lectureMinutes or 0),
            "lab_min": int((s.labMinutes or 0) if s.hasLab else 0),
            "units": int(s.units or 0),
        }
        for s in sections_qs
    }

    # -------------------- Instructor Load Caps (DYNAMIC) --------------------
    conf = InstructorSchedulingConfiguration.objects.filter(is_active=True).first()

    # Configuration for Permanent types
    overload_has_designation = conf.overload_limit_with_designation if conf else 9.0
    overload_has_no_designation = conf.overload_limit_no_designation if conf else 12.0
    
    # Configuration for Non-Permanent types
    PART_TIME_NORMAL_HRS = conf.part_time_normal_limit if conf else 15.0
    PART_TIME_OVERLOAD_HRS = conf.part_time_overload_limit if conf else 0.0
    
    # "Part-Time (Overload)" employees cannot teach Normal hours
    PURE_OVERLOAD_NORMAL_HRS = conf.pure_overload_normal_limit if conf else 0.0
    PURE_OVERLOAD_LIMIT_HRS = conf.pure_overload_max_limit if conf else 12.0

    instructor_caps = {}
    for i in instructors_qs:
        emp_type = (i.employmentType or "").lower().strip()
        
        norm_hrs = 0
        over_hrs = 0
        
        if emp_type == 'permanent':
            is_designated = False
            if i.designation:
                designation_name = (i.designation.name or "").strip().upper()
                if designation_name != "N/A" and designation_name != "":
                    is_designated = True
            
            if is_designated:
                norm_hrs = i.designation.instructionHours
            else:
                if i.rank:
                    norm_hrs = i.rank.instructionHours
                else:
                    norm_hrs = 18
            
            if is_designated:
                over_hrs = overload_has_designation
            else:
                over_hrs = overload_has_no_designation

        elif emp_type == 'part-time':
            norm_hrs = PART_TIME_NORMAL_HRS
            over_hrs = PART_TIME_OVERLOAD_HRS
            
        elif emp_type == 'overload': 
            norm_hrs = PURE_OVERLOAD_NORMAL_HRS
            over_hrs = PURE_OVERLOAD_LIMIT_HRS

        instructor_caps[i.instructorId] = {
            "normal_limit_min": int(norm_hrs * 60),
            "overload_limit_min": int(over_hrs * 60)
        }

    # -------------------- Matches --------------------
    subject_ids = {s.subject_id for s in sections_qs}

    match_qs = InstructorSubjectMatch.objects.filter(
        subject_id__in=subject_ids
    ).select_related("instructor", "subject", "latestHistory")

    subj_to_section_ids = defaultdict(list)
    for s in sections_qs:
        subj_to_section_ids[s.subject_id].append(s.sectionId)

    matches = defaultdict(list)
    for m in match_qs:
        instr_id = m.instructor.instructorId
        subj_id = m.subject.subjectId
        
        score = 0.0
        if m.latestHistory:
            score = m.latestHistory.confidenceScore
        elif m.isRecommended:
            score = 1.0

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
    raw_rooms = list(Room.objects.filter(isActive=True).order_by('roomId'))
    
    room_types = {} 
    room_capacities = {}
    
    rooms_list = [r.roomId for r in raw_rooms]
    for idx, r in enumerate(raw_rooms):
        r_type_str = (r.type or "").lower()
        
        if "lab" in r_type_str:
            room_types[idx] = "laboratory"
        elif "lec" in r_type_str:
            room_types[idx] = "lecture"
        else:
            # Fallback for weird typos
            room_types[idx] = "lecture" 

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
        
        gened_blocks.append((gday, gstart, gend, g.student_group))

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
        "gened_blocks": tuple(gened_blocks),
        "section_to_group": section_to_group,
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
        
    }
