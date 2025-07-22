from core.models import Instructor
from instructors.models import InstructorExperience, InstructorCredentials, InstructorSubjectPreference, TeachingHistory
from scheduling.models import Subject
from aimatching.models import InstructorSubjectMatch
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from .model_training import loadSVMModel

def getTrainingData():
    data = []
    labels = []

    for match in InstructorSubjectMatch.objects.select_related('instructor', 'subject').all():
        instructor = match.instructor
        subject = match.subject

        experiences = InstructorExperience.objects.filter(instructor=instructor)
        credentials = InstructorCredentials.objects.filter(instructor=instructor)
        preferences = InstructorSubjectPreference.objects.filter(instructor=instructor, subject=subject).first()
        teaching_history = TeachingHistory.objects.filter(instructor=instructor, subject=subject).first()

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


def gatherInstructorText(instructor):
    from instructors.models import InstructorExperience, InstructorCredentials, InstructorSubjectPreference, TeachingHistory

    text_parts = []

    # Experience
    for exp in InstructorExperience.objects.filter(instructor=instructor, isVerified=True):
        text_parts.append(f"{exp.title} at {exp.organization}")
        text_parts.append(exp.description or "")
        text_parts.append(exp.experienceType or "")

    # Credentials
    for cred in InstructorCredentials.objects.filter(instructor=instructor, isVerified=True):
        text_parts.append(f"{cred.title} from {cred.issuer}")
        text_parts.append(cred.description or "")
        text_parts.append(cred.type or "")

    # Subject Preferences
    for pref in InstructorSubjectPreference.objects.filter(instructor=instructor):
        text_parts.append(f"{pref.subject.name} ({pref.subject.code}) - {pref.preferenceType}")
        if pref.reason:
            text_parts.append(pref.reason)

    # Teaching History
    for history in TeachingHistory.objects.filter(instructor=instructor):
        text_parts.append(f"Taught {history.subject.name} ({history.subject.code}) {history.timesTaught} times")

    return " ".join(text_parts).strip()
