from aimatching.tfidf import loadTfidfSvmModel
from aimatching.text import fallbackSubjectMatch, buildInstructorText
from scheduling.models import Subject

def matchSubjectsForInstructor(instructor):
    subjects = Subject.objects.all()
    text = buildInstructorText(instructor)
    totalTokens = len(text.split())

    # Level 3: Enough data (supervised)
    if totalTokens >= 100:
        print("📘 Using Level 3 (SVM)")
        model = loadTfidfSvmModel()
        if not model:
            print("⚠️ Trained model not found. Falling back.")
        else:
            prediction = model.predict([text])[0]
            return [(s, 1.0 if s.code == prediction else 0.0) for s in subjects]

    # Level 2: Some data → augment logic here (placeholder)
    elif totalTokens >= 20:
        print("📘 Using Level 2 (Data Augmentation fallback to Level 1)")
        return fallbackSubjectMatch(instructor, subjects)

    # Level 1: Not enough data
    else:
        print("📘 Using Level 1 (Unsupervised Fallback)")
        return fallbackSubjectMatch(instructor, subjects)
