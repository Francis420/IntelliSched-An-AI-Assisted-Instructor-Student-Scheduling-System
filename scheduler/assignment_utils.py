# scheduler/assignment_utils.py

from django.db.models import Prefetch
from scheduling.models import SubjectOffering, Semester
from aimatching.models import InstructorSubjectMatch
from core.models import Instructor
from scheduler.constraints import (
    checkInstructorAvailability,
    checkInstructorLoad,
)
from scheduler.data_extractors import get_solver_data


def assign_instructors_for_semester(semester_id):
    """
    Assigns instructors to all subject offerings for a given semester
    using highest-confidence matches and load rules.
    """
    semester = Semester.objects.get(pk=semester_id)

    # Get all subject offerings without assigned instructor
    offerings = SubjectOffering.objects.filter(
        semester=semester,
        instructor__isnull=True
    ).select_related('subject')

    # Prefetch matches for performance
    all_matches = InstructorSubjectMatch.objects.filter(
        subject__in=[o.subject for o in offerings],
        semester=semester
    ).order_by('-confidence_score', '-created_at')  # highest score, latest first

    matches_by_subject = {}
    for match in all_matches:
        matches_by_subject.setdefault(match.subject_id, []).append(match)

    for offering in offerings:
        matches = matches_by_subject.get(offering.subject_id, [])
        assigned = False

        for match in matches:
            instructor = match.instructor

            if not checkInstructorAvailability(instructor, offering):
                continue
            if not checkInstructorLoad(instructor, offering):
                continue

            # Assign instructor
            offering.instructor = instructor
            offering.save()
            assigned = True
            break

        if not assigned:
            print(f"No available instructor found for {offering.subject.code} - {offering.section.name}")

    return True


def assign_multiple_sections(semester_id):
    """
    Handles the case where multiple sections need the same subject.
    Picks top N instructors, skipping full/overloaded ones.
    """
    semester = Semester.objects.get(pk=semester_id)

    offerings = SubjectOffering.objects.filter(
        semester=semester,
        instructor__isnull=True
    ).select_related('subject', 'section')

    all_matches = InstructorSubjectMatch.objects.filter(
        subject__in=[o.subject for o in offerings],
        semester=semester
    ).order_by('-confidence_score', '-created_at')

    matches_by_subject = {}
    for match in all_matches:
        matches_by_subject.setdefault(match.subject_id, []).append(match)

    for subject_id, subject_offerings in group_by_subject(offerings).items():
        matches = matches_by_subject.get(subject_id, [])

        for offering in subject_offerings:
            assigned = False
            for match in matches:
                instructor = match.instructor

                if not checkInstructorAvailability(instructor, offering):
                    continue
                if not checkInstructorLoad(instructor, offering):
                    continue

                offering.instructor = instructor
                offering.save()
                assigned = True
                break

            if not assigned:
                print(f"No available instructor for {offering.subject.code} ({offering.section.name})")

    return True


def group_by_subject(offerings):
    """
    Helper to group offerings by subject_id.
    """
    grouped = {}
    for o in offerings:
        grouped.setdefault(o.subject_id, []).append(o)
    return grouped
