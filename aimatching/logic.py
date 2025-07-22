from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from .model_training import loadSVMModel
from .utils import gatherInstructorText


def level1_unsupervisedFallback(instructor, subjects):
    instructor_text = gatherInstructorText(instructor)
    if not instructor_text:
        return []

    subject_texts = [subject.name + " " + (subject.code or '') for subject in subjects]
    corpus = [instructor_text] + subject_texts
    tfidf = TfidfVectorizer().fit_transform(corpus)
    cosine_sim = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
    ranked = sorted(zip(subjects, cosine_sim), key=lambda x: x[1], reverse=True)
    return ranked[:5]


def level2_dataAugmentedMatching(instructor, subjects):
    text = gatherInstructorText(instructor)
    subject_texts = [(s, s.name + " " + (s.code or '')) for s in subjects]

    tfidf = TfidfVectorizer().fit([text] + [t for _, t in subject_texts])
    instructor_vec = tfidf.transform([text])
    subject_vecs = tfidf.transform([t for _, t in subject_texts])

    cosine_sim = cosine_similarity(instructor_vec, subject_vecs).flatten()
    ranked = sorted(zip(subjects, cosine_sim), key=lambda x: x[1], reverse=True)
    return ranked[:5]


def level3_supervisedMatching(instructor, subjects):
    model = loadSVMModel()
    if not model:
        return []

    text = gatherInstructorText(instructor)
    predictions = model.predict_proba([text]) if hasattr(model, "predict_proba") else model.decision_function([text])

    if hasattr(predictions, 'shape') and predictions.shape[1] == len(model.classes_):
        scores = predictions[0]
        subject_scores = list(zip(model.classes_, scores))
        ranked = sorted(subject_scores, key=lambda x: x[1], reverse=True)

        matched_subjects = []
        for code, score in ranked:
            for subject in subjects:
                if subject.code == code:
                    matched_subjects.append((subject, score))
                    break
            if len(matched_subjects) == 5:
                break

        return matched_subjects
    return []


def matchInstructorToSubjects(instructor, subjects):
    history_count = instructor.teachingHistory.count()
    credentials_count = instructor.instructorcredentials_set.count()

    if history_count >= 3 and credentials_count >= 3:
        matches = level3_supervisedMatching(instructor, subjects)
        if matches:
            return {"label": "Supervised Matching", "matches": matches}

    if history_count >= 1 or credentials_count >= 1:
        return {"label": "Data-Augmented Matching", "matches": level2_dataAugmentedMatching(instructor, subjects)}

    return {"label": "Unsupervised Fallback", "matches": level1_unsupervisedFallback(instructor, subjects)}
