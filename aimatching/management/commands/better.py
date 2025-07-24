from django.core.management.base import BaseCommand
from instructors.models import Instructor, InstructorSubjectPreference
from scheduling.models import Subject
from instructors.models import TeachingHistory
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from django.utils import timezone
from operator import itemgetter
from aimatching.matcher.data_extractors import (
    get_teaching_text,
    get_credentials_text,
    get_experience_text,
    get_preference_text,
)

class Command(BaseCommand):
    help = 'Generates a better match model for instructors and subjects with explanations.'

    def handle(self, *args, **options):
        subjects = list(Subject.objects.all())

        # Step 1: Prepare subject texts
        subject_data = []
        subject_ids = []
        for subject in subjects:
            text = f"{subject.name}\n{subject.description or ''}\n{subject.subjectTopics or ''}"
            subject_data.append(text.strip())
            subject_ids.append(subject.subjectId)

        vectorizer = TfidfVectorizer()
        subject_vectors = vectorizer.fit_transform(subject_data)

        subject_match_scores = {subj.subjectId: [] for subj in subjects}

        # Step 2: Loop through instructors
        for instructor in Instructor.objects.all():
            print(f"Processing {instructor.instructorId} - {instructor.full_name}")

            teaching_text = get_teaching_text(instructor)
            experience_text = get_experience_text(instructor)
            credentials_text = get_credentials_text(instructor)
            preference_text = get_preference_text(instructor)

            combined_text = f"{teaching_text} {experience_text} {credentials_text} {preference_text}".strip()

            if not combined_text:
                continue  # Skip empty profiles

            instructor_vec = vectorizer.transform([combined_text])

            # Step 3: Train simple classifier
            clf = LogisticRegression()
            X = subject_vectors
            y = [
                1 if subj_id in instructor.preferences.values_list('subject__subjectId', flat=True)
                else 0
                for subj_id in subject_ids
            ]

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

                for exp in inst.experiences.all():
                    if subject.code.lower() in exp.description.lower() or subject.name.lower() in exp.description.lower():
                        reasons.append("Relevant work/academic experience")
                        break

                for cred in inst.credentials.all():
                    if subject.code.lower() in cred.title.lower() or subject.name.lower() in cred.title.lower():
                        reasons.append("Has credentials related to this subject")
                        break

                if inst.preferences.filter(subject=subject, preferenceType='Prefer').exists():
                    reasons.append("Marked as preferred before")

                reason_str = ", ".join(set(reasons)) if reasons else "Similarity-based suggestion"

                print(f" - {inst.instructorId} ({inst.full_name}) → {score:.4f}")
                print(f"   Reason: {reason_str}")