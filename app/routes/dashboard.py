# app/routes/dashboard.py
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from ..db import get_db
from ..models import Case, StatusEnum
from jinja2 import Template

router = APIRouter(tags=["dashboard"])

# --- THE UI TEMPLATE (Your Design) ---
TEMPLATE = Template("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SARAL · Operator Console</title>
  <style>
    :root {
      --saral-navy: #053047;
      --saral-blue: #4f8cff;
      --saral-mint: #2ed3b7;
      --saral-bg: #f5f2eb;
      --saral-surface: #ffffff;
      --saral-border: #e2e8f0;
      --saral-text: #1f2933;
      --saral-muted: #6b7280;
    }

    * { box-sizing: border-box; }

    body {
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 0;
      background: var(--saral-bg);
      color: var(--saral-text);
    }

    .shell {
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px 20px 40px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(0,0,0,0.05);
    }

    .brand-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .logo-img {
        height: 48px;
        width: auto;
    }

    .brand-text-col {
        display: flex;
        flex-direction: column;
        line-height: 1.1;
    }

    .brand-title {
        font-family: "Georgia", serif;
        font-size: 28px;
        color: #5c8aff; /* Periwinkle blue from image */
        letter-spacing: 0.05em;
    }

    .brand-sub {
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: #666;
    }

    .top-meta-badge {
        background: #e5e5e5;
        color: #666;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 500;
    }

    .toolbar-card {
      background: var(--saral-surface);
      border-radius: 14px;
      border: 1px solid var(--saral-border);
      padding: 12px 14px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .toolbar-card form {
      display: flex;
      flex-wrap: wrap;
      gap: 15px;
      align-items: center;
      margin: 0;
    }

    label {
      font-size: 13px;
      color: var(--saral-muted);
      font-weight: 500;
    }

    select, input[type="number"] {
      margin-left: 4px;
      padding: 6px 8px;
      border-radius: 6px;
      border: 1px solid var(--saral-border);
      background: #fff;
      font-size: 13px;
    }

    button {
      padding: 8px 16px;
      border-radius: 6px;
      border: none;
      background: var(--saral-blue);
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }

    button:hover { filter: brightness(0.95); }

    .muted-link {
      font-size: 12px;
      color: var(--saral-muted);
      text-decoration: none;
      margin-left: 10px;
    }

    .muted-link:hover { text-decoration: underline; }

    .ai-summary {
      background: var(--saral-surface);
      border-radius: 14px;
      border: 1px solid var(--saral-border);
      padding: 10px 14px;
      font-size: 13px;
      margin-bottom: 18px;
      display: flex;
      gap: 16px;
      align-items: center;
    }

    .ai-chip {
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 12px;
      background: #e0f2fe;
      color: #075985;
      font-weight: 500;
    }

    .ai-chip.attn { background: #fef3c7; color: #92400e; }
    .ai-chip.flag { background: #fee2e2; color: #991b1b; }

    table {
      border-collapse: collapse;
      width: 100%;
      background: var(--saral-surface);
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--saral-border);
      font-size: 13px;
    }

    th, td {
      padding: 12px 15px;
      text-align: left;
      border-bottom: 1px solid #edf2f7;
    }

    th {
      background: #f8fafc;
      color: #475569;
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    tr:last-child td { border-bottom: none; }

    .status-pill {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .status-NEW { background: #e0f2fe; color: #0369a1; }
    .status-IN_REVIEW { background: #fef3c7; color: #b45309; }
    .status-APPROVED { background: #dcfce7; color: #15803d; }
    .status-REJECTED { background: #fee2e2; color: #b91c1c; }

    .conf-text { font-variant-numeric: tabular-nums; font-family: monospace; }
    .flag-cell { font-size: 16px; text-align: center; }
    .reason-cell { max-width: 200px; color: var(--saral-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .reason-cell:hover { white-space: normal; overflow: visible; }

    .inline-form {
      display: inline-flex;
      gap: 6px;
      align-items: center;
    }

    .inline-form select { margin-left: 0; padding: 4px; }
    .inline-form button { padding: 4px 10px; font-size: 11px; background: #334155; }

    @media (max-width: 768px) {
      .shell { padding: 16px 12px 24px; }
      .toolbar-card form { flex-direction: column; align-items: flex-start; }
      table { display: block; overflow-x: auto; white-space: nowrap; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand-left">
        <!-- Make sure /static/assets/saral.png exists or use a placeholder -->
        <img src="/static/assets/saral.png" class="logo-img" alt="SARAL" onerror="this.style.display='none'">
        <div class="brand-text-col">
            <div class="brand-title">SARAL</div>
            <div class="brand-sub">Assistant</div>
        </div>
      </div>
      <div class="top-meta-badge">
        Field Pilot v1.3
      </div>
    </header>

    <div class="toolbar-card">
      <form method="get" action="/dashboard">
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
        <label style="display:flex; align-items:center; gap:5px;">
            <input type="checkbox" name="flags" value="true" {{ 'checked' if sel_flags else '' }}> 
            Flags only
        </label>
        <label>Min Conf.
          <input type="number" step="0.05" min="0" max="1" name="min_conf" value="{{ sel_min_conf or '' }}" style="width:5rem">
        </label>
        <button type="submit">Filter</button>
        <a class="muted-link" href="/metrics/">Metrics JSON</a>
      </form>
    </div>

    <div class="ai-summary">
      <strong>AI Status:</strong>
      <span class="ai-chip">Ready (≥0.7): {{ ready }}</span>
      <span class="ai-chip attn">Review: {{ needs }}</span>
      <span class="ai-chip flag">Audit Flags: {{ flags }}</span>
    </div>

    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Scheme</th>
          <th>Status</th>
          <th>Arm</th>
          <th>Conf.</th>
          <th>Flag</th>
          <th>Reason / Notes</th>
          <th>Intent</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
      {% for c in cases %}
      <tr>
        <td title="{{ c.id }}" style="font-family:monospace; color:#666;">
            {{ c.id[:8] }}...
        </td>
        <td><strong>{{ c.scheme_code }}</strong></td>
        <td>
          <span class="status-pill status-{{ c.status }}">
            {{ c.status }}
          </span>
        </td>
        <td style="font-size:11px; color:#666;">{{ c.arm }}</td>
        <td class="conf-text">
          {{ '%.2f'|format(c.review_confidence) if c.review_confidence is not none else '🙈' }}
        </td>
        <td class="flag-cell">{{ '⚠️' if c.audit_flag else '' }}</td>
        <td class="reason-cell" title="{{ c.flag_reason }}">
            {{ c.flag_reason or '-' }}
        </td>
        <td>{{ c.intent_label or '-' }}</td>
        <td>
          <form method="post" action="/dashboard/update" class="inline-form">
            <input type="hidden" name="id" value="{{ c.id }}">
            <select name="status">
              {% for s in statuses %}
                <option value="{{ s }}" {{ s == c.status and 'selected' or '' }}>{{ s }}</option>
              {% endfor %}
            </select>
            <button type="submit">✓</button>
          </form>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</body>
</html>
""")

# --- ROUTE LOGIC (THE BRAIN) ---

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    scheme: str | None = None, 
    status: str | None = None
):
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

    # Sort: Flags -> Low Confidence -> Newest
    q = q.order_by(
        Case.audit_flag.desc(), 
        Case.review_confidence.asc(), 
        Case.created_at.desc().nullslast()
    )
    
    items = q.limit(100).all()

    # KPI Strips
    ready = db.query(Case).filter(Case.review_confidence >= 0.7).count()
    needs = db.query(Case).filter((Case.review_confidence < 0.7) | (Case.review_confidence.is_(None))).count()
    flags = db.query(Case).filter(Case.audit_flag == True).count()

    statuses = [s.value for s in StatusEnum]
    schemes = ["UJJ", "PMAY"] # Ideally fetch distinct from DB or Config
    
    return TEMPLATE.render(
        cases=items, 
        statuses=statuses, 
        schemes=schemes,
        sel_scheme=scheme or "", 
        sel_status=status or "",
        sel_flags=flags_only, 
        sel_min_conf=min_conf or "",
        ready=ready, 
        needs=needs, 
        flags=flags
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
    
    # Return to the same filter view if possible (simple redirect for v1)
    return RedirectResponse(url="/dashboard", status_code=303)