# SARAL v1 Demo Walkthrough

## Launch  
   $ uvicorn app.main:app --reload

## Citizen simulation  
   POST /cases/ → creates a new case, triggers AI assistive score  
   Verify response (id + confidence).

## Operator side  
   Visit http://127.0.0.1:8000/dashboard  
   → Observe predicted eligibility, intent, risk flag.

## Metrics  
   GET /metrics/?since=<today> → JSON counts.

## Export  
   GET /cases/export.csv → confirm downloadable audit.

## Logs  
   Open logs/saral.log → check EXPORT_CSV and METRICS entries.

## Discussion  
   “This shows a full loop: citizen → algorithm → operator → audit.”
