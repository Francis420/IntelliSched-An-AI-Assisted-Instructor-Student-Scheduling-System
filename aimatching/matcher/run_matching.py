from django.db import transaction
from scheduling.models import Semester, Subject
from core.models import Instructor
from aimatching.matcher.data_extractors import (
    get_teaching_text,
    get_credentials_text,
    get_experience_text,
    get_subject_text,
)
# from aimatching.matcher.explain_match import generate_mistral_explanation
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

# Initialize model once
cross_encoder = CrossEncoder("cross-encoder/nli-deberta-v3-large")

def get_scores(text_a, list_of_text_b):
    """
    Compares anchor text_a (string) against a list of candidate chunks (list_of_text_b).
    """
    # Validation: list_of_text_b must be a list
    if not list_of_text_b:
        return []
        
    for b in list_of_text_b:
        if not isinstance(b, str):
            logger.warning(f"[Non-str detected in pair] text_a={text_a} b={b}")
            
    # Create pairs: (Subject Anchor, Instructor Chunk)
    pairs = [(str(text_a), str(b) if b is not None else "") for b in list_of_text_b]
    
    # Predict returns an array of scores
    return cross_encoder.predict(pairs)

def extract_entailment_prob(scores):
    """
    Extracts the highest entailment probability from a list of chunk scores.
    """
    if scores is None or len(scores) == 0:
        return 0.0
    
    scores = np.array(scores)
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)
        
    # Index 1 is 'Entailment' in NLI models (Contradiction, Entailment, Neutral) 
    # OR (Contradiction, Neutral, Entailment) depending on model.
    # For 'cross-encoder/nli-deberta-v3-large', label mapping is usually:
    # 0: Contradiction, 1: Entailment, 2: Neutral (Check model card if unsure, usually 1 is entailment for binary)
    # Actually, for standard NLI, it is often: 0: Contradiction, 1: Entailment, 2: Neutral
    # We assume Index 1 is Entailment based on your previous code.
    entail_probs = [softmax(row)[1] for row in scores] 
    return float(max(entail_probs))

def run_matching(semester_id, batch_id, generated_by=None):
    from aimatching.tasks import notify_progress

    semester = Semester.objects.get(pk=semester_id)
    # Map semester terms to integers (matches your Subject model defaults)
    term_map = {"1st": 0, "2nd": 1, "Midyear": 2, "Summer": 2}
    term_value = term_map.get(semester.term)

    # Filter subjects active in this term
    subjects = Subject.objects.filter(defaultTerm=term_value, isActive=True)
    instructors = Instructor.objects.all()

    # Load configuration weights
    try:
        config = MatchingConfig.objects.get(semester=semester)
        weights = {
            "teaching": config.teachingWeight,
            "credentials": config.credentialsWeight,
            "experience": config.experienceWeight,
        }
    except MatchingConfig.DoesNotExist:
        # Default fallback
        weights = {"teaching": 0.2, "credentials": 0.3, "experience": 0.3}

    # Get progress tracker
    progress = MatchingProgress.objects.get(batchId=batch_id)

    total_tasks = subjects.count() * instructors.count()
    completed_tasks = 0

    for subject in subjects:
        # 1. Get Subject Text
        # UPDATE: get_subject_text now returns a LIST of chunks.
        # We take the first chunk as the "Anchor" for comparison.
        subject_chunks = get_subject_text(subject)
        subject_anchor = subject_chunks[0] if subject_chunks else ""

        if not subject_anchor:
            logger.warning(f"Subject {subject.code} has no text description. Skipping.")
            continue

        for instructor in instructors:
            # Check cancel flag
            progress.refresh_from_db()
            if getattr(progress, "cancel_requested", False):
                progress.status = "cancelled"
                progress.save(update_fields=["status"])
                notify_progress(
                    batch_id,
                    progress,
                    current_instructor=None,
                    current_subject=None,
                    subject_count=subjects.count(),
                    instructor_count=instructors.count(),
                    total_tasks=total_tasks,
                )
                return False

            # 2. Extract Data (Returns lists of chunks)
            teaching_text_list = get_teaching_text(instructor)
            credentials_text_list = get_credentials_text(instructor)
            experience_text_list = get_experience_text(instructor)

            # 3. Get Scores (Subject vs List of Chunks)
            teaching_scores = get_scores(subject_anchor, teaching_text_list)
            credential_scores = get_scores(subject_anchor, credentials_text_list)
            experience_scores = get_scores(subject_anchor, experience_text_list)

            # 4. Extract Max Entailment Probability
            teaching_score = extract_entailment_prob(teaching_scores)
            credential_score = extract_entailment_prob(credential_scores)
            experience_score = extract_entailment_prob(experience_scores)

            # 5. Weighted Calculation
            confidence_score = (
                teaching_score * weights["teaching"]
                + credential_score * weights["credentials"]
                + experience_score * weights["experience"]
            )

            # 6. Determine Primary Factor
            factors = {
                "Teaching": teaching_score,
                "Credentials": credential_score,
                "Experience": experience_score,
            }
            primary_factor = max(factors, key=factors.get)

            # 7. Explanation Logic (Simplified)
            # We join the chunks back together to store as evidence text
            factor_evidence_map = {
                "Teaching": "\n".join(teaching_text_list),
                "Credentials": "\n".join(credentials_text_list),
                "Experience": "\n".join(experience_text_list),
            }
            primary_evidence = factor_evidence_map.get(primary_factor, "")
            
            # Placeholder for future LLM explanation
            explanation = "<Explanation generation is temporarily disabled>"

            # 8. Save Results
            with transaction.atomic():
                history = InstructorSubjectMatchHistory.objects.create(
                    instructor=instructor,
                    subject=subject,
                    confidenceScore=confidence_score,
                    teachingScore=teaching_score,
                    credentialScore=credential_score,
                    experienceScore=experience_score,
                    preferenceScore=0.0, # Deprecated
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

            # 9. Update Progress
            completed_tasks += 1
            progress.completedTasks = completed_tasks
            
            if completed_tasks >= total_tasks:
                progress.status = "completed"
            
            # Save progress periodically or at end
            progress.save(update_fields=["completedTasks", "status"])
            
            # Notify UI (Consider adding a throttle here if too slow)
            notify_progress(
                batch_id,
                progress,
                current_instructor=instructor.full_name,
                current_subject=subject.name,
                subject_count=subjects.count(),
                instructor_count=instructors.count(),
                total_tasks=total_tasks
            )
            
    return True


# # Generate explanation using Mistral
            # explanation = generate_mistral_explanation(
            #     subject,
            #     instructor,
            #     instructor.full_name,
            #     primary_factor,
            #     factors[primary_factor],
            #     primary_evidence
            # )