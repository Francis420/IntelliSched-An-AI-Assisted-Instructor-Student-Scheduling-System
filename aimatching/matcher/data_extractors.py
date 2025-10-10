from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("cross-encoder/nli-deberta-v3-large")

def chunk_text(text, max_tokens=200, overlap=30):
    tokens = tokenizer.tokenize(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.convert_tokens_to_string(chunk_tokens)
        chunks.append(chunk_text)
        start += max_tokens - overlap
    return chunks

def get_teaching_text(instructor, max_tokens=200):
    histories = instructor.teachingHistory.select_related('subject').all()
    full_text = "TEACHING HISTORY:\n" + "\n".join([
        f"Taught {h.subject.code} - {h.subject.name}: "
        f"{h.subject.description or ''} {h.subject.subjectTopics or ''} "
        f"({h.timesTaught} time{'s' if h.timesTaught != 1 else ''})."
        for h in histories if h.subject
    ])
    return chunk_text(full_text, max_tokens=max_tokens)

def get_credentials_text(instructor, max_tokens=200):
    credentials = instructor.credentials.prefetch_related('relatedSubjects').all()
    full_text = "CREDENTIALS:\n" + "\n".join([
        f"{c.type} - {c.title} ({c.issuer}, {c.dateEarned}): "
        f"{c.description or ''} "
        f"{'Verified' if c.isVerified else 'Unverified'}."
        for c in credentials
    ])
    return chunk_text(full_text, max_tokens=max_tokens)

def get_experience_text(instructor, max_tokens=200):
    experiences = instructor.experiences.prefetch_related('relatedSubjects').all()
    full_text = "PROFESSIONAL EXPERIENCE:\n" + "\n".join([
        f"{e.experienceType} - {e.title} at {e.organization} "
        f"({'Verified' if e.isVerified else 'Unverified'}): "
        f"{e.description or ''}"
        for e in experiences
    ])
    return chunk_text(full_text, max_tokens=max_tokens)

# def get_preference_text(instructor, subject, max_tokens=200):
#     preference = instructor.preferences.select_related('subject').filter(subject=subject).first()
#     if not preference:
#         return []

#     preference_phrase = {
#         'Prefer': f"The instructor explicitly prefers to teach {subject.code} - {subject.name}.",
#         'Neutral': f"The instructor has a neutral stance toward teaching {subject.code} - {subject.name}.",
#         'Avoid': f"The instructor prefers to avoid teaching {subject.code} - {subject.name}."
#     }.get(preference.preferenceType, f"The instructor's preference for {subject.code} - {subject.name} is unspecified.")

#     reason_text = f"Reason: {preference.reason.strip()}" if preference.reason else "No reason provided."

#     full_text = (
#         f"PREFERENCE:\n"
#         f"{preference_phrase} "
#         f"{reason_text} "
#         f"(Preference Type: {preference.preferenceType})"
#     )

#     return chunk_text(full_text, max_tokens=max_tokens)

def get_preference_score(instructor, subject):
    preference = instructor.preferences.filter(subject=subject).first()
    if not preference:
        return 0.0
    if preference.preferenceType == "Prefer":
        return 1.0
    if preference.preferenceType == "Avoid":
        return -1.0
    return 0.0



def get_preference_reason_text(instructor, subject):
    pref = instructor.preferences.filter(subject=subject).first()
    if not pref:
        return "No preference recorded."
    return f"{pref.preferenceType}: {(pref.reason or 'No reason provided.').strip()}"


def get_subject_text(subject, max_tokens=200):
    description = subject.description or 'No description available.'
    topics = subject.subjectTopics or 'No topics listed.'
    full_text = (
        f"Subject: {subject.code} - {subject.name}. "
        f"Description: {description} "
        f"Topics covered: {topics}."
    )
    return chunk_text(full_text, max_tokens=max_tokens)

def build_instructor_text_profile(instructor, subject, max_tokens=200):
    subject_chunks = get_subject_text(subject, max_tokens)
    profile_chunks = []

    profile_chunks += get_teaching_text(instructor, max_tokens)
    profile_chunks += get_experience_text(instructor, max_tokens)
    profile_chunks += get_credentials_text(instructor, max_tokens)
    profile_chunks += chunk_text(get_preference_reason_text(instructor, subject), max_tokens=max_tokens)

    if not subject_chunks:
        return []

    subject_chunk = subject_chunks[0]  # Usually one is sufficient
    paired_chunks = [(chunk, subject_chunk) for chunk in profile_chunks]
    return paired_chunks
