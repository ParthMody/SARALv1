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
    <a href="/metrics/">Metrics (JSON)</a>
  </div>
  <table>
    <thead>
      <tr><th>ID</th><th>Scheme</th><th>Status</th><th>Locale</th><th>Actions</th></tr>
    </thead>
    <tbody>
      {% for c in cases %}
      <tr>
        <td>{{ c.id }}</td>
        <td>{{ c.scheme_code }}</td>
        <td><span class="pill">{{ c.status }}</span></td>
        <td>{{ c.locale }}</td>
        <td>
          {% for s in statuses %}
            {% if s != c.status %}
              <form method="post" action="/dashboard/update">
                <input type="hidden" name="id" value="{{ c.id }}">
                <input type="hidden" name="status" value="{{ s }}">
                <button type="submit">Set {{ s }}</button>
              </form>
            {% endif %}
          {% endfor %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
""")

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), scheme: str | None = None, status: str | None = None):
    q = db.query(Case)
    if scheme: q = q.filter(Case.scheme_code == scheme)
    if status: q = q.filter(Case.status == status)
    items = q.order_by(Case.created_at.desc().nullslast()).limit(50).all()
    statuses = [s.value for s in StatusEnum]
    return TEMPLATE.render(cases=items, statuses=statuses)

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
