from InstructorEmbedding import INSTRUCTOR
import torch
from sentence_transformers import CrossEncoder
import numpy as np
from aimatching.models import MatchingConfig

_model = None
_cross_encoder = None

INSTRUCTIONS = {
    "subject": "Embed this IT course subject to find suitable instructors",
    "teaching": "Embed this instructor's past teaching subjects for relevance to an IT course",
    "credentials": "Embed this instructor's academic and professional qualifications for teaching IT",
    "experience": "Embed this instructor's relevant work experience for teaching an IT subject",
    "preference": "Embed this instructor's preferred IT subjects to teach"
} #make this editable in the admin panel

def get_model():
    global _model
    if _model is None:
        _model = INSTRUCTOR('hkunlp/instructor-xl')
        _model.to("cuda" if torch.cuda.is_available() else "cpu")
    return _model

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')
    return _cross_encoder

def get_embedding(text, instruction=None):
    if not text:
        return np.zeros(768)
    if instruction is None:
        instruction = INSTRUCTIONS["subject"]
    model = get_model()
    return model.encode([[instruction, text]])

def get_model_scores(teaching, credentials, experience, preference, subject_text, semester=None):
    from aimatching.models import MatchingConfig

    cross_encoder = get_cross_encoder()

    config = MatchingConfig.objects.filter(semester=semester, active=True).order_by('-createdAt').first()
    if not config:
        # fallback defaults
        weights = {"teaching": 0.2, "credentials": 0.3, "experience": 0.3, "preference": 0.2}
        threshold = 0.6
    else:
        weights = {
            "teaching": config.teachingWeight,
            "credentials": config.credentialWeight,
            "experience": config.experienceWeight,
            "preference": config.preferenceWeight,
        }
        threshold = config.threshold

    pairs = [
        (teaching, subject_text),
        (credentials, subject_text),
        (experience, subject_text),
        (preference, subject_text),
    ]
    raw_scores = cross_encoder.predict(pairs)
    scores = np.clip(raw_scores, 0, 1)

    teaching_score = float(scores[0])
    credential_score = float(scores[1])
    experience_score = float(scores[2])
    preference_score = float(scores[3])

    final_score = (
        teaching_score * weights["teaching"] +
        credential_score * weights["credentials"] +
        experience_score * weights["experience"] +
        preference_score * weights["preference"]
    )

    factor_map = {
        teaching_score: "Teaching",
        credential_score: "Credentials",
        experience_score: "Experience",
        preference_score: "Preference",
    }
    primary_factor = factor_map[max([teaching_score, credential_score, experience_score, preference_score])]

    if final_score >= 0.8:
        match_level = 3
    elif final_score >= 0.6:
        match_level = 2
    elif final_score >= 0.4:
        match_level = 1
    else:
        match_level = 0

    return {
        "teaching": teaching_score,
        "credentials": credential_score,
        "experience": experience_score,
        "preference": preference_score,
        "final": final_score,
        "primaryFactor": primary_factor,
        "level": match_level,
        "threshold": threshold
    }