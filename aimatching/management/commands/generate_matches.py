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


#works
# from django.core.management.base import BaseCommand
# from aimatching.match import generateMatchSuggestions
# from core.models import UserLogin, User, Instructor
# from scheduling.models import Subject
# from aimatching.models import InstructorSubjectMatch

# class Command(BaseCommand):
#     help = 'Generate instructor-subject matches using AI model (Levels 1, 2, 3)'

#     def handle(self, *args, **kwargs):
#         self.stdout.write("🧹 Deleting old matches...")
#         InstructorSubjectMatch.objects.all().delete()

#         self.stdout.write("🔍 Generating match suggestions...")
#         results = generateMatchSuggestions()
#         print("🪵 DEBUG: Raw match results =", results)  # Debug line

#         system_user = User.objects.filter(username='sysadmin').first()

#         total_created = 0
#         for instructor, matches, level in results:
#             login = UserLogin.objects.filter(instructor=instructor).first()
#             full_name = f"{login.user.firstName} {login.user.lastName}" if login and login.user else str(instructor.instructorId)

#             self.stdout.write(f"👤 Matched instructor {full_name} using level {level} (matches: {len(matches)})")

#             for subject, score in matches:
#                 self.stdout.write(f"  📘 {subject.code} ({score:.3f})")

#                 InstructorSubjectMatch.objects.create(
#                     instructor=instructor,
#                     subject=subject,
#                     matchScore=score,
#                     matchLevel=level,
#                     primaryFactor="tfidf" if level == 1 else "svm",
#                     experienceScore=0.0,
#                     teachingScore=0.0,
#                     credentialScore=0.0,
#                     availabilityScore=0.0,
#                     generatedBy=system_user
#                 )
#                 total_created += 1

#         # Dummy fallback test if no results were created
#         if total_created == 0:
#             self.stdout.write("⚠️ No matches created. Running dummy test save...")
#             if Instructor.objects.exists() and Subject.objects.exists():
#                 InstructorSubjectMatch.objects.create(
#                     instructor=Instructor.objects.first(),
#                     subject=Subject.objects.first(),
#                     matchScore=0.99,
#                     matchLevel=9,
#                     primaryFactor="test",
#                     experienceScore=1.0,
#                     teachingScore=1.0,
#                     credentialScore=1.0,
#                     availabilityScore=1.0,
#                     generatedBy=system_user
#                 )
#                 self.stdout.write("✅ Dummy test match saved.")
#             else:
#                 self.stdout.write("🚫 Dummy test failed: no instructors or subjects available.")

#         self.stdout.write(self.style.SUCCESS(f"🏁 Done. Total instructors processed: {len(results)}"))


from django.core.management.base import BaseCommand
from scheduling.models import Subject
from instructors.models import Instructor
from aimatching.pairText import generate_pair_text, load_match_model, load_vectorizer
import joblib
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
import re
import numpy as np
from instructors.models import (
    InstructorExperience,
    InstructorCredentials,
    InstructorSubjectPreference,
    TeachingHistory,
)
from scheduling.models import Subject



class Command(BaseCommand):
    help = "Generate instructor-subject matches with reasoning"

    def handle(self, *args, **kwargs):
        model = load_match_model()
        vectorizer = load_vectorizer()
        
        for subject in Subject.objects.filter(isActive=True):
            print(f"\n📘 Subject: [{subject.code}] {subject.name}")
            ranked_instructors = self.rank_instructors_for_subject(subject, model, vectorizer)
            
            for i, (instructor, score, _) in enumerate(ranked_instructors[:10], 1):
                explanation = explain_match(instructor, subject, model, vectorizer)  # ✅ <- this line updated
                print(f"{i}. {instructor.instructorId} - {instructor.full_name} (Score: {score:.2f})")
                print(f"   {explanation}")



    def rank_instructors_for_subject(self, subject, model, vectorizer):
        instructors = Instructor.objects.all()
        predictions = []

        for instructor in instructors:
            pair_text = generate_pair_text(instructor, subject)
            vectorized = vectorizer.transform([pair_text])
            score = model.decision_function(vectorized)[0]

            # Extract top keywords contributing to match
            feature_names = vectorizer.get_feature_names_out()
            tfidf_array = vectorized.toarray()[0]
            top_indices = tfidf_array.argsort()[-5:][::-1]
            top_words = [feature_names[i] for i in top_indices if tfidf_array[i] > 0]
            reasoning = ", ".join(top_words) if top_words else "N/A"

            predictions.append((instructor, score, reasoning))

        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions

def explain_match(instructor, subject, model, vectorizer):
    # Generate combined text from instructor and subject
    pair_text = generate_pair_text(instructor, subject)
    
    # Tokenize and remove stop words
    tokens = vectorizer.build_tokenizer()(pair_text.lower())
    tokens = [t for t in tokens if t not in ENGLISH_STOP_WORDS and t.isalpha()]

    # Get TF-IDF feature names and index mapping
    feature_names = vectorizer.get_feature_names_out()
    feature_index = {word: idx for idx, word in enumerate(feature_names)}

    # Find token weights based on SVM coefficients
    important_tokens = []
    for token in tokens:
        if token in feature_index:
            coef = model.coef_[0][feature_index[token]]
            important_tokens.append((token, coef))

    # Sort by importance
    important_tokens.sort(key=lambda x: x[1], reverse=True)
    top_keywords = [t[0] for t in important_tokens[:5]]

    # Additional reasoning
    taught = instructor.teachingHistory.filter(subject=subject).exists()
    preferred = InstructorSubjectPreference.objects.filter(
        instructor=instructor, subject=subject, preferenceType='Prefer'
    ).exists()

    if taught:
        reason_main = "Previously taught this subject"
    elif preferred:
        reason_main = "Expressed preference for this subject"
    else:
        reason_main = "High content similarity based on relevant keywords"

    keywords_str = ", ".join(top_keywords) if top_keywords else "N/A"

    return (
        f"🧠 Reason:\n"
        f"  • Match basis: {reason_main}\n"
        f"  • Strong keywords: {keywords_str}"
    )

