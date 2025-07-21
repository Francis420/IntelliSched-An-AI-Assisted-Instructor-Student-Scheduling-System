from core.models import Instructor
from instructors.models import InstructorExperience, InstructorCredentials
from scheduling.models import Subject
from aimatching.models import InstructorSubjectMatch  # adjust import if needed

def getTrainingData():
    data = []
    labels = []

    for match in InstructorSubjectMatch.objects.select_related('instructor', 'subject').all():
        instructor = match.instructor
        subject = match.subject

        # Gather experience & credentials / teaching history?
        experiences = InstructorExperience.objects.filter(instructor=instructor)
        credentials = InstructorCredentials.objects.filter(instructor=instructor)

        # Combine all text fields
        text_parts = []

        for exp in experiences:
            text_parts.append(exp.title or "")
            text_parts.append(exp.description or "")

        for cred in credentials:
            text_parts.append(cred.title or "")
            text_parts.append(cred.description or "")

        combined_text = " ".join(text_parts).strip()

        if combined_text and subject.code:
            data.append(combined_text)
            labels.append(subject.code)  # or use subject.subjectId? code nalang ata since more descriptive

    return data, labels
