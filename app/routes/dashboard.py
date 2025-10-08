from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Case, StatusEnum
from jinja2 import Template

router = APIRouter(tags=["dashboard"])

TEMPLATE = Template("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SARAL Dashboard</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
    form { display:inline; }
    .pill { padding: 4px 8px; border-radius: 12px; background:#f3f4f6; }
    .toolbar { margin-bottom: 12px; }
    button { padding: 6px 10px; border:1px solid #ccc; background:#fff; cursor:pointer; border-radius:6px; }
  </style>
</head>
<body>
  <h1>SARAL — Operator Dashboard</h1>
  <div class="toolbar">
    <strong>AI Summary:</strong>
    Likely: {{ ai_likely }} &nbsp; | &nbsp;
    Uncertain: {{ ai_uncertain }} &nbsp; | &nbsp;
    High-risk flags: {{ ai_flags }}
  </div>
  <div class="toolbar">
    <form method="get" action="/dashboard" style="display:flex; gap:8px; align-items:center;">
      <label>Scheme
        <select name="scheme">
          <option value="" {{ '' == sel_scheme and 'selected' or '' }}>All</option>
          {% for sc in schemes %}
            <option value="{{ sc }}" {{ sc == sel_scheme and 'selected' or '' }}>{{ sc }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Status
        <select name="status">
          <option value="" {{ '' == sel_status and 'selected' or '' }}>All</option>
          {% for s in statuses %}
            <option value="{{ s }}" {{ s == sel_status and 'selected' or '' }}>{{ s }}</option>
          {% endfor %}
        </select>
      </label>
      <button type="submit">Apply</button>
      <a href="/metrics/">Metrics (JSON)</a>
    </form>
  </div>
  <div class="toolbar"><strong>AI Summary:</strong>
    Likely: {{ ai_likely }} | Uncertain: {{ ai_uncertain }} | High-risk flags: {{ ai_flags }}
  </div>
  <table>
    <tr><th>ID</th><th>Scheme</th><th>Status</th><th>Locale</th><th>AI: Eligibility</th><th>Intent</th><th>Risk</th><th>Actions</th></tr>
    {% for c in cases %}
    <tr>
      <td>{{ c.id }}</td>
      <td>{{ c.scheme_code }}</td>
      <td>{{ c.status }}</td>
      <td>{{ c.locale }}</td>
      <td>{{ c.predicted_eligibility or '-' }} ({{ c.eligibility_confidence if c.eligibility_confidence else '' }})</td>
      <td>{{ c.intent_label or '-' }}</td>
      <td>{{ '⚠️' if c.risk_flag else '' }} {{ c.risk_score if c.risk_score else '' }}</td>
      <td>
        <form method="post" action="/dashboard/update">
          <input type="hidden" name="id" value="{{ c.id }}">
          <select name="status">
            {% for s in statuses %}
              <option value="{{ s }}" {{ s == c.status and 'selected' or '' }}>{{ s }}</option>
            {% endfor %}
          </select>
          <button type="submit">Update</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
""")

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), scheme: str | None = None, status: str | None = None):
    ai_likely = db.query(Case).filter(Case.predicted_eligibility == "likely").count()
    ai_uncertain = db.query(Case).filter(Case.predicted_eligibility == "uncertain").count()
    ai_flags = db.query(Case).filter(Case.risk_flag == True).count()

    q = db.query(Case)
    if scheme:
        q = q.filter(Case.scheme_code == scheme)
    if status:
        q = q.filter(Case.status == status)
    items = q.order_by(Case.created_at.desc().nullslast()).limit(50).all()
    statuses = [s.value for s in StatusEnum]
    schemes = ["UJJ", "PMAY"]  # quick static list; could query DB
    return TEMPLATE.render(
        cases=items,
        statuses=statuses,
        schemes=schemes,
        sel_scheme=scheme,
        sel_status=status,
        ai_likely=ai_likely,
        ai_uncertain=ai_uncertain,
        ai_flags=ai_flags
    )

@router.post("/dashboard/update")
async def dashboard_update(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    case_id = form.get("id")
    status = form.get("status")

    obj = db.query(Case).filter(Case.id == case_id).first()
    if not obj:
        raise HTTPException(404, detail="Case not found")
    if status not in [s.value for s in StatusEnum]:
        raise HTTPException(400, detail="Invalid status")

    obj.status = status
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)