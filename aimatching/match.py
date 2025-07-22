import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from aimatching.text import gatherInstructorText
from aimatching.tfidf import loadTfidfSvmModel
from scheduling.models import Subject
from core.models import Instructor
from aimatching.models import InstructorSubjectMatch

def level1_unsupervisedFallback(instructor, subject_list, vectorizer=None):
    """Level 1: For instructors with no data, fallback to keyword match with cosine similarity"""
    if vectorizer is None:
        vectorizer = TfidfVectorizer(stop_words='english')
    instructor_text = gatherInstructorText(instructor)
    if not instructor_text:
        return []

    subjects_texts = [sub.name + " " + sub.code for sub in subject_list]
    tfidf_matrix = vectorizer.fit_transform(subjects_texts + [instructor_text])
    instructor_vec = tfidf_matrix[-1]
    subjects_vecs = tfidf_matrix[:-1]

    cosine_scores = cosine_similarity(instructor_vec, subjects_vecs).flatten()
    top_indices = cosine_scores.argsort()[-5:][::-1]  # top 5
    matches = [(subject_list[i], cosine_scores[i]) for i in top_indices]

    return matches

def level2_dataAugmentation(instructor, subject_list):
    """Level 2: Data augmentation (placeholder). Can extend by using preferences etc."""
    # Example: if instructor has preferences, boost those subjects
    preferred_subjects = []
    for pref in instructor.instructorsubjectpreference_set.filter(preferenceType='Prefer'):
        preferred_subjects.append(pref.subject)

    if preferred_subjects:
        # Simple score boost for preferred subjects
        matches = [(sub, 1.0 if sub in preferred_subjects else 0.5) for sub in subject_list]
        matches = sorted(matches, key=lambda x: x[1], reverse=True)[:5]
        return matches
    return []

def level3_supervisedModel(instructor, model, subject_list):
    """Level 3: Use trained SVM model to predict best subject"""
    instructor_text = gatherInstructorText(instructor)
    if not instructor_text:
        return []

    predicted_code = model.predict([instructor_text])[0]
    matches = []
    for subject in subject_list:
        if subject.code == predicted_code:
            matches.append((subject, 1.0))  # top predicted score
            break

    # To add top 5 ranked, you can use decision_function or probability if available (LinearSVC doesn't have prob by default)
    # For simplicity, only top 1 is returned here
    return matches

def generateMatchSuggestions():
    model = loadTfidfSvmModel()
    subjects = list(Subject.objects.all())
    results = []

    for instructor in Instructor.objects.all():
        has_training_data = instructor.teachingHistory.exists()
        instructor_text = gatherInstructorText(instructor)
        has_text_data = bool(instructor_text)

        # Select match level
        if model and has_training_data:
            matches = level3_supervisedModel(instructor, model, subjects)
            level_used = 3
        elif has_text_data:
            matches = level2_dataAugmentation(instructor, subjects)
            level_used = 2
        else:
            matches = level1_unsupervisedFallback(instructor, subjects)
            level_used = 1

        # Return matches for manual saving in the command
        results.append((instructor, matches, level_used))

    return results

