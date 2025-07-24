from .embedding_utils import get_embedding
from sklearn.metrics.pairwise import cosine_similarity
from .data_extractors import (
    get_teaching_text,
    get_credentials_text,
    get_experience_text,
    get_preference_text,
)


def match_instructors_to_subject(subject, instructors, weights=None):
    if weights is None:
        weights = {
            "teaching": 0.3,
            "credentials": 0.25,
            "experience": 0.25,
            "preference": 0.2,
        }

    subject_text = f"{subject.description or ''} {subject.subjectTopics or ''}"
    subject_vec = get_embedding(subject_text)

    results = []
    for instructor in instructors:
        breakdown = {}

        # Teaching History
        teaching_text = get_teaching_text(instructor)
        teaching_vec = get_embedding(teaching_text)
        teaching_score = cosine_similarity([teaching_vec], [subject_vec])[0][0]
        breakdown["teaching"] = teaching_score

        # Credentials
        cred_text = get_credentials_text(instructor)
        cred_vec = get_embedding(cred_text)
        cred_score = cosine_similarity([cred_vec], [subject_vec])[0][0]
        breakdown["credentials"] = cred_score

        # Experiences
        exp_text = get_experience_text(instructor)
        exp_vec = get_embedding(exp_text)
        exp_score = cosine_similarity([exp_vec], [subject_vec])[0][0]
        breakdown["experience"] = exp_score

        # Preferences
        pref_text = get_preference_text(instructor)
        pref_vec = get_embedding(pref_text)
        pref_score = cosine_similarity([pref_vec], [subject_vec])[0][0]
        breakdown["preference"] = pref_score

        # Weighted Total
        total_score = (
            weights["teaching"] * teaching_score +
            weights["credentials"] * cred_score +
            weights["experience"] * exp_score +
            weights["preference"] * pref_score
        )

        results.append((instructor, total_score, breakdown))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
