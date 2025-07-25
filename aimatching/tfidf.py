import os
import joblib
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from aimatching.utils import getTrainingData
from collections import Counter


MODEL_PATH = "aimatching/saved_models/tfidf_svm_model.pkl"

def trainTfidfSvmModel():
    X, y = getTrainingData()

    print("\n=== Raw Training Samples ===")
    for i, (text, label) in enumerate(zip(X, y)):
        print(f"{i+1}. Label: {label} | Text: {text[:80]}...")  # limit to first 80 chars for readability
    print("============================\n")

    print("\nLabel Distribution:", Counter(y))

    if len(X) < 10:
        print("⚠️ Not enough training data. Skipping model training.")
        return None

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), stop_words='english')),
        ('svm', LinearSVC())
    ])

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("=== Evaluation Report ===")
    print(classification_report(y_test, y_pred))

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"✅ Model saved to {MODEL_PATH}")

    return model

def loadTfidfSvmModel():
    if not os.path.exists(MODEL_PATH):
        print("⚠️ Model not found at expected location.")
        return None
    return joblib.load(MODEL_PATH)
