from django.db.models import Count
from transformers import AutoTokenizer

# Initialize tokenizer once (global scope is usually fine for worker scripts)
# Ensure you have the 'transformers' library installed
tokenizer = AutoTokenizer.from_pretrained("cross-encoder/nli-deberta-v3-large")

def chunk_text(text, max_tokens=200, overlap=30):
    """
    Splits text into overlapping chunks based on token count.
    """
    tokens = tokenizer.tokenize(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        # Skip empty chunks
        if not chunk_tokens:
            break
            
        chunk_text = tokenizer.convert_tokens_to_string(chunk_tokens)
        chunks.append(chunk_text)
        
        # Prevent infinite loop if max_tokens is smaller than overlap
        step = max(1, max_tokens - overlap)
        start += step
        
    return chunks

def get_teaching_text(instructor, max_tokens=200):
    """
    Combines 'Automated System Assignments' and 'Manual Legacy Experience'
    into a single summarized teaching history per subject.
    """
    # 1. Aggregate System Data (Group by Subject to save tokens)
    # Result: [{'subject__code': 'CS101', 'subject__name': 'Intro to CS', 'count': 5}, ...]
    system_stats = instructor.system_assignments.values(
        'subject__code', 
        'subject__name', 
        'subject__description', 
        'subject__subjectTopics'
    ).annotate(count=Count('assignmentId'))
    
    # 2. Get Legacy Data
    legacy_stats = instructor.legacy_experiences.select_related('subject').all()
    
    # 3. Merge Data in Memory
    subject_map = {}
    
    # Process System Stats
    for item in system_stats:
        code = item['subject__code']
        subject_map[code] = {
            'name': item['subject__name'],
            'desc': item['subject__description'] or '',
            'topics': item['subject__subjectTopics'] or '',
            'system_count': item['count'],
            'legacy_count': 0,
            'legacy_years': 0
        }
        
    # Process Legacy Stats
    for item in legacy_stats:
        code = item.subject.code
        if code not in subject_map:
             subject_map[code] = {
                'name': item.subject.name,
                'desc': item.subject.description or '',
                'topics': item.subject.subjectTopics or '',
                'system_count': 0,
                'legacy_count': 0, # Will update below
                'legacy_years': 0
            }
        subject_map[code]['legacy_count'] = item.priorTimesTaught
        subject_map[code]['legacy_years'] = item.priorYearsExperience

    # 4. Generate Text
    lines = []
    for code, data in subject_map.items():
        total_times = data['system_count'] + data['legacy_count']
        
        # Build a concise summary string
        # e.g. "Taught 5 times (+2.5 years prior exp)."
        exp_details = f"{total_times} times"
        if data['legacy_years'] > 0:
            exp_details += f" (+{data['legacy_years']} years prior legacy)"
            
        lines.append(
            f"Subject: {code} - {data['name']}. "
            f"Topics: {data['topics']}. "
            f"History: Taught {exp_details}."
        )
    
    if not lines:
        return []

    full_text = "TEACHING HISTORY:\n" + "\n".join(lines)
    return chunk_text(full_text, max_tokens=max_tokens)

def get_credentials_text(instructor, max_tokens=200):
    """
    Updated for InstructorCredentials model. 
    Removed: description, isVerified (fields deleted).
    Added: expirationDate.
    """
    credentials = instructor.credentials.all()
    if not credentials.exists():
        return []

    lines = []
    for c in credentials:
        # Format: "Certification - AWS Solutions Architect (Amazon, 2023-01-01). Expires: 2026-01-01."
        expiry = f" Expires: {c.expirationDate}." if c.expirationDate else ""
        
        # Use get_FOO_display() to show "Doctorate Degree" instead of "PhD"
        lines.append(
            f"{c.get_credentialType_display()} - {c.title} ({c.issuer}, {c.dateEarned}).{expiry}"
        )
        
    full_text = "CREDENTIALS:\n" + "\n".join(lines)
    return chunk_text(full_text, max_tokens=max_tokens)

def get_experience_text(instructor, max_tokens=200):
    """
    Updated for InstructorExperience model.
    Removed: isVerified.
    Added: employmentType, isCurrent logic.
    """
    experiences = instructor.experiences.all()
    if not experiences.exists():
        return []

    lines = []
    for e in experiences:
        end_date = "Present" if e.isCurrent else str(e.endDate)
        
        # Format: "Industry (Full Time): Senior Dev at Google (San Francisco). 2020-01-01 to Present."
        lines.append(
            f"{e.get_experienceType_display()} ({e.get_employmentType_display()}): "
            f"{e.title} at {e.organization} {f'({e.location})' if e.location else ''}. "
            f"Period: {e.startDate} to {end_date}. "
            f"Details: {e.description or 'N/A'}"
        )

    full_text = "PROFESSIONAL EXPERIENCE:\n" + "\n".join(lines)
    return chunk_text(full_text, max_tokens=max_tokens)

def get_subject_text(subject, max_tokens=200):
    """
    Generates text for the Target Subject being compared against.
    """
    description = subject.description or 'No description available.'
    topics = subject.subjectTopics or 'No topics listed.'
    
    full_text = (
        f"TARGET SUBJECT:\n"
        f"Code: {subject.code} - {subject.name}.\n"
        f"Description: {description}\n"
        f"Topics: {topics}"
    )
    return chunk_text(full_text, max_tokens=max_tokens)

def build_instructor_text_profile(instructor, subject, max_tokens=200):
    """
    Main entry point. Generates (Instructor Chunk, Subject Chunk) pairs.
    """
    # 1. Get the Subject Text (The "Query" or "Anchor")
    subject_chunks = get_subject_text(subject, max_tokens)
    if not subject_chunks:
        return []
    
    # We typically just use the first chunk of the subject description 
    # as the anchor for comparison, assuming subject descriptions aren't massive.
    subject_anchor = subject_chunks[0]

    # 2. Get All Instructor Profile Text Chunks
    profile_chunks = []
    profile_chunks += get_teaching_text(instructor, max_tokens)
    profile_chunks += get_experience_text(instructor, max_tokens)
    profile_chunks += get_credentials_text(instructor, max_tokens)

    # 3. Create Pairs for the Cross-Encoder
    # The model expects [[text1_A, text2], [text1_B, text2], ...]
    paired_chunks = [(chunk, subject_anchor) for chunk in profile_chunks]
    
    return paired_chunks