# scripts/seed_cases.py
import os, sys
# If running script directly, ensure repo root is on path (Option B safety)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from random import choice, randint
from sqlalchemy.orm import Session

from app.db import Base, engine, SessionLocal
from app import models

def ensure_tables():
    Base.metadata.create_all(bind=engine)

def seed_schemes(db: Session):
    data = [
        {"code": "UJJ", "name": "PM Ujjwala Yojana"},
        {"code": "PMAY", "name": "PM Awas Yojana"},
    ]
    for s in data:
        if not db.query(models.Scheme).filter(models.Scheme.code == s["code"]).first():
            db.add(models.Scheme(code=s["code"], name=s["name"]))
    db.commit()

def seed_cases(db: Session, n: int = 10):
    statuses = [models.StatusEnum.NEW, models.StatusEnum.IN_REVIEW]
    schemes = ["UJJ", "PMAY"]

    for i in range(n):
        citizen_hash = f"hash_{i}"
        scheme_code = choice(schemes)
        existing = (
            db.query(models.Case)
              .filter(models.Case.citizen_hash == citizen_hash,
                      models.Case.scheme_code == scheme_code)
              .first()
        )
        if existing:
            continue

        c = models.Case(
            citizen_hash=citizen_hash,
            scheme_code=scheme_code,
            status=choice(statuses),
            source=models.SourceEnum.SMS if i % 2 == 0 else models.SourceEnum.WEB,
            locale="hi" if i % 2 == 0 else "en",
        )
        db.add(c)
        db.commit()
        db.refresh(c)

        # Log CREATE_CASE event
        db.add(models.Event(
            case_id=c.id,
            action=models.ActionEnum.CREATE_CASE,
            actor_type="CITIZEN",
            payload="{}"
        ))
        db.commit()

if __name__ == "__main__":
    ensure_tables()
    db = SessionLocal()
    try:
        seed_schemes(db)
        seed_cases(db, n=10)
        print("Seeded schemes and cases successfully.")
    except Exception as e:
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()
