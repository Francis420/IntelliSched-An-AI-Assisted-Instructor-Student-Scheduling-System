from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from instructors.models import Instructor, InstructorSubjectPreference
from scheduling.models import Subject

import random
import joblib

from aimatching.helpers import gatherInstructorText


def generate_pair_text(instructor, subject):
    instructor_text = gatherInstructorText(instructor)
    subject_details = f"Subject: {subject.code} - {subject.name}\n"
    subject_details += f"Description: {subject.description or ''}\n"
    subject_details += f"Topics: {subject.subjectTopics or ''}"
    return instructor_text + "\n" + subject_details



def getTrainingData():
    X = []
    y = []

    subjects = list(Subject.objects.filter(isActive=True))
    instructors = list(Instructor.objects.all())

    for instructor in instructors:
        # ✅ POSITIVE: Previously taught subjects
        for teaching in instructor.teachingHistory.all():
            subj = teaching.subject
            X.append(generate_pair_text(instructor, subj))
            y.append(1)

        # ✅ POSITIVE: Preferred subjects
        for pref in InstructorSubjectPreference.objects.filter(instructor=instructor, preferenceType='Prefer'):
            subj = pref.subject
            X.append(generate_pair_text(instructor, subj))
            y.append(1)

    for instructor in instructors:
        prefer_subject_ids = set(
            InstructorSubjectPreference.objects.filter(instructor=instructor).values_list('subject_id', flat=True)
        )
        taught_subject_ids = set(
            instructor.teachingHistory.values_list('subject_id', flat=True)
        )
        related_ids = prefer_subject_ids.union(taught_subject_ids)

        # ❌ NEGATIVE: Avoid subjects
        for pref in InstructorSubjectPreference.objects.filter(instructor=instructor, preferenceType='Avoid'):
            subj = pref.subject
            X.append(generate_pair_text(instructor, subj))
            y.append(0)

        # ❌ NEGATIVE: Random unrelated subjects
        unrelated_subjects = [s for s in subjects if s.subjectId not in related_ids]
        random.shuffle(unrelated_subjects)
        for subj in unrelated_subjects[:3]:
            X.append(generate_pair_text(instructor, subj))
            y.append(0)

    return X, y


def trainBinaryMatchModel():
    X, y = getTrainingData()

    if len(set(y)) < 2:
        print("⚠️ Not enough label diversity for training.")
        return None

    print("🔢 Total Samples:", len(X))

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    vectorizer = TfidfVectorizer()
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = LinearSVC()
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)
    print(classification_report(y_test, y_pred))

    # ✅ Save both the model and vectorizer
    joblib.dump(model, "aimatching/match_model.pkl")
    joblib.dump(vectorizer, "aimatching/vectorizer.pkl")
    print("✅ Binary match model trained and saved.")

    return model


def load_match_model():
    return joblib.load("aimatching/match_model.pkl")


def load_vectorizer():
    return joblib.load("aimatching/vectorizer.pkl")