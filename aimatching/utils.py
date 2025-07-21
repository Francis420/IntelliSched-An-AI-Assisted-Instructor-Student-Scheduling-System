from core.models import Instructor
from instructors.models import InstructorExperience, InstructorCredentials, InstructorSubjectPreference, TeachingHistory
from scheduling.models import Subject
from aimatching.models import InstructorSubjectMatch

def getTrainingData():
    data = []
    labels = []

    for match in InstructorSubjectMatch.objects.select_related('instructor', 'subject').all():
        instructor = match.instructor
        subject = match.subject

        # --- Gather related data ---
        experiences = InstructorExperience.objects.filter(instructor=instructor)
        credentials = InstructorCredentials.objects.filter(instructor=instructor)
        preferences = InstructorSubjectPreference.objects.filter(instructor=instructor, subject=subject).first()
        teaching_history = TeachingHistory.objects.filter(instructor=instructor, subject=subject).first()

        # --- Combine all relevant text fields ---
        text_parts = []

        for exp in experiences:
            text_parts.append(exp.title or "")
            text_parts.append(exp.description or "")

        for cred in credentials:
            text_parts.append(cred.title or "")
            text_parts.append(cred.description or "")

        if preferences:
            text_parts.append(preferences.preferenceType or "")
            text_parts.append(preferences.reason or "")

        if teaching_history:
            text_parts.append(f"Taught {teaching_history.timesTaught} times")

        combined_text = " ".join(text_parts).strip()

        if combined_text and subject.code:
            data.append(combined_text)
            labels.append(subject.code)

    return data, labels
