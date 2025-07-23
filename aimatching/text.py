from instructors.models import (
    InstructorExperience,
    InstructorCredentials,
    InstructorSubjectPreference,
    TeachingHistory,
)
from scheduling.models import Subject


def gatherInstructorText(instructor):
    lines = []

    # Academic attainment, designation, rank
    if instructor.academicAttainment:
        lines.append(f"Academic Attainment: {instructor.academicAttainment.name}")
    if instructor.designation:
        lines.append(f"Designation: {instructor.designation.name}")
    if instructor.rank:
        lines.append(f"Rank: {instructor.rank.name}")

    # Teaching history
    for teaching in instructor.teachingHistory.all():
        subject = teaching.subject
        topic_str = f" - Topics: {subject.subjectTopics}" if subject.subjectTopics else ""
        lines.append(f"Taught: {subject.code} - {subject.name}{topic_str} x{teaching.timesTaught}")

    # Experiences
    from instructors.models import InstructorExperience
    experiences = InstructorExperience.objects.filter(instructor=instructor, isVerified=True).prefetch_related("relatedSubjects")
    for exp in experiences:
        lines.append(f"Experience ({exp.experienceType}): {exp.title} at {exp.organization} - {exp.description}")
        for subj in exp.relatedSubjects.all():
            topic_str = f" - Topics: {subj.subjectTopics}" if subj.subjectTopics else ""
            lines.append(f"Related Subject: {subj.code} - {subj.name}{topic_str}")

    # Credentials
    from instructors.models import InstructorCredentials
    credentials = InstructorCredentials.objects.filter(instructor=instructor, isVerified=True).prefetch_related("relatedSubjects")
    for cred in credentials:
        lines.append(f"Credential ({cred.type}): {cred.title} - {cred.description} by {cred.issuer}")
        for subj in cred.relatedSubjects.all():
            topic_str = f" - Topics: {subj.subjectTopics}" if subj.subjectTopics else ""
            lines.append(f"Related Subject: {subj.code} - {subj.name}{topic_str}")

    # Subject preferences
    from instructors.models import InstructorSubjectPreference
    preferences = InstructorSubjectPreference.objects.filter(instructor=instructor).select_related("subject")
    for pref in preferences:
        subject = pref.subject
        topic_str = f" - Topics: {subject.subjectTopics}" if subject.subjectTopics else ""
        lines.append(f"Preference ({pref.preferenceType}): {subject.code} - {subject.name}{topic_str}")

    return "\n".join(lines)
