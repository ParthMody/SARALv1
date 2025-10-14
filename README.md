# SARAL v1 – AI-Assisted Welfare Access System
> A transparent, offline-first prototype to test equitable AI-enabled welfare delivery.

---

## Overview
SARAL v1 evaluates how citizens experience welfare access through a rule-based, explainable system while the **Operator Behaviour Module** studies how human intermediaries interpret or override algorithmic guidance.

### Core Principles
- Human-first, explainable AI
- Offline-first, low-bandwidth operation
- Transparent logs + local privacy
- Co-accountability between citizen & operator

---

## Architecture
| Layer | Stack | Purpose |
|-------|--------|----------|
| API | FastAPI + SQLite | Offline logic & storage |
| AI | Python (scikit-learn + rules) | Eligibility + intent assist |
| Dashboard | HTML/Jinja2 | Operator interface |
| Logs | RotatingFileHandler + CSV export | Transparent audit trail |

---

## Run Locally
```bash
uvicorn app.main:app --reload
