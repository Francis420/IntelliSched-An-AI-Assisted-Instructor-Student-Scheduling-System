from .embedding_utils import get_embedding
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from .data_extractors import (
    get_teaching_text,
    get_experience_text,
    get_credentials_text,
    get_preference_text,
)

def explain_match(subject_text, instructor, score=None):
    """
    Generate a natural explanation for a subject–instructor match.
    `subject_text` is raw preprocessed text from the subject.
    `instructor` is an Instructor instance.
    """
    explanation = ""

    # Score-based reasoning
    if score is not None:
        if score >= 0.80:
            explanation += "✅ Strong match — the instructor has highly relevant experience.\n"
        elif score >= 0.60:
            explanation += "🟡 Moderate match — some overlapping skills and background.\n"
        elif score >= 0.40:
            explanation += "⚠️ Weak match — partial relevance based on background.\n"
        else:
            explanation += "❌ Poor match — very limited alignment found.\n"

    # ✅ Build instructor profile text using extractors
    full_instructor_text = " ".join([
        get_teaching_text(instructor),
        get_experience_text(instructor),
        get_credentials_text(instructor),
        get_preference_text(instructor),
    ])

    # Keyword overlap (very naive)
    subject_keywords = extract_keywords(subject_text)
    instructor_keywords = extract_keywords(full_instructor_text)

    shared = subject_keywords.intersection(instructor_keywords)
    if shared:
        explanation += f"Overlapping concepts: {', '.join(shared)}\n"

    return explanation.strip()


def extract_keywords(text):
    """
    Naive keyword extractor — can be replaced with spaCy, RAKE, etc.
    """
    import re
    tokens = re.findall(r'\b\w{4,}\b', text.lower())  # 4+ character words
    return set(tokens)
