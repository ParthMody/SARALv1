# ai/generate_synthetic.py
import csv, random, pathlib
DATA = pathlib.Path(__file__).resolve().parents[0] / "data"
DATA.mkdir(parents=True, exist_ok=True)
random.seed(42)

def synth_row():
    age = random.randint(18, 70)
    gender = random.choice(["M","F"])
    income = random.choice([60000, 90000, 120000, 180000, 240000, 300000])
    education_years = random.choice([0, 5, 8, 10, 12, 16])
    rural = random.choice([0,1])
    caste_marginalized = random.choice([0,1,1]) # skew a bit
    # simple synthetic rule for label
    eligible = 1 if (income <= 120000 and education_years <= 10) else 0
    # add noise
    if random.random() < 0.15: eligible = 1-eligible
    return [age, gender, income, education_years, rural, caste_marginalized, eligible]

with open(DATA/"synth_eligibility.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["age","gender","income","education_years","rural","caste_marginalized","eligible"])
    for _ in range(300): w.writerow(synth_row())

# intents (simple)
intents = [
 ("I applied for gas connection","applied"),
 ("my application was rejected","rejected"),
 ("need help to apply","help"),
 ("status please","status"),
 ("how to submit documents","help"),
 ("approved message received","approved"),
 ("I was rejected unfairly","grievance"),
 ("want to check eligibility","eligibility"),
]
with open(DATA/"intents.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["text","label"])
    # duplicate with small perturbations
    for text,label in intents:
        for i in range(40):
            w.writerow([text, label])
