# aimatching/tasks/run_matching.py
from django.db import transaction
from scheduling.models import Semester, Subject
from core.models import Instructor
from aimatching.models import (
    InstructorSubjectMatch,
    InstructorSubjectMatchHistory,
    MatchingProgress,
    MatchingConfig
)

# Import the individual functions from your simplified extractor
from aimatching.matcher.data_extractors import (
    split_text_by_words,
    get_teaching_history_text,
    get_experience_text,
    get_credentials_text,
    get_target_subject_text
)

from sentence_transformers import CrossEncoder
from scipy.special import softmax
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Initialize model once (Global)
cross_encoder = CrossEncoder("cross-encoder/nli-deberta-v3-large")

# ==========================================
# HELPER: Get Score for a List of Chunks
# ==========================================
def calculate_category_score(text_chunks, subject_anchor):
    """
    Compares a list of text chunks (e.g., experience history) against the subject.
    Returns the highest match probability found (0.0 to 1.0).
    """
    # If no text in this category, score is 0
    if not text_chunks:
        return 0.0

    # Create pairs: [ [Chunk1, Subject], [Chunk2, Subject] ... ]
    pairs = []
    for chunk in text_chunks:
        if chunk.strip():
            pairs.append([chunk, subject_anchor])
            
    if not pairs:
        return 0.0

    # Predict
    scores = cross_encoder.predict(pairs)
    
    # Convert to probability (Softmax)
    # If single pair, reshape to ensure 2D array
    scores = np.array(scores)
    if scores.ndim == 1:
        scores = scores.reshape(1, -1)

    # column 1 is 'Entailment' (Match)
    entail_probs = [softmax(row)[1] for row in scores]
    
    # Return the best single chunk score
    return float(max(entail_probs))


# ==========================================
# MAIN MATCHING LOGIC
# ==========================================
def run_matching(semester_id, batch_id, generated_by=None):
    from aimatching.tasks import notify_progress 

    # 1. Setup Data & Weights
    semester = Semester.objects.get(pk=semester_id)
    
    # --- FIX: Safe Config Loading (Matches your old code) ---
    try:
        config = MatchingConfig.objects.get(semester=semester)
        # We use the values from the database
        w_teaching = config.teachingWeight
        w_experience = config.experienceWeight
        w_credentials = config.credentialsWeight  # Plural 'credentials' matched to your DB
    except MatchingConfig.DoesNotExist:
        # Default fallback if no config exists for this semester
        logger.warning(f"No MatchingConfig found for semester {semester_id}. Using defaults.")
        w_teaching = 0.5
        w_experience = 0.3
        w_credentials = 0.2

    # Map semester terms
    term_map = {"1st": 0, "2nd": 1, "Midyear": 2, "Summer": 2}
    term_value = term_map.get(semester.term, 0)

    # Get active subjects & instructors
    subjects = Subject.objects.filter(defaultTerm=term_value, isActive=True)
    instructors = Instructor.objects.all()

    # Progress tracking
    progress = MatchingProgress.objects.get(batchId=batch_id)
    total_tasks = subjects.count() * instructors.count()
    completed_tasks = 0

    # 2. Main Loop
    for subject in subjects:
        
        # Prepare Subject Anchor (Do this once per subject to save time)
        subject_text_full = get_target_subject_text(subject)
        subject_chunks = split_text_by_words(subject_text_full, max_words=150)
        
        if not subject_chunks:
            # Fallback if description is empty
            subject_anchor = subject.name 
        else:
            # We take the first chunk (first ~150 words) as the main comparison anchor
            subject_anchor = subject_chunks[0]

        for instructor in instructors:
            
            # --- Check Cancellation ---
            progress.refresh_from_db()
            if getattr(progress, "cancel_requested", False):
                progress.status = "cancelled"
                progress.save(update_fields=["status"])
                return False

            # --- A. CALCULATE INDIVIDUAL SCORES ---
            
            # 1. Teaching History
            t_text = get_teaching_history_text(instructor)
            t_chunks = split_text_by_words(t_text)
            score_teaching = calculate_category_score(t_chunks, subject_anchor)

            # 2. Experience
            e_text = get_experience_text(instructor)
            e_chunks = split_text_by_words(e_text)
            score_experience = calculate_category_score(e_chunks, subject_anchor)

            # 3. Credentials
            c_text = get_credentials_text(instructor)
            c_chunks = split_text_by_words(c_text)
            score_credentials = calculate_category_score(c_chunks, subject_anchor)

            # --- B. WEIGHTED AVERAGE ---
            final_score = (
                (score_teaching * w_teaching) +
                (score_experience * w_experience) +
                (score_credentials * w_credentials)
            )

            # Determine Primary Factor (for explanation)
            scores_map = {
                "Teaching History": score_teaching,
                "Professional Experience": score_experience,
                "Credentials": score_credentials
            }
            primary_factor = max(scores_map, key=scores_map.get)
            
            # --- C. SAVE RESULTS ---
            with transaction.atomic():
                history = InstructorSubjectMatchHistory.objects.create(
                    instructor=instructor,
                    subject=subject,
                    batchId=batch_id,
                    generatedBy=generated_by,
                    modelVersion="crossenc-nli-deberta-v3-large",
                    
                    # Final Weighted Score
                    confidenceScore=final_score,
                    
                    # Individual Scores
                    teachingScore=score_teaching,
                    credentialScore=score_credentials, # Note: DB model usually uses singular 'credentialScore'
                    experienceScore=score_experience,
                    
                    primaryFactor=primary_factor, 
                    explanation=f"Matches based primarily on {primary_factor}."
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
                match.confidenceScore = final_score
                match.batchId = batch_id
                match.save()

            # --- D. UPDATE PROGRESS ---
            completed_tasks += 1
            if completed_tasks % 5 == 0:
                progress.completedTasks = completed_tasks
                notify_progress(
                    batch_id, progress,
                    current_instructor=instructor.full_name,
                    current_subject=subject.name,
                    subject_count=subjects.count(),
                    instructor_count=instructors.count(),
                    total_tasks=total_tasks
                )

    # 3. Finish
    progress.completedTasks = total_tasks
    progress.status = "completed"
    progress.save()
    
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