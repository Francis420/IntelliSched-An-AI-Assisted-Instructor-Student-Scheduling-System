# core/data_extractors.py
from django.db.models import Count

# ==========================================
# HELPER: Text Chunking
# ==========================================
def split_text_by_words(text, max_words=150):
    """
    Splits a long text into smaller lists of words (chunks).
    This prevents the AI from crashing when reading long profiles.
    """
    if not text:
        return []
        
    words = text.split()
    chunks = []
    
    # Loop through words and slice them into chunks of size 'max_words'
    for i in range(0, len(words), max_words):
        chunk_words = words[i : i + max_words]
        chunk_str = " ".join(chunk_words)
        chunks.append(chunk_str)
        
    return chunks

# ==========================================
# 1. TEACHING HISTORY EXTRACTOR
# ==========================================
def get_teaching_history_text(instructor):
    """
    Summarizes what the instructor has taught in the past.
    """
    summary_lines = []

    # Get data from the database
    # 1. System Assignments (Counted by subject)
    system_stats = instructor.system_assignments.values(
        'subject__code', 'subject__name'
    ).annotate(count=Count('assignmentId'))

    # 2. Legacy Experience (Manual entries)
    legacy_stats = instructor.legacy_experiences.select_related('subject').all()

    # Combine them into a dictionary to avoid duplicates
    subject_history = {}

    for stat in system_stats:
        code = stat['subject__code']
        subject_history[code] = f"{stat['subject__name']} ({stat['count']} times in system)"

    for leg in legacy_stats:
        code = leg.subject.code
        legacy_note = f"Legacy: {leg.priorTimesTaught} times, {leg.priorYearsExperience} years."
        
        if code in subject_history:
            subject_history[code] += f". {legacy_note}"
        else:
            subject_history[code] = f"{leg.subject.name}. {legacy_note}"

    # Format into a list of strings
    for code, details in subject_history.items():
        summary_lines.append(f"Subject {code}: {details}")

    if not summary_lines:
        return ""
        
    return "TEACHING HISTORY:\n" + "\n".join(summary_lines)

# ==========================================
# 2. PROFESSIONAL EXPERIENCE EXTRACTOR
# ==========================================
def get_experience_text(instructor):
    """
    Formats work experience (Industry, Research, etc).
    """
    experiences = instructor.experiences.all()
    if not experiences.exists():
        return ""

    lines = []
    for exp in experiences:
        end_date = "Present" if exp.isCurrent else str(exp.endDate)
        
        line = (
            f"{exp.get_experienceType_display()} - {exp.title} at {exp.organization}. "
            f"({exp.startDate} to {end_date}). "
            f"{exp.description}"
        )
        lines.append(line)

    return "PROFESSIONAL EXPERIENCE:\n" + "\n".join(lines)

# ==========================================
# 3. CREDENTIALS EXTRACTOR
# ==========================================
def get_credentials_text(instructor):
    """
    Formats degrees and licenses.
    """
    credentials = instructor.credentials.all()
    if not credentials.exists():
        return ""

    lines = []
    for cred in credentials:
        line = (
            f"{cred.get_credentialType_display()}: {cred.title} "
            f"from {cred.issuer} ({cred.dateEarned})."
        )
        lines.append(line)

    return "CREDENTIALS:\n" + "\n".join(lines)

# ==========================================
# 4. TARGET SUBJECT EXTRACTOR
# ==========================================
def get_target_subject_text(subject):
    """
    Formats the subject we want to find a match for.
    """
    return (
        f"TARGET SUBJECT:\n"
        f"Code: {subject.code}\n"
        f"Name: {subject.name}\n"
        f"Description: {subject.description or 'No description'}\n"
        f"Topics: {subject.subjectTopics or 'No topics'}"
    )

# ==========================================
# MAIN FUNCTION
# ==========================================
def build_instructor_text_profile(instructor, target_subject):
    """
    Creates pairs of text for the AI to compare.
    Returns: List of [Instructor_Text, Subject_Text]
    """
    # 1. Prepare the Target Subject text (The Anchor)
    subject_text_full = get_target_subject_text(target_subject)
    # We take the first chunk of the subject description as the main comparison point
    subject_chunks = split_text_by_words(subject_text_full, max_words=150)
    
    if not subject_chunks:
        return []
    
    subject_anchor = subject_chunks[0]

    # 2. Collect all Instructor text
    history = get_teaching_history_text(instructor)
    experience = get_experience_text(instructor)
    credentials = get_credentials_text(instructor)

    # Combine into one big string
    full_profile = f"{history}\n\n{experience}\n\n{credentials}"

    # 3. Split the Instructor text into chunks (to handle large amounts of text)
    instructor_chunks = split_text_by_words(full_profile, max_words=150)

    # 4. Create Comparison Pairs
    # The AI needs to see: [Instructor Part 1, Subject], [Instructor Part 2, Subject], etc.
    pairs = []
    for chunk in instructor_chunks:
        if chunk.strip():
            pairs.append([chunk, subject_anchor])

    return pairs