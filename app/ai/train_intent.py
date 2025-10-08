# ai/train_intent.py
import csv, pickle, pathlib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

ROOT = pathlib.Path(__file__).resolve().parents[0]
DATA = ROOT / "data"
MODELS = ROOT / "models"
MODELS.mkdir(parents=True, exist_ok=True)

texts, labels = [], []
with open(DATA/"intents.csv", encoding="utf-8") as f:
    f.readline()
    for line in f:
        t,l = line.strip().split(",")
        texts.append(t); labels.append(l)

vec = TfidfVectorizer(ngram_range=(1,2), min_df=1)
X = vec.fit_transform(texts)
clf = MultinomialNB().fit(X, labels)

with open(MODELS/"intent_vectorizer.pkl","wb") as f: pickle.dump(vec, f)
with open(MODELS/"intent_nb.pkl","wb") as f: pickle.dump(clf, f)
print("intent model + vectorizer saved")
