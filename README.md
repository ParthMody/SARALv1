# SARAL v1

**Citizen-Centred Welfare Access Prototype**  
*Deadline: 25 Oct 2025 (v1 feature lock)*

---

##  Overview
SARAL is a lightweight, citizen-centred platform designed to test how low-literacy users can interact with welfare schemes through simple digital channels.  

The v1 prototype demonstrates a complete end-to-end flow:
- Citizens create welfare cases via **SMS (mock/test harness)**.
- Operators triage and update cases via a **Dashboard**.
- Events are logged automatically, and **Analytics** show real-time counts.

---

## Documentation
All design artifacts and technical specifications are maintained in [`/docs`](docs).

- [Software Design Document (SDD)](docs/SDD.md) — full architecture, diagrams, schema, and acceptance criteria  
- System Context Diagram  
- Sequence Diagrams (Citizen + Operator flows)  
- ERD & Data Dictionary  

---

##  Tech Stack (planned)
- **Backend:** Python (FastAPI), SQLAlchemy  
- **Database:** PostgreSQL 15  
- **Auth (mock v1):** OTP stub (header-based)  
- **Infra:** Docker Compose (local), single VM deploy (cloud)  

---

##  Contributing
This repo is under active development. Contributions are welcome after v1 milestone.
