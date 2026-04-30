# SARAL v2

**Synthetic Administrative Review for Algorithmic Layering**

A controlled experimental instrument for measuring how administrative decision-makers respond to field-generated context when reviewing rule-based algorithmic recommendations in welfare eligibility verification.

---

## 1. What This Is

SARAL v2 is **not a workflow system** and not a production tool.

It is a **session-based experimental instrument** designed to measure the causal effect of field-generated signals on operator override behaviour, and to test whether interpretive content in prior-officer notes shifts final-layer decisions on rule-eligible cases.

SARAL v1.3 was a kiosk-style workflow prototype with live case processing, a shared operator dashboard, and a unidirectional ML risk score. v2 replaces that entirely with a controlled experimental design grounded in the Slum Rehabilitation Authority (SRA) Annexure-II eligibility framework (GR ZoPuDho-0810/2018).

---

## 2. Research Design

### 2.1 Primary Research Question

How do administrative decision-makers incorporate informal signals from prior field-level verification when reviewing a case with a formal eligibility record, and how does this influence their decision to follow, override, or defer an algorithmic recommendation?

### 2.2 Operator Position

Operators in this study are positioned at the **final-officer layer** (Sub-Divisional Officer / Sakshama Pradhikari), reviewing cases that have completed prior junior-officer field verification. This matches the role at which SARAL is designed to operate in the actual SRA Annexure-II workflow.

### 2.3 Experimental Structure

The vignette set identifies three interacting components:

| Dimension | Levels |
|---|---|
| Algorithmic recommendation | Approve / Reject |
| Field-generated signal | Absent (Control) / Present (Treatment) |
| Signal direction | Reinforcing (WITH) / Contradicting (AGAINST) the recommendation |

The pool contains **16 base profiles**, each with control and treatment versions (32 vignette objects), balanced **4/4/4/4** across the recommendation × signal direction factorial. This design breaks the confound between algorithm direction and signal direction present in earlier iterations.

### 2.4 Per-Session Structure

Each operator evaluates **12 cases** drawn from the 16-profile pool in randomised order, with **6 control + 6 treatment** enforced at draw. Approve/reject distribution falls out of the draw (averaging ~6/6 across operators).

### 2.5 Primary Outcome

`override = 1` when operator decision ≠ algorithm recommendation.

Override is defined as disagreement with the algorithmic recommendation, not rejection of the applicant.

### 2.6 Secondary Outcomes

- Override response by signal direction (WITH vs. AGAINST)
- Override response by signal category (six SRA-grounded categories)
- Inter-rater agreement (second review)
- Response time as a behavioural proxy for deliberation
- Post-task salience ratings linked to override patterns

### 2.7 Reasoning Text

Reasoning text is collected but treated as **exploratory** in the analysis plan, given expected sparsity in low-stakes vignette settings. Primary inferences do not depend on reasoning content.

---

## 3. Grounding and Sources

Vignette signals are paraphrased from one of two sources:

1. **Phase 1 verification corpus** (260 PMAY field observations, Maharashtra, January 2026): signal types observed in actual welfare verification practice.
2. **GR-documented disqualifications** (D1–D4, VP1–VP6, Track A/B requirements) under the 2018 SRA GR.

Applicant profiles are synthetic composites identified by case number; no names, addresses, or survey numbers corresponding to identifiable individuals are used. No vignette uses constructed humanitarian scenarios; sympathy framings appear only at the level attested in Phase 1 field notes.

### Signal Categories

Re-derived from the Phase 1 corpus and the GR's six-point eligibility framework:

- Cutoff-date proof
- Family property holdings
- Tenancy and occupancy
- Documentation authenticity
- Alternate-property declaration integrity
- Sympathy framing

---

## 4. Key Differences from v1.3

| | v1.3 | v2 |
|---|---|---|
| **Purpose** | Workflow prototype | Controlled experiment |
| **Cases** | Live intake from kiosk | Pre-loaded synthetic vignette pool (16 profiles, 32 vignettes) |
| **Grounding** | Generic welfare context | SRA Annexure-II, 2018 GR-grounded |
| **Operator visibility** | Shared queue across operators | Session-isolated, no cross-visibility |
| **Algorithm output** | Approve only (unidirectional) | Approve and Reject (bidirectional) |
| **Risk score** | Shown to treatment arm | Excluded — confounds signal isolation |
| **Cell balance** | Not enforced | 4/4/4/4 across rec × direction factorial |
| **Post-task survey** | None | 3-item Likert salience survey |
| **Secondary review** | None | Independent blind review (~10% of cases) |
| **Data model** | `cases`, `events` | `operators`, `evaluations`, `survey_responses`, `second_reviews`, `audit_log` |

---

## 5. System Architecture

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI + SQLite | Session logic and persistence |
| Interface | Jinja2 templates | Operator session, admin panel |
| Vignette engine | Python seeder script | 16-profile pool, paraphrased from Phase 1 + GR |
| Audit trail | `audit_log` table | Immutable append-only event log |
| Export | CSV via admin panel | Analysis-ready outputs |

**Design constraints:**

- No external APIs
- No real-time inference
- No cross-operator visibility during sessions
- No feedback shown to operators after session
- Local-only data storage; no cloud dependency

---

## 6. Functional Components

### 6.1 Operator Session Flow

1. **Login** — captures initials, age, role, experience years, locale (English / Marathi)
2. **Session framing** — operator informed of final-officer review position
3. **Case assignment** — 6 control + 6 treatment vignettes drawn from 16-profile pool, order randomised per operator
4. **Case evaluation** — operator sees applicant profile (case number, demographics, claimed timeline, documents, structure), field note (sterile in control, interpretive in treatment), and algorithm recommendation; submits decision (Approve / Reject / Escalate) with brief reasoning
5. **Post-task survey** — 3 Likert items on field note salience, standout observations, and decision confidence
6. **Session complete** — no feedback shown; operator notifies researcher

### 6.2 Vignette Pool

16 base profiles × 2 arms (control/treatment) = 32 vignette objects.

**Cell distribution:**

| | WITH algo | AGAINST algo |
|---|---|---|
| **APPROVE** | 4 profiles (3, 4, 10, 15) | 4 profiles (7, 8, 13, 14) |
| **REJECT** | 4 profiles (1, 2, 5, 11) | 4 profiles (6, 9, 12, 16) |

Field notes are stored in both English and Marathi and served based on operator locale at runtime. Marathi translations are researcher-translated; this limitation is acknowledged in the analysis plan.

### 6.3 Admin Panel

Accessible at `/admin` (passcode protected via `SARAL_ADMIN_SECRET`).

- Session monitor — completion status, override counts, response times, crash recovery
- Second review assignment — triggers post-hoc assignment of treatment-arm overrides
- Data exports — evaluations, survey responses, second reviews (CSV)

### 6.4 Secondary Review Module

Triggered post-hoc after primary sessions complete. Approximately 10% of cases reviewed.

Assignment priority:

1. Operator with ≥ 10 additional years of experience → `review_type = experienced`
2. Otherwise → random independent operator → `review_type = random`

Primary decision is stored in the database but never surfaced to the secondary reviewer during their session. Blinding is enforced at the query layer.

### 6.5 Session Recovery

If an operator's browser crashes mid-session, the researcher can resume the session from the admin panel without data loss. All submitted evaluations are preserved. The operator's session code is displayed in the topbar for researcher reference at session start.

---

## 7. Data Model

| Table | Description |
|---|---|
| `operators` | One row per session — demographics, locale, completion status |
| `vignettes` | Pre-loaded 32-vignette pool — immutable at runtime |
| `evaluations` | Primary outcome table — one row per operator × case |
| `survey_responses` | Post-task Likert survey — one row per operator |
| `second_reviews` | Secondary review outcomes — blind to primary decision |
| `audit_log` | Immutable append-only event log |

---

## 8. Privacy & Ethics

- Local-only data storage; no cloud dependency
- No persistent personal identifiers beyond session IDs
- Operator demographics (initials, age, role, experience) stored for heterogeneity analysis only
- No citizen PII — all cases are synthetic composites identified by case number
- No real names, addresses, or survey numbers used in vignettes
- The study is conducted as **independent research**; a self-governance protocol covering consent, voluntariness, data handling, and withdrawal procedures is documented in lieu of formal institutional ethics review
- All participation is voluntary; written informed consent obtained before each session

---

## 9. Local Setup

### 9.1 Requirements

- Python 3.10+
- Virtual environment recommended

### 9.2 Install

```bash
pip install -r requirements.txt
pip install python-multipart
```

### 9.3 Configure

Create a `.env` file in the project root:

```
SARAL_ADMIN_SECRET=your_admin_passcode_here
DATABASE_URL=sqlite:///./saral_v2.db
```

### 9.4 Seed the vignette pool

```bash
python -m scripts.seed_vignettes
```

To reseed (drops existing pool):

```bash
python -m scripts.seed_vignettes --clear
```

### 9.5 Run

```bash
uvicorn app.main:app --reload
```

### 9.6 Access

| URL | Description |
|---|---|
| `http://localhost:8000/` | Operator login |
| `http://localhost:8000/admin` | Admin panel (passcode required) |
| `http://localhost:8000/reviewer-login` | Secondary reviewer login |

---

## 10. Status

**Instrument finalised.** Field deployment scheduled May 2026 in Mumbai.

The intended contribution is a reusable research instrument for studying how field-generated context changes human responses to rule-based algorithmic recommendations, with the SRA deployment serving as a first instantiation against a documented welfare-eligibility framework.

---

## 11. Documentation

Supporting documents, including consent forms, self-governance protocol, pre-registration, and codebook, will be maintained separately and made available at [parthmody.me](https://parthmody.me) at a later date.

---

## License

Research code. Not licensed for production use.

## Contact

Parth Mody · [parthmody.me](https://parthmody.me)
