# from aimatching.matcher.semantic_matcher import match_instructors_to_subject
# from core.models import Instructor
# from scheduling.models import Subject
# from django.core.management.base import BaseCommand
# import numpy as np

# class Command(BaseCommand):
#     help = 'Run improved instructor-subject matching with normalized scores.'

#     def handle(self, *args, **kwargs):
#         subject = Subject.objects.get(code="IT 429")
#         instructors = Instructor.objects.all()

#         matches = match_instructors_to_subject(subject, instructors)

#         # Extract raw component scores
#         raw_teaching = np.array([b['teaching'] for _, _, b in matches])
#         raw_credentials = np.array([b['credentials'] for _, _, b in matches])
#         raw_experience = np.array([b['experience'] for _, _, b in matches])
#         raw_preference = np.array([b['preference'] for _, _, b in matches])

#         def min_max_normalize(arr):
#             min_val = np.min(arr)
#             max_val = np.max(arr)
#             return (arr - min_val) / (max_val - min_val) if max_val > min_val else np.zeros_like(arr)

#         # Normalize each component
#         teaching_norm = min_max_normalize(raw_teaching)
#         credentials_norm = min_max_normalize(raw_credentials)
#         experience_norm = min_max_normalize(raw_experience)
#         preference_norm = min_max_normalize(raw_preference)

#         # Replace breakdown scores with normalized values + recalculate total
#         normalized_matches = []
#         for i, (instructor, _, breakdown) in enumerate(matches):
#             breakdown_norm = {
#                 'teaching': float(teaching_norm[i]),
#                 'credentials': float(credentials_norm[i]),
#                 'experience': float(experience_norm[i]),
#                 'preference': float(preference_norm[i]),
#             }
#             total_score = np.mean(list(breakdown_norm.values()))
#             normalized_matches.append((instructor, total_score, breakdown_norm))

#         # Sort by normalized total score
#         normalized_matches.sort(key=lambda x: x[1], reverse=True)

#         self.stdout.write(f"Top normalized matches for subject: {subject.code} - {subject.name}\n")

#         for instructor, score, breakdown in normalized_matches[:10]:
#             self.stdout.write(f"{instructor.instructorId} - {instructor}")
#             self.stdout.write(f"  Teaching History:     {breakdown['teaching']:.2f}")
#             self.stdout.write(f"  Credentials:          {breakdown['credentials']:.2f}")
#             self.stdout.write(f"  Experience:           {breakdown['experience']:.2f}")
#             self.stdout.write(f"  Subject Preference:   {breakdown['preference']:.2f}")
#             self.stdout.write(f"  ➤ Total Compatibility: {score:.2f}")
#             self.stdout.write("-" * 50)

from django.core.management.base import BaseCommand
from instructors.models import (
    Instructor, InstructorSubjectPreference,
    InstructorExperience, TeachingHistory, InstructorCredentials,
)
from scheduling.models import Subject
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from django.utils import timezone
from operator import itemgetter

class Command(BaseCommand):
    help = 'Generate better subject preferences using instructor background'

    def handle(self, *args, **options):
        subjects = list(Subject.objects.all())

        # Step 1: Prepare subject texts
        subject_data = []
        subject_ids = []
        for subject in subjects:
            text = f"{subject.code} {subject.name}"
            subject_data.append(text)
            subject_ids.append(subject.subjectId)

        vectorizer = TfidfVectorizer()
        subject_vectors = vectorizer.fit_transform(subject_data)

        subject_match_scores = {subj.subjectId: [] for subj in subjects}

        # Step 2: Loop through instructors
        for instructor in Instructor.objects.all():
            print(f"Processing {instructor.instructorId} - {instructor.full_name}")

            experiences = InstructorExperience.objects.filter(instructor=instructor)
            teachings = TeachingHistory.objects.filter(instructor=instructor)
            credentials = InstructorCredentials.objects.filter(instructor=instructor)
            preferences = InstructorSubjectPreference.objects.filter(instructor=instructor)

            combined_text = ""

            for exp in experiences:
                combined_text += f"{exp.title} {exp.description} "

            for teach in teachings:
                combined_text += f"{teach.subject.code} {teach.subject.name} "

            for cred in credentials:
                combined_text += f"{cred.title} {cred.issuer} "

            for pref in preferences:
                combined_text += f"{pref.subject.code} {pref.subject.name} {pref.preferenceType} "

            if not combined_text.strip():
                continue  # Skip empty profiles

            instructor_vec = vectorizer.transform([combined_text])

            # Step 3: Train simple classifier
            clf = LogisticRegression()
            X = subject_vectors
            y = [1 if subj_id in preferences.values_list('subject__subjectId', flat=True) else 0 for subj_id in subject_ids]

            if len(set(y)) < 2:
                continue  # Skip if not enough variation

            clf.fit(X, y)
            predictions = clf.predict_proba(subject_vectors)[:, 1]  # Probability of being a match

            for i, prob in enumerate(predictions):
                subj_id = subject_ids[i]
                subject_match_scores[subj_id].append((instructor, prob))

        # Final Output: Top 5 per subject with explanations
        print("\n=== Top 5 Instructors per Subject ===\n")
        for subject in subjects:
            print(f"{subject.code} {subject.name}:")

            matches = sorted(subject_match_scores[subject.subjectId], key=itemgetter(1), reverse=True)

            # Apply weighting based on timesTaught
            adjusted_matches = []
            for inst, raw_score in matches:
                teach_record = TeachingHistory.objects.filter(instructor=inst, subject=subject).first()
                times_taught = teach_record.timesTaught if teach_record else 0

                # Weight: +1% score boost per subject repetition (cap at +10%)
                weight_boost = min(times_taught * 0.01, 0.10)
                adjusted_score = raw_score + weight_boost
                adjusted_matches.append((inst, adjusted_score, times_taught))

            # Sort again using adjusted score
            adjusted_matches.sort(key=lambda x: x[1], reverse=True)
            top_matches = adjusted_matches[:5]

            for inst, score, times_taught in top_matches:
                reasons = []

                if times_taught >= 3:
                    reasons.append(f"Frequently taught this subject ({times_taught} times)")
                elif times_taught > 0:
                    reasons.append(f"Taught before ({times_taught} time{'s' if times_taught > 1 else ''})")

                for exp in inst.experiences:
                    if subject.code.lower() in exp.description.lower() or subject.name.lower() in exp.description.lower():
                        reasons.append("Relevant work/academic experience")
                        break

                for cred in inst.instructorcredentials_set.all():
                    if subject.code.lower() in cred.title.lower() or subject.name.lower() in cred.title.lower():
                        reasons.append("Has credentials related to this subject")
                        break

                if inst.subjectPreferences.filter(subject=subject, preferenceType='Prefer').exists():
                    reasons.append("Marked as preferred before")

                reason_str = ", ".join(set(reasons)) if reasons else "Similarity-based suggestion"

                print(f" - {inst.instructorId} ({inst.full_name}) → {score:.4f}")
                print(f"   Reason: {reason_str}")





