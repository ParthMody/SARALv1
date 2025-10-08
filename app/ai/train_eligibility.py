# ai/train_eligibility.py
import csv, pickle, pathlib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[0]
DATA = ROOT / "data"
MODELS = ROOT / "models"
MODELS.mkdir(parents=True, exist_ok=True)

rows = []
with open(DATA/"synth_eligibility.csv") as f:
    f.readline()
    for line in f:
        age,gender,income,edu,rural,cast,e = line.strip().split(",")
        rows.append([int(age), gender, int(income), int(edu), int(rural), int(cast), int(e)])
X = np.array([r[:-1] for r in rows], dtype=object)
y = np.array([r[-1] for r in rows], dtype=int)

pipe = Pipeline(steps=[
  ("pre", ColumnTransformer([
      ("gender", OneHotEncoder(handle_unknown="ignore"), [1]),
      ("pass", "passthrough", [0,2,3,4,5])
  ])),
  ("clf", LogisticRegression(max_iter=2000))
])
pipe.fit(X, y)

with open(MODELS/"eligibility.pkl","wb") as f: pickle.dump(pipe, f)
print("eligibility.pkl saved")
