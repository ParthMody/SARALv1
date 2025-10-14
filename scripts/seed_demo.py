from app.db import SessionLocal
from app import models
import uuid, datetime

def seed_demo():
    db = SessionLocal()
    if not db.query(models.Case).first():
        cases = [
            models.Case(
                id=str(uuid.uuid4()), citizen_hash=f"hash_demo_{i}",
                scheme_code="UJJ" if i % 2 == 0 else "PMAY",
                status=models.StatusEnum.NEW,
                source=models.SourceEnum.SMS,
                locale="hi" if i % 2 == 0 else "en",
                review_confidence=0.65 + 0.1 * (i % 3),
                audit_flag=bool(i % 3 == 0),
                flag_reason="missing_fields" if i % 3 == 0 else "",
                intent_label="apply" if i % 2 == 0 else "help",
                created_at=datetime.datetime.utcnow(),
            )
            for i in range(8)
        ]
        db.add_all(cases)
        db.commit()
        print("Seeded demo data.")
    db.close()

if __name__ == "__main__":
    seed_demo()
