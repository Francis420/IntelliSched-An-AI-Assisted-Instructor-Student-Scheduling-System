from scheduling.models import Semester, Section, Subject, GenEdSchedule
from instructors.models import InstructorDesignation, InstructorRank, InstructorAcademicAttainment, InstructorAvailability
from core.models import Instructor

def getSolverData(semester: Semester):
    """
    Build structured data for the solver:
    - Sections & Subjects
    - GenEd priority schedules
    - Instructor availability (default Mon–Fri 08:00–20:00 if none given)
    - Teaching load rules (normal + overload)
    """

    # Sections & Subjects
    sections = Section.objects.filter(semester=semester).select_related("subject")
    subjects = [s.subject for s in sections]

    # GenEd schedules (priority blocks)
    genedBlocks = list(GenEdSchedule.objects.filter(semester=semester, isPriority=True))

    # Instructor availability
    allAvailabilities = InstructorAvailability.objects.select_related("instructor")

    availabilities = {}
    for inst in Instructor.objects.all():
        instructorAvailabilities = [
            {
                "day": a.dayOfWeek,
                "start": a.startTime.strftime("%H:%M"),
                "end": a.endTime.strftime("%H:%M"),
            }
            for a in allAvailabilities if a.instructor == inst
        ]
        if not instructorAvailabilities:
            # fallback: full availability Mon–Fri 08:00–20:00
            instructorAvailabilities = [
                {"day": d, "start": "08:00", "end": "20:00"}
                for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            ]
        availabilities[inst.instructorId] = instructorAvailabilities

    # Instructor teaching load rules
    loadData = []
    for instructor in Instructor.objects.all():
        if instructor.designation:
            normalLoad = instructor.designation.instructionHours
        elif instructor.rank:
            normalLoad = instructor.rank.instructionHours
        else:
            normalLoad = 18  # default fallback

        if instructor.academicAttainment:
            if instructor.designation:
                overloadUnits = instructor.academicAttainment.overloadUnitsHasDesignation
            else:
                overloadUnits = instructor.academicAttainment.overloadUnitsNoDesignation
        else:
            overloadUnits = 0

        loadData.append({
            "instructor": instructor,
            "normalLoad": normalLoad,
            "overloadUnits": overloadUnits,
            "availability": availabilities[instructor.instructorId],
        })

    return {
        "sections": sections,
        "subjects": subjects,
        "gened_blocks": genedBlocks,
        "instructors": loadData,
    }


def checkInstructorAvailability(instructor_data, day, start, end):
    """
    Returns True if instructor is available for the given time slot.
    """
    for block in instructor_data["availability"]:  # 🔹 fixed here
        if block["day"] == day and block["start"] <= start and block["end"] >= end:
            return True
    return False


def checkInstructorLoad(instructor_data, assigned_hours):
    """
    Returns True if instructor can take the assigned_hours considering normal & overload rules.
    """
    if assigned_hours <= instructor_data["normalLoad"]:
        return True
    elif assigned_hours <= instructor_data["normalLoad"] + instructor_data["overloadUnits"]:
        return True
    return False

def enforceLectureLabDifferentDays(model, section_vars, sections):
    """
    Add constraint so that lecture and lab of the same section
    must be scheduled on different days.
    """
    for section in sections:
        if section.subject.hasLab:
            lec_var = section_vars[(section.sectionId, "Lecture")]["day"]
            lab_var = section_vars[(section.sectionId, "Lab")]["day"]
            model.Add(lec_var != lab_var)
