import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from .utils import getTrainingData

MODEL_PATH = "aimatching/svm_model.joblib"

def trainSVMModel():
    data, labels = getTrainingData()
    if not data:
        print("No data to train on.")
        return None

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer()),
        ('svm', LinearSVC())
    ])

    pipeline.fit(data, labels)
    joblib.dump(pipeline, MODEL_PATH)
    print(f"SVM model trained and saved to {MODEL_PATH}")
    return pipeline

def loadSVMModel():
    try:
        return joblib.load(MODEL_PATH)
    except Exception as e:
        print("Error loading model:", e)
        return None
