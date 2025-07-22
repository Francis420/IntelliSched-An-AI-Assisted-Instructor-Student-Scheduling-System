# from django.core.management.base import BaseCommand
# from django.db import transaction
# from core.models import Instructor
# from scheduling.models import Subject
# from instructors.models import (
#     InstructorExperience,
#     InstructorCredentials,
#     InstructorSubjectPreference,
#     TeachingHistory
# )
# from aimatching.models import InstructorSubjectMatch
# from aimatching.tfidf import loadTfidfSvmModel


# def gatherInstructorText(instructor):
#     text_parts = []

#     experiences = InstructorExperience.objects.filter(instructor=instructor)
#     credentials = InstructorCredentials.objects.filter(instructor=instructor)
#     preferences = InstructorSubjectPreference.objects.filter(instructor=instructor)
#     teaching_history = TeachingHistory.objects.filter(instructor=instructor)

#     for exp in experiences:
#         text_parts.append(exp.title or "")
#         text_parts.append(exp.description or "")

#     for cred in credentials:
#         text_parts.append(cred.title or "")
#         text_parts.append(cred.description or "")

#     for pref in preferences:
#         text_parts.append(pref.preferenceType or "")
#         text_parts.append(pref.reason or "")

#     for history in teaching_history:
#         text_parts.append(f"Taught {history.subject.code} {history.timesTaught} times")

#     return " ".join(text_parts).strip()


# class Command(BaseCommand):
#     help = "Generate top 5 instructor-subject matches using the trained AI model"

#     def handle(self, *args, **kwargs):
#         model = loadTfidfSvmModel()

#         if model is None:
#             self.stdout.write(self.style.ERROR("❌ Trained model not found. Run `train_match_model` first."))
#             return

#         subject_qs = Subject.objects.all()
#         subjects = {sub.code: sub for sub in subject_qs}

#         total_created = 0
#         total_skipped = 0

#         for instructor in Instructor.objects.all():
#             input_text = gatherInstructorText(instructor)

#             if not input_text:
#                 self.stdout.write(f"⚠️ Skipped instructor {instructor.user.fullName} (no data).")
#                 total_skipped += 1
#                 continue

#             # Get decision scores for all subjects
#             if not hasattr(model.named_steps['svm'], "classes_"):
#                 self.stdout.write("❌ Model does not support probability prediction.")
#                 return

#             vectorized = model.named_steps['tfidf'].transform([input_text])
#             decision_scores = model.named_steps['svm'].decision_function(vectorized)

#             # Pair with subject codes and sort by score
#             top_indices = decision_scores.argsort()[::-1][:5]
#             top_scores = decision_scores[top_indices]
#             top_subject_codes = model.named_steps['svm'].classes_[top_indices]

#             with transaction.atomic():
#                 for code, score in zip(top_subject_codes, top_scores):
#                     subject = subjects.get(code)
#                     if subject:
#                         match, created = InstructorSubjectMatch.objects.update_or_create(
#                             instructor=instructor,
#                             subject=subject,
#                             defaults={"score": float(score)}
#                         )
#                         if created:
#                             total_created += 1
#                             self.stdout.write(f"✅ Matched {instructor.user.fullName} → {subject.code} (score: {score:.4f})")
#                         else:
#                             self.stdout.write(f"🔁 Updated {instructor.user.fullName} → {subject.code} (score: {score:.4f})")
#                     else:
#                         self.stdout.write(f"❓ Predicted subject '{code}' not found in database.")

#         self.stdout.write(self.style.SUCCESS(f"🎯 Finished. Matches created or updated: {total_created}, Skipped: {total_skipped}"))


from django.core.management.base import BaseCommand
from aimatching.match import generateMatchSuggestions
from core.models import UserLogin, User, Instructor
from scheduling.models import Subject
from aimatching.models import InstructorSubjectMatch

class Command(BaseCommand):
    help = 'Generate instructor-subject matches using AI model (Levels 1, 2, 3)'

    def handle(self, *args, **kwargs):
        self.stdout.write("🧹 Deleting old matches...")
        InstructorSubjectMatch.objects.all().delete()

        self.stdout.write("🔍 Generating match suggestions...")
        results = generateMatchSuggestions()
        print("🪵 DEBUG: Raw match results =", results)  # Debug line

        system_user = User.objects.filter(username='sysadmin').first()

        total_created = 0
        for instructor, matches, level in results:
            login = UserLogin.objects.filter(instructor=instructor).first()
            full_name = f"{login.user.firstName} {login.user.lastName}" if login and login.user else str(instructor.instructorId)

            self.stdout.write(f"👤 Matched instructor {full_name} using level {level} (matches: {len(matches)})")

            for subject, score in matches:
                self.stdout.write(f"  📘 {subject.code} ({score:.3f})")

                InstructorSubjectMatch.objects.create(
                    instructor=instructor,
                    subject=subject,
                    matchScore=score,
                    matchLevel=level,
                    primaryFactor="tfidf" if level == 1 else "svm",
                    experienceScore=0.0,
                    teachingScore=0.0,
                    credentialScore=0.0,
                    availabilityScore=0.0,
                    generatedBy=system_user
                )
                total_created += 1

        # Dummy fallback test if no results were created
        if total_created == 0:
            self.stdout.write("⚠️ No matches created. Running dummy test save...")
            if Instructor.objects.exists() and Subject.objects.exists():
                InstructorSubjectMatch.objects.create(
                    instructor=Instructor.objects.first(),
                    subject=Subject.objects.first(),
                    matchScore=0.99,
                    matchLevel=9,
                    primaryFactor="test",
                    experienceScore=1.0,
                    teachingScore=1.0,
                    credentialScore=1.0,
                    availabilityScore=1.0,
                    generatedBy=system_user
                )
                self.stdout.write("✅ Dummy test match saved.")
            else:
                self.stdout.write("🚫 Dummy test failed: no instructors or subjects available.")

        self.stdout.write(self.style.SUCCESS(f"🏁 Done. Total instructors processed: {len(results)}"))






