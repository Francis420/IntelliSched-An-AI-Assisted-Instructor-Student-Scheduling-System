from .embedding_utils import get_embedding
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def explain_match(subject_text, instructor_text, score=None):
    """
    Generate a natural explanation for a subject–instructor match.
    """
    explanation = ""

    # Score-based explanation
    if score is not None:
        if score >= 0.80:
            explanation += "✅ Strong match — the instructor has highly relevant experience.\n"
        elif score >= 0.60:
            explanation += "🟡 Moderate match — some overlapping skills and background.\n"
        elif score >= 0.40:
            explanation += "⚠️ Weak match — partial relevance based on background.\n"
        else:
            explanation += "❌ Poor match — very limited alignment found.\n"

    # Optionally, highlight overlap via simple keyword heuristics
    subject_keywords = extract_keywords(subject_text)
    instructor_keywords = extract_keywords(instructor_text)

    shared = subject_keywords.intersection(instructor_keywords)
    if shared:
        explanation += f"Overlapping concepts: {', '.join(shared)}\n"

    return explanation.strip()

def extract_keywords(text):
    """
    Naive keyword extractor — lowercased alphanumeric noun-like terms.
    Can be replaced later with spaCy or RAKE.
    """
    import re
    tokens = re.findall(r'\b\w{4,}\b', text.lower())  # 4+ letter words
    return set(tokens)
