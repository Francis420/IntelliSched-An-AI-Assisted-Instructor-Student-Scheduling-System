from django.core.management.base import BaseCommand
from aimatching.matcher.data_extractors import build_instructor_text_profile
from aimatching.matcher.explain_match import generate_mistral_explanation
from aimatching.models import InstructorSubjectMatch
from core.models import Instructor
from scheduling.models import Subject
from sentence_transformers import CrossEncoder

class Command(BaseCommand):
    help = 'Run instructor–subject matching using cross-encoder scoring'

    def handle(self, *args, **options):
        print("🔎 Loading cross-encoder model (ms-marco-MiniLM-L12-v2)...")
        cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L12-v2')

        subjects = Subject.objects.all()
        instructors = Instructor.objects.all()

        for subject in subjects:
            subject_text = f"{subject.code} {subject.name}. {subject.description or ''}. {subject.subjectTopics or ''}"

            print(f"\n📘 Subject: {subject.code} - {subject.name}")
            instructor_scores = []

            for instructor in instructors:
                instructor_text = build_instructor_text_profile(instructor)
                score = cross_encoder.predict([(instructor_text, subject_text)])[0]
                instructor_scores.append((instructor, score))

            instructor_scores.sort(key=lambda x: x[1], reverse=True)
            top_5 = instructor_scores[:5]

            print("Top 5 Matches:")
            for idx, (instructor, score) in enumerate(top_5, start=1):
                user_login = instructor.userlogin_set.first()
                user = user_login.user if user_login else None
                full_name = f"{user.firstName} {user.lastName}" if user else instructor.instructorId

                explanation = generate_mistral_explanation(
                    f"Give a brief explaination why {full_name} is a good fit for the subject {subject.name}?"
                )
                print(f"\n#{idx} → {full_name} (Score: {score:.4f})") #also print the other fields
                print(explanation)
        print("\n✅ Matching process completed.")