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




# Load CrossEncoder once globally
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-12-v2")


def run_matching(semester_id, batch_id, generated_by=None):
    from aimatching.tasks import notify_progress
    semester = Semester.objects.get(pk=semester_id)

    # ✅ Map semester.term → Subject.defaultTerm
    term_map = {"1st": 0, "2nd": 1, "Midyear": 2}
    term_value = term_map.get(semester.term)

    # ✅ Get subjects active for this semester
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
            preference_text = get_preference_text(instructor)

            pairs = [
                (subject_text, teaching_text),
                (subject_text, credentials_text),
                (subject_text, experience_text),
                (subject_text, preference_text),
            ]
            scores = cross_encoder.predict(pairs)
            teaching_score, credential_score, experience_score, preference_score = scores

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
                f"{instructor.full_name} is considered for {subject.name}. "
                f"Primary factor: {primary_factor}. "
                "AI-generated explanation disabled for now."
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
                    modelVersion="crossenc-v1",
                    batchId=batch_id,
                    generatedBy=generated_by,
                )

                match, _ = InstructorSubjectMatch.objects.get_or_create(
                    instructor=instructor,
                    subject=subject,
                    defaults={
                        "batchId": batch_id,
                        "modelVersion": "crossenc-v1",
                        "generatedBy": generated_by,
                    }
                )
                match.latestHistory = history
                match.batchId = batch_id
                match.modelVersion = "crossenc-v1"
                match.generatedBy = generated_by
                match.save()

            completed_tasks += 1
            progress.completedTasks = completed_tasks
            if completed_tasks >= total_tasks:
                progress.status = "completed"
            progress.save(update_fields=["completedTasks", "status"])
            notify_progress(batch_id, progress)

    return True

