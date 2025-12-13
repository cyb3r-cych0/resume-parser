# helpers/section_classifier.py
import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from typing import List

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODEL_DIR, "section_classifier.pkl")
VEC_PATH = os.path.join(MODEL_DIR, "section_vectorizer.pkl")

SECTION_LABELS = ["experience", "education", "skills", "summary", "other"]

# ---------------------- TRAIN ON FIRST RUN ----------------------
def train_default_model():
    # small synthetic dataset — enough to bootstrap improvements
    samples = [
        ("Worked with X, managed Y, delivered Z. 2019–2022", "experience"),
        ("Senior Developer, Google, 2018-2020", "experience"),
        ("BSc Computer Science, MIT, GPA 3.7", "education"),
        ("Master of Science in AI, Stanford", "education"),
        ("Python, Java, SQL, Spring Boot", "skills"),
        ("AWS, Docker, Kubernetes, Terraform", "skills"),
        ("Highly motivated engineer with passion for X", "summary"),
        ("Professional summary: cloud engineer with 5 years...", "summary"),
        ("References available upon request", "other"),
        ("Hobbies: football, travel", "other"),
    ]

    texts = [s[0] for s in samples]
    labels = [s[1] for s in samples]

    vec = TfidfVectorizer(ngram_range=(1,2), stop_words="english")
    X = vec.fit_transform(texts)

    clf = LogisticRegression(max_iter=200)
    clf.fit(X, labels)

    joblib.dump(clf, MODEL_PATH)
    joblib.dump(vec, VEC_PATH)

    return clf, vec


# ---------------------- LOAD OR TRAIN ----------------------
def load_section_model():
    if not os.path.exists(MODEL_PATH):
        return train_default_model()

    clf = joblib.load(MODEL_PATH)
    vec = joblib.load(VEC_PATH)
    return clf, vec


clf, vec = load_section_model()


# ---------------------- CLASSIFY BLOCKS ----------------------
def classify_blocks(paragraphs: List[str]) -> List[str]:
    """
    Input: list of text blocks (e.g., split paragraphs)
    Output: list of predicted section labels
    """
    if not paragraphs:
        return []

    X = vec.transform(paragraphs)
    preds = clf.predict(X)
    return preds.tolist()

def classify_sections():
    pass