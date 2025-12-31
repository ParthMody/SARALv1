# app/routes/dashboard.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template
from pydantic import BaseModel
from sqlalchemy import asc, desc, case as sa_case
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Case,
    FinalActionEnum,
    ReasonCodeEnum,
    StatusEnum,
    RuleResultEnum,
    ActionEnum,
    Event,
)

router = APIRouter(tags=["dashboard"])

# -------------------------
# SOP CONSTRAINTS (v1)
# -------------------------
RISK_HIGH_THRESHOLD = 0.70

# Allowed reason codes by final action (baseline guard)
ALLOWED_REASONS_BY_ACTION: dict[str, set[str]] = {
    "APPROVE": {"OTHER"},
    "REQUEST_DOCS": {"DOCS_MISSING", "MISMATCH", "OTHER"},
    "ESCALATE": {"MISMATCH", "OTHER"},
    "REJECT": {"RULE_FAIL", "MISMATCH", "FRAUD_SUSPECTED", "OTHER"},
}

# Allowed final actions by rule result (triage guard)
ALLOWED_ACTIONS_BY_RULE: dict[str, set[str]] = {
    "ELIGIBLE_BY_RULE": {"APPROVE", "REQUEST_DOCS", "ESCALATE", "REJECT"},
    "UNKNOWN_NEEDS_DOCS": {"REQUEST_DOCS", "ESCALATE", "REJECT"},
    "INELIGIBLE_BY_RULE": {"REJECT", "ESCALATE"},
}

# Optional extra constraint: block RULE_FAIL when rules say eligible/unknown (avoid nonsensical coding)
DISALLOW_REASON_WHEN_RULE: dict[str, set[str]] = {
    "ELIGIBLE_BY_RULE": {"RULE_FAIL"},
    "UNKNOWN_NEEDS_DOCS": {"RULE_FAIL"},
    # INELIGIBLE_BY_RULE allows RULE_FAIL
}


class DispositionIn(BaseModel):
    id: str
    final_action: str
    reason_code: str
    operator_id: str
    rule_result: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_values(e) -> list[str]:
    return [x.value for x in e]


def _parse_since(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid 'since' date. Use YYYY-MM-DD.")


def _apply_filters(q, scheme: str | None, status: str | None, arm: str | None, since_dt: datetime | None):
    if scheme:
        q = q.filter(Case.scheme_code == scheme)
    if status:
        try:
            q = q.filter(Case.status == StatusEnum(status))
        except Exception:
            pass
    if arm:
        q = q.filter(Case.arm == arm)
    if since_dt:
        q = q.filter(Case.created_at >= since_dt)
    return q


def _tooltip_list(xs: Iterable[str]) -> str:
    xs = list(xs or [])
    return "\n".join([str(x) for x in xs]) if xs else ""


def _avg_seconds(pairs: list[tuple[datetime | None, datetime | None]]) -> float | None:
    vals: list[float] = []
    for a, b in pairs:
        if a is None or b is None:
            continue
        vals.append((b - a).total_seconds())
    if not vals:
        return None
    return sum(vals) / len(vals)


def _validate_disposition(rule_result: str, final_action: str, reason_code: str) -> None:
    # Final action must be allowed for rule_result
    allowed_actions = ALLOWED_ACTIONS_BY_RULE.get(rule_result, set())
    if allowed_actions and final_action not in allowed_actions:
        raise HTTPException(
            400,
            f"Disposition not allowed for rule_result={rule_result}. Allowed: {sorted(list(allowed_actions))}",
        )

    # Reason code must be allowed for action
    allowed_reasons = ALLOWED_REASONS_BY_ACTION.get(final_action, set())
    if allowed_reasons and reason_code not in allowed_reasons:
        raise HTTPException(
            400,
            f"Reason code not allowed for final_action={final_action}. Allowed: {sorted(list(allowed_reasons))}",
        )

    # Disallow nonsensical combos by rule_result (v1 hygiene)
    disallowed = DISALLOW_REASON_WHEN_RULE.get(rule_result, set())
    if reason_code in disallowed:
        raise HTTPException(400, f"Reason code {reason_code} not allowed when rule_result={rule_result}.")


TEMPLATE = Template(
    r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SARAL · Operator Console</title>
  <style>
    :root {
      --saral-blue: #4f8cff;
      --saral-bg: #f5f2eb;
      --saral-surface: #ffffff;
      --saral-border: #e2e8f0;
      --saral-text: #1f2933;
      --saral-muted: #6b7280;
    }
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; background: var(--saral-bg); color: var(--saral-text); }
    .shell { max-width: 1200px; margin: 0 auto; padding: 22px 18px 40px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .brand { display:flex; align-items:center; gap:12px; }
    .logo-img { height: 44px; width:auto; }
    .brand-title { font-family: "Georgia", serif; font-size: 26px; letter-spacing: 0.05em; color:#5c8aff; }
    .brand-sub { font-size: 12px; text-transform: uppercase; letter-spacing: 0.15em; color: #666; }
    .badge { background:#e5e5e5; color:#666; padding:6px 14px; border-radius:999px; font-size:13px; }

    .toolbar {
      background: var(--saral-surface);
      border-radius: 14px;
      border: 1px solid var(--saral-border);
      padding: 12px 14px;
      margin: 10px 0 10px;
      display:flex; align-items:center; justify-content:space-between; gap:12px;
    }
    .toolbar form { display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin:0; }
    label { font-size: 13px; color: var(--saral-muted); font-weight: 600; }
    select, input[type="number"], input[type="date"], input[type="text"] {
      margin-left: 6px;
      padding: 6px 8px;
      border-radius: 8px;
      border: 1px solid var(--saral-border);
      background: #fff;
      font-size: 13px;
    }
    button, .linkbtn {
      padding: 8px 14px;
      border-radius: 10px;
      border: none;
      background: var(--saral-blue);
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      text-decoration:none;
      display:inline-flex;
      align-items:center;
      gap:8px;
    }
    .linkbtn.secondary { background:#334155; }
    .toolbar-right { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }

    .summary {
      background: var(--saral-surface);
      border-radius: 14px;
      border: 1px solid var(--saral-border);
      padding: 10px 14px;
      font-size: 13px;
      margin-bottom: 14px;
      display: flex;
      gap: 14px;
      align-items: center;
      flex-wrap: wrap;
    }
    .chip { padding: 3px 10px; border-radius: 999px; font-size: 12px; background: #e0f2fe; color: #075985; font-weight: 700; }
    .chip.warn { background:#fef3c7; color:#92400e; }
    .chip.bad { background:#fee2e2; color:#991b1b; }
    .chip.neutral { background:#eef2ff; color:#3730a3; }

    table {
      width:100%;
      border-collapse: collapse;
      background: var(--saral-surface);
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--saral-border);
      font-size: 13px;
    }
    th, td { padding: 11px 12px; text-align:left; border-bottom:1px solid #edf2f7; vertical-align: top; }
    th { background: #f8fafc; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
    tr:last-child td { border-bottom:none; }

    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; color:#666; }
    .pill { padding: 4px 10px; border-radius:999px; font-size:11px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
    .st-NEW { background:#e0f2fe; color:#0369a1; }
    .st-IN_REVIEW { background:#fef3c7; color:#b45309; }
    .st-APPROVED { background:#dcfce7; color:#15803d; }
    .st-REJECTED { background:#fee2e2; color:#b91c1c; }

    .reason { max-width: 260px; color: var(--saral-muted); white-space: nowrap; overflow:hidden; text-overflow: ellipsis; }
    .reason:hover { white-space: normal; overflow: visible; }

    .inline { display:inline-flex; gap:8px; align-items:center; }
    .inline select { margin-left:0; padding:5px 6px; border-radius:8px; }
    .inline button { padding:6px 10px; border-radius:10px; background:#334155; font-size:12px; }
    .muted { color: var(--saral-muted); font-size: 12px; font-style: italic; }

    .err { color:#991b1b; background:#fee2e2; border:1px solid #fecaca; padding:8px 10px; border-radius:10px; margin: 0 0 12px; font-size: 13px; }

    @media (max-width: 900px) {
      table { display:block; overflow-x:auto; white-space:nowrap; }
      .toolbar { flex-direction: column; align-items: flex-start; }
      .toolbar-right { width:100%; justify-content:flex-start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <img src="/static/assets/saral.png" class="logo-img" alt="SARAL" onerror="this.style.display='none'">
        <div>
          <div class="brand-title">SARAL</div>
          <div class="brand-sub">Operator Console</div>
        </div>
      </div>
      <div class="badge">Field Pilot v1</div>
    </header>

    {% if err_msg %}
      <div class="err">{{ err_msg }}</div>
    {% endif %}

    <div class="toolbar">
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

        <label>Arm
          <select name="arm">
            <option value="" {{ '' == sel_arm and 'selected' or '' }}>All</option>
            <option value="CONTROL" {{ 'CONTROL' == sel_arm and 'selected' or '' }}>CONTROL</option>
            <option value="TREATMENT" {{ 'TREATMENT' == sel_arm and 'selected' or '' }}>TREATMENT</option>
          </select>
        </label>

        <label>Since
          <input type="date" name="since" value="{{ sel_since or '' }}">
        </label>

        <button type="submit">Filter</button>
      </form>

      <div class="toolbar-right">
        <a class="linkbtn secondary"
           href="/cases/export.csv{% if sel_since %}?since={{ sel_since }}{% endif %}">
          Export CSV
        </a>
      </div>
    </div>

    <div class="summary">
      <strong>Counts:</strong>
      <span class="chip warn">In Review: {{ in_review }}</span>
      <span class="chip">Approved: {{ approved }}</span>
      <span class="chip bad">Rejected: {{ rejected }}</span>
      <span class="chip neutral">Overrides (T only): {{ override_rate_pct }}%</span>
      <span class="chip">Avg Triage Time (s): {{ avg_triage_seconds }}</span>
      <span class="chip">Control: {{ n_control }}</span>
      <span class="chip">Treatment: {{ n_treatment }}</span>
    </div>

    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Scheme</th>
          <th>Status</th>
          <th>Arm</th>
          <th>Rule</th>
          <th>Docs</th>
          <th>Risk</th>
          <th>Band</th>
          <th>Top Reasons</th>
          <th>Disposition</th>
        </tr>
      </thead>
      <tbody>
      {% for c in cases %}
      <tr data-rule="{{ c.rule_result }}" data-arm="{{ c.arm }}">
        <td class="mono" title="{{ c.id }}">{{ c.id[:8] }}…</td>
        <td><strong>{{ c.scheme_code }}</strong></td>
        <td><span class="pill st-{{ c.status }}">{{ c.status }}</span></td>
        <td class="mono">{{ c.arm }}</td>
        <td class="mono">{{ c.rule_result }}</td>
        <td title="{{ c.docs_tooltip }}">{{ c.docs_count }}</td>

        <td class="mono">{{ c.risk_disp }}</td>
        <td class="mono">{{ c.risk_band_disp }}</td>
        <td class="reason" title="{{ c.top_reasons_tooltip }}">{{ c.top_reasons_disp }}</td>

        <td>
          {% if c.rule_result == 'INELIGIBLE_BY_RULE' and c.arm == 'CONTROL' %}
            <span class="muted">No action required</span>
          {% else %}
            <div class="inline">
              <input type="hidden" data-role="case_id" value="{{ c.id }}">
              <input type="hidden" data-role="rule_result" value="{{ c.rule_result }}">

              <select data-role="final_action">
                {% for a in actions %}
                  <option value="{{ a }}" {{ 'selected' if a == c.final_action else '' }}>{{ a }}</option>
                {% endfor %}
              </select>

              <select data-role="reason_code">
                {% for r in reasons %}
                  <option value="{{ r }}" {{ 'selected' if r == c.reason_code else '' }}>{{ r }}</option>
                {% endfor %}
              </select>

              <input type="text" data-role="operator_id" placeholder="op_id" value="{{ c.operator_id or '' }}" style="width:6rem; padding:5px 6px; border-radius:8px; border:1px solid #e2e8f0;">

              <button type="button" class="disp-btn">✓</button>
            </div>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>

  </div>

<script>
  const ACTIONS_BY_RULE = {{ actions_by_rule_json | safe }};
  const REASONS_BY_ACTION = {{ reasons_by_action_json | safe }};
  const DISALLOW_REASON_WHEN_RULE = {{ disallow_reason_when_rule_json | safe }};

  function restrictSelectOptions(selectEl, allowedSet) {
    const opts = Array.from(selectEl.options);
    opts.forEach(o => {
      o.hidden = allowedSet && allowedSet.length ? !allowedSet.includes(o.value) : false;
      o.disabled = o.hidden;
    });

    if (allowedSet && allowedSet.length) {
      const current = selectEl.value;
      const visible = opts.filter(o => !o.hidden);
      if (!visible.some(o => o.value === current)) {
        if (visible.length) selectEl.value = visible[0].value;
      }
    }
  }

  function applyRowConstraints(container) {
    const tr = container.closest("tr");
    const rule = (tr.getAttribute("data-rule") || "").trim();

    const finalSel = container.querySelector('select[data-role="final_action"]');
    const reasonSel = container.querySelector('select[data-role="reason_code"]');

    const allowedActions = ACTIONS_BY_RULE[rule] || [];
    restrictSelectOptions(finalSel, allowedActions);

    const action = finalSel.value;
    const allowedReasons = (REASONS_BY_ACTION[action] || []).slice();

    const disallowed = DISALLOW_REASON_WHEN_RULE[rule] || [];
    const filteredReasons = allowedReasons.filter(r => !disallowed.includes(r));
    restrictSelectOptions(reasonSel, filteredReasons);
  }

  function fmtDetail(detail) {
    if (typeof detail === "string") return detail;
    try { return JSON.stringify(detail); } catch { return "Invalid request"; }
  }

  async function submitDispositionFromButton(btn) {
    const row = btn.closest("tr");
    const container = btn.closest(".inline");
    if (!row || !container) return;

    const rule = (row.getAttribute("data-rule") || "").trim();

    const finalAction = container.querySelector('select[data-role="final_action"]').value;
    const reasonCode  = container.querySelector('select[data-role="reason_code"]').value;
    const operatorId  = (container.querySelector('input[data-role="operator_id"]').value || "").trim();
    const caseId      = container.querySelector('input[data-role="case_id"]').value;
    const ruleResult  = container.querySelector('input[data-role="rule_result"]').value;

    if (!operatorId) { alert("operator_id is required."); return; }

    const allowedActions = ACTIONS_BY_RULE[rule] || [];
    if (allowedActions.length && !allowedActions.includes(finalAction)) {
      alert("Invalid disposition for this rule_result.");
      return;
    }

    const allowedReasons = (REASONS_BY_ACTION[finalAction] || []).slice();
    const disallowed = DISALLOW_REASON_WHEN_RULE[rule] || [];
    const filteredReasons = allowedReasons.filter(r => !disallowed.includes(r));
    if (filteredReasons.length && !filteredReasons.includes(reasonCode)) {
      alert("Invalid reason_code for this final_action.");
      return;
    }

    btn.disabled = true;
    const oldText = btn.innerText;
    btn.innerText = "…";

    try {
      const res = await fetch("/dashboard/disposition", {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify({
          id: caseId,
          rule_result: ruleResult,
          final_action: finalAction,
          reason_code: reasonCode,
          operator_id: operatorId
        })
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data && data.detail ? fmtDetail(data.detail) : ("Request failed (" + res.status + ")");
        alert(msg);
        return;
      }

      window.location.reload();
    } catch (e) {
      alert("Network error");
    } finally {
      btn.disabled = false;
      btn.innerText = oldText;
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".disp-btn");
    if (!btn) return;
    submitDispositionFromButton(btn);
  });

  document.addEventListener("change", (e) => {
    const sel = e.target;
    if (!(sel && sel.tagName === "SELECT")) return;
    const container = sel.closest(".inline");
    if (!container) return;
    applyRowConstraints(container);
  });

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".inline").forEach(c => applyRowConstraints(c));
  });
</script>

</body>
</html>
"""
)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    scheme: str | None = Query(None),
    status: str | None = Query(None),
    arm: str | None = Query(None),
    since: str | None = Query(None),
    err: str | None = Query(None),
):
    since_dt = _parse_since(since)

    base = db.query(Case)
    base = _apply_filters(base, scheme, status, arm, since_dt)

    items = (
        base.order_by(
            desc(Case.arm == "TREATMENT"),
            desc(Case.risk_score).nullslast(),
            desc(sa_case((Case.rule_result == RuleResultEnum.UNKNOWN_NEEDS_DOCS, 1), else_=0)),
            asc(Case.created_at),
        )
        .limit(160)
        .all()
    )

    view: list[dict[str, Any]] = []
    for c in items:
        docs = c.documents or []
        rr = c.rule_result.value if c.rule_result else "-"

        # Blinding in dashboard display
        if c.arm == "CONTROL":
            risk_disp = "—"
            risk_band_disp = "—"
            top_reasons_disp = "—"
            top_reasons_tooltip = ""
        else:
            risk_disp = "—" if c.risk_score is None else f"{c.risk_score:.2f}"
            risk_band_disp = c.risk_band or "—"
            trs = c.top_reasons or []
            top_reasons_disp = ", ".join(trs[:3]) if trs else "—"
            top_reasons_tooltip = _tooltip_list(trs)

        view.append(
            {
                "id": c.id,
                "scheme_code": c.scheme_code,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "arm": c.arm,
                "rule_result": rr,
                "docs_count": len(docs),
                "docs_tooltip": _tooltip_list(docs),
                "risk_disp": risk_disp,
                "risk_band_disp": risk_band_disp,
                "top_reasons_disp": top_reasons_disp,
                "top_reasons_tooltip": top_reasons_tooltip,
                "final_action": (c.final_action.value if c.final_action else ""),
                "reason_code": (c.reason_code.value if c.reason_code else ""),
                "operator_id": getattr(c, "operator_id", None),
            }
        )

    # Summary counts (same filter set)
    filtered = db.query(Case)
    filtered = _apply_filters(filtered, scheme, status, arm, since_dt)

    in_review = filtered.filter(Case.status == StatusEnum.IN_REVIEW).count()
    approved = filtered.filter(Case.status == StatusEnum.APPROVED).count()
    rejected = filtered.filter(Case.status == StatusEnum.REJECTED).count()
    n_control = filtered.filter(Case.arm == "CONTROL").count()
    n_treatment = filtered.filter(Case.arm == "TREATMENT").count()

    # Overrides (defensible): Treatment only
    override_n = filtered.filter(
        Case.arm == "TREATMENT",
        Case.decision_support_shown == True,  # noqa
        Case.risk_score.isnot(None),
        Case.risk_score >= RISK_HIGH_THRESHOLD,
        Case.final_action == FinalActionEnum.APPROVE,
    ).count()

    treatment_decided = filtered.filter(
        Case.arm == "TREATMENT",
        Case.decision_support_shown == True,  # noqa
        Case.final_action.isnot(None),
    ).count()

    override_rate = (override_n / treatment_decided) if treatment_decided else 0.0
    override_rate_pct = f"{override_rate * 100:.1f}"

    # Avg triage time: created_at -> opened_at (wait time)
    decided_pairs = (
        filtered.with_entities(Case.created_at, Case.opened_at)
        .filter(Case.opened_at.isnot(None))
        .all()
    )
    avg_triage = _avg_seconds([(a, b) for (a, b) in decided_pairs])
    avg_triage_seconds = "—" if avg_triage is None else f"{avg_triage:.0f}"

    statuses = _enum_values(StatusEnum)
    schemes = ["UJJ", "PMAY"]  # deterministic v1
    actions = _enum_values(FinalActionEnum)
    reasons = _enum_values(ReasonCodeEnum)

    actions_by_rule_json = json.dumps({k: sorted(list(v)) for k, v in ALLOWED_ACTIONS_BY_RULE.items()}, ensure_ascii=False)
    reasons_by_action_json = json.dumps({k: sorted(list(v)) for k, v in ALLOWED_REASONS_BY_ACTION.items()}, ensure_ascii=False)
    disallow_reason_when_rule_json = json.dumps({k: sorted(list(v)) for k, v in DISALLOW_REASON_WHEN_RULE.items()}, ensure_ascii=False)

    err_msg = None
    if err:
        try:
            err_msg = json.loads(err).get("msg")
        except Exception:
            err_msg = err

    return TEMPLATE.render(
        cases=view,
        statuses=statuses,
        schemes=schemes,
        actions=actions,
        reasons=reasons,
        sel_scheme=scheme or "",
        sel_status=status or "",
        sel_arm=arm or "",
        sel_since=since or "",
        in_review=in_review,
        approved=approved,
        rejected=rejected,
        n_control=n_control,
        n_treatment=n_treatment,
        override_rate_pct=override_rate_pct,
        avg_triage_seconds=avg_triage_seconds,
        actions_by_rule_json=actions_by_rule_json,
        reasons_by_action_json=reasons_by_action_json,
        disallow_reason_when_rule_json=disallow_reason_when_rule_json,
        err_msg=err_msg,
    )


@router.post("/dashboard/disposition")
def dashboard_disposition(payload: DispositionIn, db: Session = Depends(get_db)):
    case_id = (payload.id or "").strip()
    final_action = (payload.final_action or "").strip()
    reason_code = (payload.reason_code or "").strip()
    operator_id = (payload.operator_id or "").strip()
    rule_result_str = (payload.rule_result or "").strip()

    if not case_id:
        raise HTTPException(400, "Missing case id")
    if not operator_id:
        raise HTTPException(400, "operator_id is required")

    operator_id = operator_id.lower()

    obj = db.query(Case).filter(Case.id == case_id).first()
    if not obj:
        raise HTTPException(404, "Case not found")

    if final_action not in _enum_values(FinalActionEnum):
        raise HTTPException(400, "Invalid final_action")
    if reason_code not in _enum_values(ReasonCodeEnum):
        raise HTTPException(400, "Invalid reason_code")

    rr_db = obj.rule_result.value if obj.rule_result else (rule_result_str or "-")
    if rr_db == "-":
        rr_db = "UNKNOWN_NEEDS_DOCS"

    # Block disposition only for CONTROL + INELIGIBLE_BY_RULE (Treatment still allowed)
    if obj.arm == "CONTROL" and rr_db == RuleResultEnum.INELIGIBLE_BY_RULE.value:
        raise HTTPException(400, "Disposition disabled for CONTROL + INELIGIBLE_BY_RULE")

    _validate_disposition(rr_db, final_action, reason_code)

    if obj.opened_at is None:
        obj.opened_at = _utcnow()

    obj.final_action = FinalActionEnum(final_action)
    obj.reason_code = ReasonCodeEnum(reason_code)
    obj.operator_id = operator_id
    obj.decided_at = _utcnow()
    obj.sop_version = obj.sop_version or "SOP_v1"

    # Status mapping (DB update)
    if final_action == FinalActionEnum.REQUEST_DOCS.value:
        obj.status = StatusEnum.IN_REVIEW
    elif final_action == FinalActionEnum.APPROVE.value:
        obj.status = StatusEnum.APPROVED
    elif final_action == FinalActionEnum.REJECT.value:
        obj.status = StatusEnum.REJECTED
    else:
        obj.status = StatusEnum.IN_REVIEW

    # Override flag (defensible): Treatment only, decision support shown, high risk + approve
    if obj.arm == "TREATMENT" and bool(getattr(obj, "decision_support_shown", False)):
        obj.override_flag = bool(
            obj.risk_score is not None
            and obj.risk_score >= RISK_HIGH_THRESHOLD
            and obj.final_action == FinalActionEnum.APPROVE
        )
    else:
        obj.override_flag = None

    db.commit()

    evt = Event(
        case_id=obj.id,
        action=ActionEnum.OP_DISPOSITION,
        actor_type="OPERATOR",
        payload=json.dumps(
            {
                "rule_result": rr_db,
                "final_action": final_action,
                "reason_code": reason_code,
                "operator_id": operator_id,
                "decision_support_shown": bool(getattr(obj, "decision_support_shown", False)),
                "risk_score": obj.risk_score,
                "override_flag": obj.override_flag,
                "sop_version": obj.sop_version,
            },
            ensure_ascii=False,
        ),
    )
    db.add(evt)
    db.commit()

    return JSONResponse({"ok": True})
