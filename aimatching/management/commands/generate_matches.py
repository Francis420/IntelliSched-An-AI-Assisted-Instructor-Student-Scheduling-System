from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Instructor
from scheduling.models import Subject
from instructors.models import (
    InstructorExperience,
    InstructorCredentials,
    InstructorSubjectPreference,
    TeachingHistory
)
from aimatching.models import InstructorSubjectMatch
from aimatching.tfidf import loadTfidfSvmModel


def gatherInstructorText(instructor):
    text_parts = []

    experiences = InstructorExperience.objects.filter(instructor=instructor)
    credentials = InstructorCredentials.objects.filter(instructor=instructor)
    preferences = InstructorSubjectPreference.objects.filter(instructor=instructor)
    teaching_history = TeachingHistory.objects.filter(instructor=instructor)

    for exp in experiences:
        text_parts.append(exp.title or "")
        text_parts.append(exp.description or "")

    for cred in credentials:
        text_parts.append(cred.title or "")
        text_parts.append(cred.description or "")

    for pref in preferences:
        text_parts.append(pref.preferenceType or "")
        text_parts.append(pref.reason or "")

    for history in teaching_history:
        text_parts.append(f"Taught {history.subject.code} {history.timesTaught} times")

    return " ".join(text_parts).strip()


class Command(BaseCommand):
    help = "Generate top 5 instructor-subject matches using the trained AI model"

    def handle(self, *args, **kwargs):
        model = loadTfidfSvmModel()

        if model is None:
            self.stdout.write(self.style.ERROR("❌ Trained model not found. Run `train_match_model` first."))
            return

        subject_qs = Subject.objects.all()
        subjects = {sub.code: sub for sub in subject_qs}

        total_created = 0
        total_skipped = 0

        for instructor in Instructor.objects.all():
            input_text = gatherInstructorText(instructor)

            if not input_text:
                self.stdout.write(f"⚠️ Skipped instructor {instructor.user.fullName} (no data).")
                total_skipped += 1
                continue

            # Get decision scores for all subjects
            if not hasattr(model.named_steps['svm'], "classes_"):
                self.stdout.write("❌ Model does not support probability prediction.")
                return

            vectorized = model.named_steps['tfidf'].transform([input_text])
            decision_scores = model.named_steps['svm'].decision_function(vectorized)

            # Pair with subject codes and sort by score
            top_indices = decision_scores.argsort()[::-1][:5]
            top_scores = decision_scores[top_indices]
            top_subject_codes = model.named_steps['svm'].classes_[top_indices]

            with transaction.atomic():
                for code, score in zip(top_subject_codes, top_scores):
                    subject = subjects.get(code)
                    if subject:
                        match, created = InstructorSubjectMatch.objects.update_or_create(
                            instructor=instructor,
                            subject=subject,
                            defaults={"score": float(score)}
                        )
                        if created:
                            total_created += 1
                            self.stdout.write(f"✅ Matched {instructor.user.fullName} → {subject.code} (score: {score:.4f})")
                        else:
                            self.stdout.write(f"🔁 Updated {instructor.user.fullName} → {subject.code} (score: {score:.4f})")
                    else:
                        self.stdout.write(f"❓ Predicted subject '{code}' not found in database.")

        self.stdout.write(self.style.SUCCESS(f"🎯 Finished. Matches created or updated: {total_created}, Skipped: {total_skipped}"))
