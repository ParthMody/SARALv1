# SARAL

**A deployed experimental platform for studying how administrative reviewers integrate machine recommendations with field context.**

SARAL presents welfare-eligibility cases to a reviewer alongside a rule-based
recommendation and a field note from prior verification, and records the
reviewer's decision (approve / reject / escalate) and reasoning. It was built to
run a pre-registered experiment on when and how reviewers depart from algorithmic
recommendations — and, in a live field deployment, to observe the same behaviour
in practice.

The paradigm is not specific to welfare: it generalises to any setting pairing a
machine recommendation with private contextual evidence and a reviewer who can
comply, counter-determine, or decline to resolve. Welfare eligibility is the first
instantiation. See [`DESIGN.md`](./DESIGN.md) for the full experimental design and
the v1→v2 design history.

**Paper and materials:** [parthmody.me/saral](https://www.parthmody.me/saral) ·
pre-registration, consent form, governance protocol, de-identified data, and
analysis code.
**Live instrument:** [saral-production.up.railway.app](https://saral-production.up.railway.app/)

---

## What this is

A research instrument, not a workflow tool. It renders a fixed set of case
vignettes for an experiment; it is not a case-management or eligibility-adjudication
system and is not intended for operational use.

Each case presents:

- a **structured record** (applicant profile, documents, eligibility-relevant facts),
- a **field note** — first-hand observations from a prior verification visit, which
  may or may not bear on eligibility,
- a **rule-based recommendation** (approve / reject), derived from the structured
  record alone; the recommendation does not see the field note.

The reviewer issues one of three decisions and a brief written rationale:

- **Approve** — accept eligibility.
- **Reject** — deny eligibility (a *counter-determination* against a recommendation
  to approve, or agreement with a recommendation to reject).
- **Escalate** — decline to resolve the case and route it onward for further review.

The primary outcome, **override**, is any decision that differs from the
recommendation. Because the reviewer can reject *or* escalate against a binary
recommendation, override comprises two distinct acts — *reversal* (a counter-
determination) and *escalation* (a refusal to resolve) — both recorded as override
and distinguished directly from the decision. This decomposition is central to the
study; escalation is not treated as compliance.

## Session flow

1. **Consent** — participant information sheet and informed consent.
2. **Briefing** — the scheme, the eligibility rule, and the three decisions.
3. **Practice case** (not recorded) — familiarisation with the interface.
4. **Comprehension check** — a gated item (two attempts) confirming the participant
   can read the record and field note correctly; passing is required to proceed.
5. **Cases** — twelve vignettes in randomised order; each decision is final on
   submission. A reference panel restating the rules and definitions is available
   on every case screen.
6. **Post-task survey** — field-note salience, standout observations, decision
   confidence.

Blinding, assignment, and outcome recording are handled server-side; the reviewer
sees only the case, and no personally identifying information (all profiles are
synthetic composites).

## Running it

**Requirements:** [fill: runtime + versions, e.g. Python 3.11 / Node 18, Postgres 14]

```bash
# clone
git clone https://github.com/ParthMody/SARAL.git
cd SARAL

# [fill: your actual setup steps — env, deps, DB, seed, run]
```

The vignette pool is defined in [`fill: seeder path`]. Domain content (profiles,
field notes, eligibility rules) is separated from the decision architecture, so the
paradigm can be re-instantiated for a different setting by replacing the seeder
without changing the interface or recording logic.

## Data and reproducibility

De-identified data and the analysis code that reproduces every figure and table in
the paper are at [parthmody.me/saral](https://www.parthmody.me/saral). The analytic
sample and all reported estimates can be regenerated from the raw exports and the
session-timing records included there.

## Ethics

Conducted as independent research under a documented self-governance protocol
(informed consent, voluntariness, withdrawal, data handling, exclusion of
personally identifying information); no institutional ethics review was available
to the investigator in this capacity. All applicant profiles are synthetic; no
vignette corresponds to a real individual. Protocol and consent materials are in
the linked archive.

## License

[DECISION NEEDED — see note below]

## Citation

> Mody, P. (2026). *SARAL: Field-Generated Context and Algorithmic Override in
> Welfare Decision-Making* (working paper). https://www.parthmody.me/saral (In progress)
