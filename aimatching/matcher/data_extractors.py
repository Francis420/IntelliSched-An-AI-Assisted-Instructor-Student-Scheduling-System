def get_teaching_text(instructor):
    parts = []
    for history in instructor.teachingHistory.all():
        if history.subject:
            parts.append(history.subject.name)
            parts.append(history.subject.description or "")
            parts.append(history.subject.subjectTopics or "")
    return " ".join(parts)

def get_credentials_text(instructor):
    parts = []
    for cred in instructor.instructorcredentials_set.filter(isVerified=True):
        parts.append(cred.title)
        parts.append(cred.type)
        parts.append(cred.description or "")
        parts.append(cred.issuer)
        for subj in cred.relatedSubjects.all():
            parts.append(subj.name)
            parts.append(subj.subjectTopics or "")
            parts.append(subj.description or "")
    return " ".join(parts)

def get_experience_text(instructor):
    parts = []
    for exp in instructor.experiences.all():
        parts.append(exp.title)
        parts.append(exp.description or "")
    return " ".join(parts)

def get_preference_text(instructor):
    parts = []
    for pref in instructor.subjectPreferences.all():
        if pref.subject:
            parts.append(pref.subject.name)
            parts.append(pref.subject.subjectTopics or "")
            parts.append(pref.subject.description or "")
        parts.append(pref.reason or "")
    return " ".join(parts)
