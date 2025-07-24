def get_teaching_text(instructor):
    histories = instructor.teachingHistory.select_related('subject').all()
    return " ".join([
        f"{h.subject.code} {h.subject.name} "
        f"{h.subject.description or ''} {h.subject.subjectTopics or ''} "
        f"Taught {h.timesTaught} time{'s' if h.timesTaught != 1 else ''}"
        for h in histories if h.subject
    ])

def get_credentials_text(instructor):
    credentials = instructor.credentials.prefetch_related('relatedSubjects').all()
    return " ".join([
        f"{c.type} - {c.title} ({c.issuer}, {c.dateEarned}) "
        f"{c.description or ''} "
        f"{'Verified' if c.isVerified else 'Unverified'} "
        f"{' '.join([s.code for s in c.relatedSubjects.all()])}"
        for c in credentials
    ])


def get_experience_text(instructor):
    experiences = instructor.experiences.prefetch_related('relatedSubjects').all()
    return " ".join([
        f"{e.experienceType}: {e.title} at {e.organization}, "
        f"{'(Verified)' if e.isVerified else '(Unverified)'} "
        f"{e.description or ''} "
        f"{' '.join([s.code for s in e.relatedSubjects.all()])}"
        for e in experiences
    ])


def get_preference_text(instructor):
    preferences = instructor.preferences.select_related('subject').all()
    return " ".join([
        f"{p.subject.code} {p.subject.name} {p.reason or ''} {p.preferenceType}"
        for p in preferences
    ])


def get_subject_text(subject):
    """
    Returns a combined string of the subject's code, name, description, and topics.
    """
    return f"{subject.code} {subject.name} {subject.description or ''} {subject.subjectTopics or ''}"

