from .embedding_utils import get_embedding
from sklearn.metrics.pairwise import cosine_similarity
from .data_extractors import (
    get_teaching_text,
    get_credentials_text,
    get_experience_text,
    get_preference_text,
    get_subject_text,
)

def match_instructors_to_subject(subject, instructors, weights=None):
    if weights is None:
        weights = {
            "teaching": 0.3,
            "credentials": 0.25,
            "experience": 0.25,
            "preference": 0.2,
        }

    subject_text = get_subject_text(subject)
    if not subject_text.strip():
        return []

    subject_vec = get_embedding(subject_text, "Represent this IT subject")

    results = []
    for instructor in instructors:
        breakdown = {}

        teaching_text = get_teaching_text(instructor)
        cred_text = get_credentials_text(instructor)
        exp_text = get_experience_text(instructor)
        pref_text = get_preference_text(instructor)

        if not any([teaching_text, cred_text, exp_text, pref_text]):
            continue

        teaching_vec = get_embedding(teaching_text, "Represent this instructor's teaching history")
        cred_vec = get_embedding(cred_text, "Represent this instructor's credentials")
        exp_vec = get_embedding(exp_text, "Represent this instructor's experience")
        pref_vec = get_embedding(pref_text, "Represent this instructor's subject preference")

        breakdown["teaching"] = cosine_similarity([subject_vec], [teaching_vec])[0][0]
        breakdown["credentials"] = cosine_similarity([subject_vec], [cred_vec])[0][0]
        breakdown["experience"] = cosine_similarity([subject_vec], [exp_vec])[0][0]
        breakdown["preference"] = cosine_similarity([subject_vec], [pref_vec])[0][0]

        total_score = (
            weights["teaching"] * breakdown["teaching"] +
            weights["credentials"] * breakdown["credentials"] +
            weights["experience"] * breakdown["experience"] +
            weights["preference"] * breakdown["preference"]
        )

        results.append({
            "instructor": instructor,
            "total_score": total_score,
            "breakdown": breakdown
        })

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results
