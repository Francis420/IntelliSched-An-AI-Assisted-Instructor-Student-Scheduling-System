import spacy
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from instructors.models import InstructorSubjectPreference

# ✅ Load spaCy model once
nlp = spacy.load("en_core_web_sm")

# ✅ Skill/topic clusters (customize as needed)
SKILL_CLUSTERS = {
    "Project Management": {"project", "capstone", "management", "timeline", "milestone"},
    "Object-Oriented Programming": {"object", "oriented", "oop", "class", "inheritance"},
    "Web Development": {"html", "css", "javascript", "react", "web", "frontend", "backend"},
    "Data Science": {"data", "analysis", "statistics", "machine", "learning", "visualization"},
    "Database Systems": {"sql", "database", "schema", "query", "relational"},
    "Networking": {"network", "protocol", "tcp", "ip", "routing", "cybersecurity"},
    "Software Engineering": {"software", "testing", "agile", "scrum", "development"},
    "Internship / Practicum": {"practicum", "hours", "work", "supervision", "deployment", "company"},
}

# ✅ Extract noun phrases from text
def extract_noun_phrases(text):
    doc = nlp(text)
    return [chunk.text.lower().strip() for chunk in doc.noun_chunks if chunk.text.lower() not in ENGLISH_STOP_WORDS]

# ✅ Map extracted phrases to predefined skill clusters
def map_phrases_to_clusters(phrases):
    matched_clusters = set()
    for phrase in phrases:
        for cluster, keywords in SKILL_CLUSTERS.items():
            for keyword in keywords:
                if keyword in phrase:
                    matched_clusters.add(cluster)
    return list(matched_clusters)

# ✅ Main explanation function with phrase + cluster support
def explain_match(instructor, subject, model, vectorizer):
    # Combine instructor + subject text
    from aimatching.helpers import gatherInstructorText
    from aimatching.models import InstructorSubjectPreference

    pair_text = gatherInstructorText(instructor) + "\n" + (
        f"Subject: {subject.code} - {subject.name}\nDescription: {subject.subjectTopics or subject.description or ''}"
    )

    # ✨ STEP 2: Phrase extraction + cluster mapping
    phrases = extract_noun_phrases(pair_text)
    clusters = map_phrases_to_clusters(phrases)

    # STEP 3: Preference / history signals
    taught = instructor.teachingHistory.filter(subject=subject).exists()
    preferred = InstructorSubjectPreference.objects.filter(
        instructor=instructor, subject=subject, preferenceType='Prefer'
    ).exists()

    # STEP 4: Reason construction
    reasons = []
    if taught:
        reasons.append("previously taught this subject")
    if preferred:
        reasons.append("expressed preference for this subject")
    if clusters:
        reasons.append("strong alignment with topics like " + ", ".join(clusters))
    elif phrases:
        reasons.append("content similarity based on key concepts")

    reason_str = "; ".join(reasons) if reasons else "matched by content similarity"
    concept_str = ", ".join(phrases[:5]) if phrases else "N/A"

    return f"""🧠 Reason:
• Match basis: {reason_str}
• Key concepts: {concept_str}"""
