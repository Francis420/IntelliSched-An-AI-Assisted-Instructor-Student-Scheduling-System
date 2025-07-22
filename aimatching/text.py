from instructors.models import InstructorExperience, InstructorCredentials, InstructorSubjectPreference, TeachingHistory

def gatherInstructorText(instructor):
    text_parts = []

    experiences = InstructorExperience.objects.filter(instructor=instructor)
    credentials = InstructorCredentials.objects.filter(instructor=instructor)
    preferences = InstructorSubjectPreference.objects.filter(instructor=instructor)
    teaching_history = TeachingHistory.objects.filter(instructor=instructor)

    for exp in experiences:
        text_parts.append(exp.title or "")
        text_parts.append(exp.description or "")

    for cred in credentials:
        text_parts.append(cred.title or "")
        text_parts.append(cred.description or "")

    for pref in preferences:
        text_parts.append(pref.preferenceType or "")
        text_parts.append(pref.reason or "")

    for history in teaching_history:
        if history.subject:
            text_parts.append(history.subject.name or "")
            text_parts.append(history.subject.code or "")
        if history.semester:
            text_parts.append(history.semester.name or "")
        text_parts.append(f"Taught {history.timesTaught} times")

    return " ".join(text_parts).strip()
