# SARAL v1.3
**System for Algorithmic Fairness in Responsible Access to Livelihoods**

A transparent, offline-first **research prototype** to study AI-assisted welfare access and human decision-making under algorithmic guidance.

## 1. Purpose

SARAL v1 is **not a production system**.  
It is a **research instrument** designed to empirically study:

- How citizens experience structured welfare eligibility checks
- How human operators interpret, trust, or override algorithmic signals
- How explainable, low-automation AI affects access, consistency, and fairness

The system is intentionally **minimal, auditable, and constrained**.

## 2. Research Framing

SARAL v1 supports **quasi-experimental and RCT-style field testing**.

### 2.1 Study Dimensions
- **Citizen Experience**
  - Clarity of process
  - Trust in system
  - Comfort with disclosure
- **Operator Behaviour**
  - Reliance on algorithmic signals
  - Override frequency and rationale
  - Bias amplification or correction
- **System-Level Effects**
  - Decision consistency
  - Error propagation
  - Transparency and traceability

### 2.2 Treatment Logic
- **Control Arm**
  - No algorithmic guidance
- **Treatment Arm**
  - Rule-based eligibility signals
  - Optional ML risk scores
- **Human-in-the-Loop**
  - Human operators make all final decisions
  - No automated approvals or rejections

## 3. Core Principles

- Human-first decision-making
- Explainability over performance
- Offline-first, low-bandwidth operation
- Local data storage with no cloud dependency
- Explicit auditability
- Co-accountability between system and operator

## 4. System Architecture

| Layer | Technology | Purpose |
|------|-----------|---------|
| API | FastAPI + SQLite | Local logic and persistence |
| Intelligence | Python (rules + optional ML) | Eligibility signals |
| Interface | HTML + Jinja2 | Operator dashboard |
| Logging | RotatingFileHandler + CSV export | Audit trail |
| Export | CSV | Analysis-ready outputs |

**Design constraints:**
- No external APIs  
- No real-time inference dependency  

## 5. Functional Components

### 5.1 Citizen Intake (Kiosk Mode)
- Structured, form-based data collection
- Plain-language questions
- No scores or decisions shown to citizens
- Fully offline operation

### 5.2 Eligibility & Signal Layer
- Deterministic rule-based checks (baseline)
- Optional ML-derived risk scores (treatment arm only)
- Confidence bands where applicable
- Signals are advisory only and never enforced

### 5.3 Operator Dashboard
- Case review interface
- Visibility into:
  - Input variables
  - Eligibility signals
  - Model rationale (where applicable)
- Explicit recording of operator decisions

### 5.4 Operator Behaviour Module
Captures:
- Acceptance vs override of algorithmic signals
- Time-to-decision
- Consistency across comparable cases
- Differences between control and treatment arms

This module represents the **primary research contribution** of SARAL v1.

## 6. Logging & Auditability

Each case generates:
- Input snapshot
- Algorithmic outputs
- Operator action
- Timestamped decision record

### Outputs
- CSV files for quantitative analysis
- Structured logs for traceability

No black-box decisions exist.

## 7. Privacy & Ethics Model

- Local-only data storage
- No persistent personal identifiers beyond session IDs
- No biometric or document storage
- Explicit informed consent during field testing

Designed to be compatible with **academic ethics review** requirements.

## 8. Local Setup

### 8.1 Requirements
- Python 3.10+
- Virtual environment recommended

### 8.2 Run Locally
```bash
uvicorn app.main:app --reload
```

--------------------------------------------------------------------------------------------------------------------------------------------
v2
--------------------------------------------------------------------------------------------------------------------------------------------


# SARAL v2
**System for Algorithmic Fairness in Responsible Access to Livelihoods**

A controlled experimental instrument for measuring operator decision behaviour under algorithmic guidance in welfare triage contexts.

---

## 1. What This Is

SARAL v2 is **not a workflow system** and not a production tool.

It is a **session-based experimental instrument** designed to measure the causal effect of unencoded signals in welfare case notes on operator decision-making, and to test algorithm aversion by exposing operators to explicit algorithmic recommendations.

SARAL v1.3 was a kiosk-style workflow prototype with live case processing, a shared operator dashboard, and a unidirectional ML risk score. v2 replaces that entirely with a controlled experimental design.

---

## 2. Research Design

### 2.1 Primary Research Questions

- Do unencoded signals in field notes (e.g. material affluence proxies) causally affect operator approve/reject decisions?
- Do operators exhibit algorithm aversion — diverging from explicit algorithmic recommendations — and does this vary with signal exposure?

### 2.2 Experimental Structure

| | Control Arm (Arm A) | Treatment Arm (Arm B) |
|---|---|---|
| **Field note** | Restates structured inputs only | Identical structure + one injected unencoded signal |
| **Algorithm recommendation** | Approve or Reject | Approve or Reject |
| **Cases per session** | 8 | 8 |
| **Pool size** | 160 | 160 |

Each operator evaluates **16 cases** in a single supervised session — 8 control and 8 treatment, randomised in order. The operator does not know which arm each case belongs to.

### 2.3 Primary Outcome

`override = 1` when operator decision ≠ algorithm recommendation.

This is the TDD §8.3 definition: rejecting an applicant is not the same as overriding the algorithm.

### 2.4 Secondary Outcomes

- Operator heterogeneity in response to the injected signal
- Agreement rate in secondary review
- Post-task salience ratings linked to override patterns
- Response time as a behavioural proxy for deliberation

---

## 3. Key Differences from v1.3

| | v1.3 | v2 |
|---|---|---|
| **Purpose** | Workflow prototype | Controlled experiment |
| **Cases** | Live intake from kiosk | Pre-loaded synthetic vignette pool |
| **Operator visibility** | Shared queue across operators | Session-isolated, no cross-visibility |
| **Algorithm output** | Approve only (unidirectional) | Approve and Reject (bidirectional) |
| **Risk score** | Shown to treatment arm | Excluded — confounds signal isolation |
| **Post-task survey** | None | 3-item Likert salience survey |
| **Secondary review** | None | Post-hoc treatment-arm override review |
| **Data model** | `cases`, `events` | `operators`, `evaluations`, `survey_responses`, `second_reviews`, `audit_log` |

---

## 4. System Architecture

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI + SQLite | Session logic and persistence |
| Interface | Jinja2 templates | Operator session, admin panel |
| Vignette engine | Python seeder script | Synthetic case pool (320 vignettes) |
| Audit trail | `audit_log` table | Immutable append-only event log |
| Export | CSV via admin panel | Analysis-ready outputs |

**Design constraints:**
- No external APIs
- No real-time inference
- No cross-operator visibility during sessions
- No feedback shown to operators after session

---

## 5. Functional Components

### 5.1 Operator Session Flow

1. **Login** — captures initials, age, role, experience years, locale (English / Marathi)
2. **Case assignment** — 8 control + 8 treatment vignettes drawn from pool, order randomised per operator
3. **Case evaluation** — operator sees applicant profile, field note, rule result, and algorithm recommendation; submits decision (Approve / Reject / Escalate) with mandatory reasoning
4. **Post-task survey** — 3 Likert items on field note salience, standout observations, and decision confidence
5. **Session complete** — no feedback shown; operator notifies researcher

### 5.2 Vignette Pool

320 synthetic cases across 4 buckets:

| Arm | Recommendation | Count |
|---|---|---|
| Control | Approve | 80 |
| Control | Reject | 80 |
| Treatment | Approve | 80 |
| Treatment | Reject | 80 |

Pool is seeded once before the experiment. Field notes are stored in both English and Marathi and served based on operator locale at runtime.

> **Note:** The current pool uses stub field notes pending confirmation of SRA Annexure-II field note format and Marathi translation verification by a domain-familiar speaker.

### 5.3 Admin Panel

Accessible at `/admin` (passcode protected via `SARAL_ADMIN_SECRET`).

- Session monitor — completion status, override counts, response times, crash recovery
- Second review assignment — triggers post-hoc assignment of treatment-arm overrides
- Data exports — evaluations, survey responses, second reviews (CSV)

### 5.4 Secondary Review Module

Triggered post-hoc after all primary sessions complete. Only treatment-arm overrides are eligible.

Assignment priority:
1. Operator with ≥ 10 additional years of experience → `review_type = experienced`
2. Otherwise → random independent operator → `review_type = random`

Primary decision is stored in the database but never surfaced to the secondary reviewer until after they submit. Blinding is enforced at the query layer.

### 5.5 Session Recovery

If an operator's browser crashes mid-session, the researcher can resume the session from the admin panel without data loss. All submitted evaluations are preserved. The operator's 8-character session code is displayed in the topbar for the researcher to note at session start.

---

## 6. Data Model

| Table | Description |
|---|---|
| `operators` | One row per session — demographics, locale, completion status |
| `vignettes` | Pre-loaded synthetic case pool — immutable at runtime |
| `evaluations` | Primary outcome table — one row per operator × case |
| `survey_responses` | Post-task Likert survey — one row per operator |
| `second_reviews` | Secondary review outcomes — treatment overrides only |
| `audit_log` | Immutable append-only event log |

---

## 7. Privacy & Ethics

- Local-only data storage — no cloud dependency
- No persistent personal identifiers beyond session IDs
- Operator demographics (initials, age, role, experience) stored for heterogeneity analysis only
- No citizen PII — all cases are synthetic
- No feedback or deception debrief shown during session (Hawthorne mitigation)
- Designed to be compatible with academic ethics review requirements

---

## 8. Local Setup

### 8.1 Requirements

- Python 3.10+
- Virtual environment recommended

### 8.2 Install

```bash
pip install -r requirements.txt
pip install python-multipart
```

### 8.3 Configure

Create a `.env` file in the project root:

```
SARAL_ADMIN_SECRET=your_admin_passcode_here
DATABASE_URL=sqlite:///./saral_v2.db
```

### 8.4 Seed the vignette pool

```bash
python -m scripts.seed_vignettes
```

To reseed (drops existing pool):

```bash
python -m scripts.seed_vignettes --clear
```

### 8.5 Run

```bash
uvicorn app.main:app --reload
```

### 8.6 Access

| URL | Description |
|---|---|
| `http://localhost:8000/` | Operator login |
| `http://localhost:8000/admin` | Admin panel (passcode required) |
| `http://localhost:8000/reviewer-login` | Secondary reviewer login | (Pending)

---

## 9. Open Items (Pre-Pilot)

| Item | Status |
|---|---|
| SRA Annexure-II field note format and language register | Pending field contact (April 13) |
| Marathi translation verification | Pending domain-familiar speaker review |
| Algorithm rejection vignette wording | To be finalised before build |
| Identification strategy and estimand validity | Pending Gigi Foster feedback (April 13) |
| Data export anonymisation policy | To be resolved before Mumbai pilot |
