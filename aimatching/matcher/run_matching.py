from django.db import transaction
from scheduling.models import Semester, Subject
from core.models import Instructor
from aimatching.matcher.data_extractors import (
    get_teaching_text,
    get_credentials_text,
    get_experience_text,
    get_preference_text,
    get_subject_text,
)
from aimatching.matcher.explain_match import generate_mistral_explanation
from sentence_transformers import CrossEncoder
from aimatching.models import (
    InstructorSubjectMatch,
    InstructorSubjectMatchHistory,
    MatchingConfig,
    MatchingProgress,
)
from scipy.special import softmax

import numpy as np
import logging

logger = logging.getLogger(__name__)

cross_encoder = CrossEncoder("cross-encoder/nli-deberta-v3-large")

def get_scores(text_a, list_of_text_b):
    for b in list_of_text_b:
        if not isinstance(b, str):
            print(f"[Warning] Non-str detected in pair: {text_a=} {b=}")
    pairs = [(str(text_a), str(b) if b is not None else "") for b in list_of_text_b]
    return cross_encoder.predict(pairs)

def extract_entailment_prob(scores):
    if scores is None or len(scores) == 0:
        return 0.0
    scores = np.array(scores)
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)
    entail_probs = [softmax(row)[1] for row in scores]  # [1] = entailment class
    return float(max(entail_probs))




def run_matching(semester_id, batch_id, generated_by=None):
    from aimatching.tasks import notify_progress

    semester = Semester.objects.get(pk=semester_id)
    term_map = {"1st": 0, "2nd": 1, "Midyear": 2, "Summer": 2}
    term_value = term_map.get(semester.term)

    subjects = Subject.objects.filter(defaultTerm=term_value, isActive=True)
    instructors = Instructor.objects.all()

    try:
        config = MatchingConfig.objects.get(semester=semester)
        weights = {
            "teaching": config.teachingWeight,
            "credentials": config.credentialsWeight,
            "experience": config.experienceWeight,
            "preference": config.preferenceWeight,
        }
    except MatchingConfig.DoesNotExist:
        weights = {"teaching": 0.2, "credentials": 0.3, "experience": 0.3, "preference": 0.2}

    progress = MatchingProgress.objects.get(batchId=batch_id)

    total_tasks = subjects.count() * instructors.count()
    completed_tasks = 0

    for subject in subjects:
        subject_text = get_subject_text(subject)

        for instructor in instructors:
            teaching_text = get_teaching_text(instructor)
            credentials_text = get_credentials_text(instructor)
            experience_text = get_experience_text(instructor)
            preference_text = get_preference_text(instructor, subject)

            teaching_scores = get_scores(subject_text, teaching_text)
            credential_scores = get_scores(subject_text, credentials_text)
            experience_scores = get_scores(subject_text, experience_text)
            preference_scores = get_scores(subject_text, preference_text)

            logger.info(f"TEACHING RAW scores: {teaching_scores}")
            logger.info(f"CREDENTIAL RAW scores: {credential_scores}")
            logger.info(f"EXPERIENCE RAW scores: {experience_scores}")
            logger.info(f"PREFERENCE RAW scores: {preference_scores}")

            teaching_score = extract_entailment_prob(teaching_scores)
            credential_score = extract_entailment_prob(credential_scores)
            experience_score = extract_entailment_prob(experience_scores)
            preference_score = extract_entailment_prob(preference_scores)


            confidence_score = (
                teaching_score * weights["teaching"]
                + credential_score * weights["credentials"]
                + experience_score * weights["experience"]
                + preference_score * weights["preference"]
            )

            factors = {
                "Teaching": teaching_score,
                "Credentials": credential_score,
                "Experience": experience_score,
                "Preference": preference_score,
            }
            primary_factor = max(factors, key=factors.get)

            # explanation = generate_mistral_explanation(
            #     subject,
            #     instructor,
            #     instructor.full_name,
            #     factors,
            #     confidence_score,
            #     f"Primary factor: {primary_factor}"
            # )

            explanation = (
                f"{instructor.full_name} is matched with {subject.name}. "
                f"This decision prioritizes their strongest area: {primary_factor}. "
                f"AI-generated detailed explanation is currently disabled for faster matching."
            )

            with transaction.atomic():
                history = InstructorSubjectMatchHistory.objects.create(
                    instructor=instructor,
                    subject=subject,
                    confidenceScore=confidence_score,
                    teachingScore=teaching_score,
                    credentialScore=credential_score,
                    experienceScore=experience_score,
                    preferenceScore=preference_score,
                    primaryFactor=primary_factor,
                    explanation=explanation,
                    modelVersion="crossenc-nli-deberta-v3-large",
                    batchId=batch_id,
                    generatedBy=generated_by,
                )

                match, _ = InstructorSubjectMatch.objects.get_or_create(
                    instructor=instructor,
                    subject=subject,
                    defaults={
                        "batchId": batch_id,
                        "modelVersion": "crossenc-nli-deberta-v3-large",
                        "generatedBy": generated_by,
                    }
                )
                match.latestHistory = history
                match.batchId = batch_id
                match.modelVersion = "crossenc-nli-deberta-v3-large"
                match.generatedBy = generated_by
                match.save()

            completed_tasks += 1
            progress.completedTasks = completed_tasks
            if completed_tasks >= total_tasks:
                progress.status = "completed"
            progress.save(update_fields=["completedTasks", "status"])
            notify_progress(batch_id, progress)

    return True
