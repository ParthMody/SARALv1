# SARAL v1  
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
