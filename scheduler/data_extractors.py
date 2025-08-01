from scheduling.models import Semester, Section, Subject, GenEdSchedule 
from instructors.models import (
    InstructorDesignation, InstructorRank, InstructorAcademicAttainment, InstructorAvailability
)
from core.models import Instructor


def get_solver_data(semester: Semester):
    # Sections & Subjects
    sections = Section.objects.filter(semester=semester).select_related("subject")
    subjects = [s.subject for s in sections]

    # GenEd schedules (priority blocks)
    gened_blocks = list(GenEdSchedule.objects.filter(semester=semester, isPriority=True))

    # Instructor availability
    availabilities = InstructorAvailability.objects.select_related("instructor")

    # Instructor teaching load rules
    instructors = Instructor.objects.all()
    load_data = []
    for instructor in instructors:
        if instructor.designation:
            normal_load = instructor.designation.instructionHours
        elif instructor.rank:
            normal_load = instructor.rank.instructionHours
        else:
            normal_load = 18  # Default fallback if neither designation nor rank is set

        if instructor.academicAttainment:
            if instructor.designation:
                overload_units = instructor.academicAttainment.overloadUnitsHasDesignation
            else:
                overload_units = instructor.academicAttainment.overloadUnitsNoDesignation
        else:
            overload_units = 0

        load_data.append({
            "instructor": instructor,
            "normal_load": normal_load,
            "overload_units": overload_units,
        })

    return {
        "sections": sections,
        "subjects": subjects,
        "gened_blocks": gened_blocks,
        "availabilities": availabilities,
        "instructors": load_data,
    }
