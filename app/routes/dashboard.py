# app/routes/dashboard.py
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
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
    .muted { color:#666; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Operator Dashboard <span title="Assistive AI – triage only"></span></h1>

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
      <label><input type="checkbox" name="flags" value="true" {{ 'checked' if sel_flags else '' }}> Flags only</label>
      <label>Min confidence <input type="number" step="0.05" min="0" max="1" name="min_conf" value="{{ sel_min_conf or '' }}" style="width:6rem"></label>
      <button type="submit">Apply</button>
      <a class="muted" href="/metrics/">Metrics (JSON)</a>
    </form>
  </div>

  <div class="toolbar"><strong>AI Summary:</strong>
    Review-ready (≥0.7): {{ ready }} | Needs attention: {{ needs }} | Flags: {{ flags }}
  </div>

  <table>
    <tr>
      <th>ID</th><th>Scheme</th><th>Status</th><th>Locale</th>
      <th>Confidence</th><th>Audit</th><th>Reason</th><th>Intent</th>
      <th>Actions</th>
    </tr>
    {% for c in cases %}
    <tr>
      <td>{{ c.id }}</td>
      <td>{{ c.scheme_code }}</td>
      <td>{{ c.status }}</td>
      <td>{{ c.locale }}</td>
      <td>{{ '%.2f'|format(c.review_confidence) if c.review_confidence is not none else '-' }}</td>
      <td>{{ '⚠️' if c.audit_flag else '' }}</td>
      <td>{{ c.flag_reason or '-' }}</td>
      <td>{{ c.intent_label or '-' }}</td>
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
    q = db.query(Case)

    # Filters
    flags_only = request.query_params.get("flags") == "true"
    min_conf = request.query_params.get("min_conf")
    if scheme:
        q = q.filter(Case.scheme_code == scheme)
    if status:
        q = q.filter(Case.status == status)
    if flags_only:
        q = q.filter(Case.audit_flag == True)
    if min_conf:
        try:
            q = q.filter(Case.review_confidence >= float(min_conf))
        except ValueError:
            pass

    # Sort: flags first, high confidence next, newest last
    q = q.order_by(Case.audit_flag.desc(), Case.review_confidence.desc(), Case.created_at.desc().nullslast())
    items = q.limit(50).all()

    # Insight strip
    ready = db.query(Case).filter(Case.review_confidence >= 0.7).count()
    needs = db.query(Case).filter((Case.review_confidence < 0.7) | (Case.review_confidence.is_(None))).count()
    flags = db.query(Case).filter(Case.audit_flag == True).count()

    statuses = [s.value for s in StatusEnum]
    schemes = ["UJJ", "PMAY"]
    return TEMPLATE.render(
        cases=items, statuses=statuses, schemes=schemes,
        sel_scheme=scheme or "", sel_status=status or "",
        sel_flags=flags_only, sel_min_conf=min_conf or "",
        ready=ready, needs=needs, flags=flags
    )

@router.post("/dashboard/update")
async def dashboard_update(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    case_id = form.get("id")
    status = form.get("status")

    obj = db.query(Case).filter(Case.id == case_id).first()
    if not obj: raise HTTPException(404, detail="Case not found")
    if status not in [s.value for s in StatusEnum]: raise HTTPException(400, detail="Invalid status")

    obj.status = status
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)