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
# SOP CONSTRAINTS (RELAXED FOR PILOT)
# -------------------------
RISK_HIGH_THRESHOLD = 0.70

# Defines what shows up in the dropdown
ALLOWED_REASONS_BY_ACTION: dict[str, set[str]] = {
    "APPROVE": {"OTHER"},
    "REQUEST_DOCS": {"DOCS_MISSING", "MISMATCH", "OTHER"},
    "ESCALATE": {"MISMATCH", "OTHER"},
    "REJECT": {"RULE_FAIL", "MISMATCH", "FRAUD_SUSPECTED", "DOCS_MISSING", "OTHER"},
}

# LOGIC MAP: Which actions are allowed for which Rule Result
ALLOWED_ACTIONS_BY_RULE: dict[str, set[str]] = {
    "ELIGIBLE_BY_RULE": {"APPROVE", "REQUEST_DOCS", "ESCALATE", "REJECT"},
    "UNKNOWN_NEEDS_DOCS": {"REQUEST_DOCS", "ESCALATE", "REJECT"},
    "INELIGIBLE_BY_RULE": {"REJECT", "ESCALATE"},
}

class DispositionIn(BaseModel):
    id: str
    final_action: str
    reason_code: str
    operator_id: str
    rule_result: str | None = None
    opened_at: str | None = None
    
    # --- ETHNOGRAPHIC DATA ---
    operator_comment: str | None = None
    flagged: bool = False


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
        q = q.filter(Case.status == StatusEnum(status))
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
        dur = (b - a).total_seconds()
        if dur > 0:
            vals.append(dur)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _verification_value(c: Case) -> str | None:
    if not hasattr(c, "verification_status"):
        return None
    v = getattr(c, "verification_status", None)
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


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
      --surface: #ffffff;
      --border: #e2e8f0;
      --text: #1f2933;
      --muted: #6b7280;
      --danger: #ef4444;
      --success: #15803d;
      --warn: #b45309;
    }
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; background: var(--saral-bg); color: var(--text); }
    
    .shell { max-width: 1400px; margin: 0 auto; padding: 22px 18px 40px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .brand { display:flex; align-items:center; gap:12px; }
    .logo-img { height: 44px; width:auto; }
    .brand-title { font-family: "Georgia", serif; font-size: 26px; letter-spacing: 0.05em; color:#5c8aff; }
    .brand-sub { font-size: 12px; text-transform: uppercase; letter-spacing: 0.15em; color: #666; }
    .badge { background:#e5e5e5; color:#666; padding:6px 14px; border-radius:999px; font-size:13px; font-weight: 700; }

    .summary {
      background: var(--surface);
      border-radius: 14px;
      border: 1px solid var(--border);
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

    table {
      width:100%; border-collapse: collapse; background: var(--surface);
      border-radius: 14px; overflow: hidden; border: 1px solid var(--border); font-size: 13px;
    }
    th, td { padding: 11px 12px; text-align:left; border-bottom:1px solid #edf2f7; }
    th { background: #f8fafc; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
    tr:hover { background: #f8fafc; cursor: pointer; }

    .pill { padding: 4px 10px; border-radius:999px; font-size:11px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; }
    .st-NEW { background:#e0f2fe; color:#0369a1; }
    .st-IN_REVIEW { background:#fef3c7; color:#b45309; }
    .st-APPROVED { background:#dcfce7; color:#15803d; }
    .st-REJECTED { background:#fee2e2; color:#b91c1c; }

    /* Modal */
    .modal-backdrop { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(15, 23, 42, 0.6); z-index: 100; backdrop-filter: blur(2px); }
    .modal { 
        position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); 
        width: 90%; max-width: 1000px; height: 85vh; 
        background: var(--surface); border-radius: 16px; 
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        display: flex; flex-direction: column; overflow: hidden;
    }
    .modal-header { padding: 18px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #f8fafc; }
    .modal-title { font-size: 18px; font-weight: 700; color: var(--text); }
    .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--muted); }
    .modal-body { flex: 1; display: grid; grid-template-columns: 2fr 1fr; overflow: hidden; }
    .col-left { padding: 24px; overflow-y: auto; border-right: 1px solid var(--border); }
    .col-right { padding: 24px; background: #fafafa; display: flex; flex-direction: column; gap: 20px; border-left: 1px solid var(--border); }

    .section { margin-bottom: 24px; }
    .section-title { font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 700; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
    .data-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .data-item label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; }
    .data-item span { font-size: 14px; font-weight: 600; color: var(--text); }
    .data-item.full { grid-column: span 2; }

    .sop-box { background: #eff6ff; padding: 16px; border-radius: 8px; border: 1px solid #dbeafe; font-size: 12px; line-height: 1.5; color: #1e40af; }
    .sop-box ul { padding-left: 16px; margin: 8px 0 0; }

    .decision-area { margin-top: auto; padding-top: 20px; border-top: 1px solid var(--border); }
    .btn-group { display: flex; gap: 10px; margin-bottom: 12px; }
    .btn { flex: 1; padding: 12px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; text-align: center; background: white; }
    
    .btn.approve:hover, .btn.approve.selected { background: var(--success); color: white; border-color: var(--success); }
    .btn.reject:hover, .btn.reject.selected { background: var(--danger); color: white; border-color: var(--danger); }
    .btn.review:hover, .btn.review.selected { background: var(--warn); color: white; border-color: var(--warn); }

    .input-row { margin-bottom: 10px; }
    .input-row select, .input-row input, .input-row textarea { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border); font-size: 13px; font-family: inherit; }
    .submit-btn { width: 100%; padding: 14px; background: #334155; color: white; border: none; border-radius: 8px; font-weight: 700; cursor: pointer; margin-top: 10px; }
    
    .risk-badge { padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 10px; border: 1px solid transparent; }
    .risk-HIGH { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
    .risk-MED { background: #ffedd5; color: #9a3412; border-color: #fed7aa; }
    .risk-LOW { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
    
    .mono { font-family: ui-monospace, monospace; }
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
    <div class="badge">Field Pilot v1.3</div>
  </header>

  <div class="summary">
    <strong>Stats:</strong>
    <span class="chip warn">In Review: {{ in_review }}</span>
    <span class="chip">Approved: {{ approved }}</span>
    <span class="chip bad">Rejected: {{ rejected }}</span>
    <span class="chip">Avg Time: {{ avg_triage_seconds }}s</span>
    <a href="/cases/export.csv" style="margin-left:auto; font-weight:700; text-decoration:none; color:var(--saral-blue);">⬇ Export CSV</a>
  </div>

  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Scheme</th>
        <th>Status</th>
        <th>Arm</th>
        <th>Docs Req.</th>
        <th>Verification</th>
        <th>AI Risk</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {% for c in cases %}
      <tr onclick='openCase({{ c | tojson | safe }})'>
        <td class="mono">{{ c.id[:8] }}</td>
        <td><strong>{{ c.scheme_code }}</strong></td>
        <td><span class="pill st-{{ c.status }}">{{ c.status }}</span></td>
        <td class="mono">{{ c.arm }}</td>
        
        <td>{{ c.docs_count }} Required</td>
        
        <td>
            {% if c.verification_status == "ID_SEEN_PHYSICAL" %}
                <span style="color:var(--success); font-weight:700;">✓ Verified</span>
            {% elif c.verification_status == "NO_ID_PRESENTED" %}
                <span style="color:var(--danger); font-weight:700;">✗ No ID</span>
            {% else %}
                <span style="color:var(--muted);">—</span>
            {% endif %}
            
            {% if c.has_house_risk %}
                <span title="Potential House Owner Detected in Notes" style="cursor:help; margin-left:6px; font-size:14px;">🏠⚠️</span>
            {% endif %}
        </td>
        <td>
            {% if c.arm == "TREATMENT" %}
                {{ c.risk_disp }} ({{ c.risk_band_disp }})
            {% else %}
                <span style="color:#cbd5e1;">(Blinded)</span>
            {% endif %}
        </td>
        <td><button class="btn" style="padding:4px 12px; font-size:11px; background:#f1f5f9;">Review</button></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="modal-backdrop" id="backdrop">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-title">Review Case <span id="m-id" class="mono" style="color:#666;"></span></div>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    
    <div class="modal-body">
      <div class="col-left">
        <div class="section">
            <div class="section-title">1. Document Checklist (System Requirements)</div>
            <div class="data-grid">
                <div class="data-item full">
                    <label>Required Documents for {{ scheme }}</label>
                    <ul id="m-docs-list" style="padding-left:16px; margin:4px 0; font-size:13px; color:#1e293b; line-height:1.5;"></ul>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">2. Physical Verification (Field Data)</div>
            <div class="data-grid">
                <div class="data-item">
                    <label>Verification Status</label>
                    <span id="m-verif-status"></span>
                </div>
                <div class="data-item full">
                    <label>Operator Notes (Crucial Context)</label>
                    <span id="m-verif-note" style="font-weight:400; color:#334155; background:#f1f5f9; padding:10px; border-radius:6px; display:block; border-left:3px solid #cbd5e1;"></span>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">3. Eligibility Rules</div>
            <div class="data-grid">
                <div class="data-item">
                    <label>Rule Result</label>
                    <span id="m-rule-res"></span>
                </div>
            </div>
        </div>
      </div>

      <div class="col-right">
        <div id="m-risk-box">
            <div class="section-title">4. AI Risk Score</div>
            <div id="m-risk-badge" class="risk-badge">
                <span class="risk-score" id="m-risk-score"></span>
                <span class="risk-label" id="m-risk-band"></span>
            </div>
            <div style="font-size:11px; color:#64748b;">
                <strong>Factors:</strong>
                <ul id="m-risk-factors" style="padding-left:16px; margin-top:4px;"></ul>
            </div>
        </div>

        <div class="sop-box">
            <strong>⚖️ Protocol:</strong>
            <ul>
                <li>Match "Required Docs" with "Operator Notes".</li>
                <li>If Note says "Pakka House" → <strong>REJECT</strong>.</li>
                <li>If Verification is "No ID" → <strong>REJECT</strong>.</li>
            </ul>
        </div>

        <div class="decision-area">
            <div class="section-title">5. Disposition</div>
            <input type="hidden" id="d-case-id">
            <input type="hidden" id="d-rule-res">
            
            <div class="input-row">
                <label style="font-size:11px; font-weight:700;">Operator ID</label>
                <input type="text" id="d-op-id" placeholder="OP_ID" value="VOLUNTEER_1">
            </div>
            
            <div style="margin-bottom:12px; display:flex; align-items:center; gap:8px; font-size:13px; color:#b45309; font-weight:500;">
                <input type="checkbox" id="d-flag">
                <label for="d-flag">Flag for discussion (Unsure)</label>
            </div>

            <div class="btn-group">
                <div class="btn approve" onclick="selectAction('APPROVE')">APPROVE</div>
                <div class="btn reject" onclick="selectAction('REJECT')">REJECT</div>
                <div class="btn review" onclick="selectAction('REQUEST_DOCS')">DOCS</div>
            </div>
            <input type="hidden" id="d-action">

            <div class="input-row">
                <select id="d-reason">
                    <option value="" disabled selected>Reason Code...</option>
                    {% for r in reasons %}
                    <option value="{{ r }}">{{ r }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="input-row">
                <textarea id="d-comment" rows="2" placeholder="Research Note: Why did you reject? (e.g. 'Has home in Bihar', 'Income Mismatch')"></textarea>
            </div>

            <button class="submit-btn" id="btn-submit" onclick="submitDisposition()">CONFIRM</button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
  const ACTIONS_BY_RULE = {{ actions_by_rule_json | safe }};
  const REASONS_BY_ACTION = {{ reasons_by_action_json | safe }};
  
  let caseTimers = {};
  let currentCaseId = null;

  // Restore Operator ID from LocalStorage
  document.addEventListener("DOMContentLoaded", () => {
    const savedOp = localStorage.getItem("saral_operator_id");
    if (savedOp) {
        document.getElementById('d-op-id').value = savedOp;
    }
  });

  function openCase(c) {
    currentCaseId = c.id;
    if (!caseTimers[c.id]) caseTimers[c.id] = new Date().toISOString();

    document.getElementById('m-id').innerText = c.id.substring(0, 8);
    document.getElementById('d-case-id').value = c.id;
    document.getElementById('d-rule-res').value = c.rule_result;

    // 1. Requirements Checklist
    const ul = document.getElementById('m-docs-list');
    ul.innerHTML = '';
    if (c.documents && c.documents.length > 0) {
        c.documents.forEach(doc => {
            const li = document.createElement('li');
            li.innerText = doc;
            ul.appendChild(li);
        });
    } else {
        ul.innerHTML = '<li style="color:#94a3b8; font-style:italic;">No specific docs required by rule engine.</li>';
    }

    // 2. Verification & WARNING SYSTEM
    const vStat = document.getElementById('m-verif-status');
    const vNote = document.getElementById('m-verif-note');
    
    // Status Display
    vStat.innerText = c.verification_status;
    vStat.style.color = (c.verification_status === 'ID_SEEN_PHYSICAL') ? '#15803d' : '#ef4444';
    vStat.style.fontWeight = '700';

    // ---- NEW DANGER DETECTION LOGIC ----
    const noteText = (c.verification_note || "").toLowerCase();
    const housingRisk = ["pakka", "owns", "already has", "has a house", "home", "flat"].some(k => noteText.includes(k));
    const noIdRisk = (c.verification_status === "NO_ID_PRESENTED" && c.rule_result === "ELIGIBLE_BY_RULE");
    
    let warningHTML = "";
    if (housingRisk) {
        warningHTML += "<div style='margin-top:8px; font-weight:700; color:#b91c1c; border-top:1px solid #fecaca; padding-top:4px;'>⚠️ STOP: Note mentions 'House'. Check PMAY eligibility.</div>";
    }
    if (noIdRisk) {
        warningHTML += "<div style='margin-top:8px; font-weight:700; color:#b91c1c; border-top:1px solid #fecaca; padding-top:4px;'>⛔ STOP: No ID Presented. Must REJECT (Even if Eligible).</div>";
    }

    if (housingRisk || noIdRisk) {
        vNote.style.backgroundColor = "#fee2e2"; // Red Alert BG
        vNote.style.borderLeftColor = "#ef4444"; 
        vNote.style.color = "#7f1d1d";
        vNote.innerHTML = (c.verification_note || "No notes") + warningHTML;
    } else {
        vNote.innerText = c.verification_note || "No notes provided.";
        vNote.style.backgroundColor = "#f1f5f9";
        vNote.style.borderLeftColor = "#cbd5e1";
        vNote.style.color = "#334155";
    }
    // -------------------------------------
    
    // 3. Rules
    document.getElementById('m-rule-res').innerText = c.rule_result;
    
    // 4. AI Risk
    const riskBox = document.getElementById('m-risk-box');
    if (c.arm === 'CONTROL') {
        riskBox.style.display = 'none';
    } else {
        riskBox.style.display = 'block';
        document.getElementById('m-risk-score').innerText = c.risk_disp;
        document.getElementById('m-risk-band').innerText = c.risk_band_disp;
        document.getElementById('m-risk-badge').className = 'risk-badge risk-' + c.risk_band_disp; 
        
        const rul = document.getElementById('m-risk-factors');
        rul.innerHTML = '';
        if (c.top_reasons_disp && c.top_reasons_disp !== '—') {
            c.top_reasons_disp.split(',').forEach(r => {
                const li = document.createElement('li');
                li.innerText = r.trim();
                rul.appendChild(li);
            });
        }
    }

    // Reset Controls
    document.getElementById('d-action').value = "";
    document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('selected'));
    document.getElementById('d-reason').value = "";
    document.getElementById('d-comment').value = "";
    document.getElementById('d-flag').checked = false;
    
    document.getElementById('backdrop').style.display = 'block';
  }

  function closeModal() {
    document.getElementById('backdrop').style.display = 'none';
    currentCaseId = null;
  }

  function selectAction(act) {
    document.getElementById('d-action').value = act;
    document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('selected'));
    
    if(act === 'APPROVE') document.querySelector('.btn.approve').classList.add('selected');
    if(act === 'REJECT') document.querySelector('.btn.reject').classList.add('selected');
    if(act === 'REQUEST_DOCS') document.querySelector('.btn.review').classList.add('selected');

    const reasonSel = document.getElementById('d-reason');
    const allowed = REASONS_BY_ACTION[act] || [];
    
    Array.from(reasonSel.options).forEach(opt => {
        if (opt.value === "") return;
        opt.hidden = !allowed.includes(opt.value);
    });
    reasonSel.value = "";
  }

  async function submitDisposition() {
    const caseId = document.getElementById('d-case-id').value;
    const finalAction = document.getElementById('d-action').value;
    const reasonCode = document.getElementById('d-reason').value;
    const opId = document.getElementById('d-op-id').value;
    const rr = document.getElementById('d-rule-res').value;
    
    const comment = document.getElementById('d-comment').value;
    const flagged = document.getElementById('d-flag').checked;

    if (!finalAction) { alert("Select Action"); return; }
    if (!reasonCode) { alert("Select Reason"); return; }
    if (!opId) { alert("Enter Operator ID"); return; }
    
    localStorage.setItem("saral_operator_id", opId);

    const btn = document.getElementById('btn-submit');
    btn.disabled = true;
    btn.innerText = "Saving...";

    try {
        const res = await fetch("/dashboard/disposition", {
            method: "POST",
            headers: { "Content-Type":"application/json" },
            body: JSON.stringify({
                id: caseId,
                rule_result: rr,
                final_action: finalAction,
                reason_code: reasonCode,
                operator_id: opId,
                operator_comment: comment,
                flagged: flagged,
                opened_at: caseTimers[caseId] || null
            })
        });

        if (res.ok) {
            window.location.reload();
        } else {
            const d = await res.json();
            alert("Error: " + (d.detail || "Failed"));
            btn.disabled = false;
            btn.innerText = "CONFIRM";
        }
    } catch (e) {
        alert("Network Error");
    }
  }
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
        ver = _verification_value(c)
        docs_count = len(docs)
        rr = c.rule_result.value if c.rule_result else "-"
        
        # PRE-CALC RISK FLAGS FOR TEMPLATE
        note_text = (c.verification_note or "").lower()
        has_house_risk = any(k in note_text for k in ["pakka", "owns", "has a house", "home", "flat"])

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
                "documents": docs,
                "docs_count": docs_count,
                "verification_status": ver or "—",
                "verification_note": c.verification_note or "",
                "risk_disp": risk_disp,
                "risk_band_disp": risk_band_disp,
                "top_reasons_disp": top_reasons_disp,
                "top_reasons_tooltip": top_reasons_tooltip,
                "final_action": (c.final_action.value if c.final_action else ""),
                "reason_code": (c.reason_code.value if c.reason_code else ""),
                "operator_id": getattr(c, "operator_id", None),
                # New Flag for UI
                "has_house_risk": has_house_risk,
            }
        )

    filtered = db.query(Case)
    filtered = _apply_filters(filtered, scheme, status, arm, since_dt)

    in_review = filtered.filter(Case.status == StatusEnum.IN_REVIEW).count()
    approved = filtered.filter(Case.status == StatusEnum.APPROVED).count()
    rejected = filtered.filter(Case.status == StatusEnum.REJECTED).count()
    n_control = filtered.filter(Case.arm == "CONTROL").count()
    n_treatment = filtered.filter(Case.arm == "TREATMENT").count()

    decided_pairs = (
        filtered.with_entities(Case.opened_at, Case.decided_at)
        .filter(Case.opened_at.isnot(None))
        .filter(Case.decided_at.isnot(None))
        .all()
    )
    avg_triage = _avg_seconds([(a, b) for (a, b) in decided_pairs])
    avg_triage_seconds = "—" if avg_triage is None else f"{avg_triage:.0f}"

    statuses = _enum_values(StatusEnum)
    schemes = ["UJJ", "PMAY"]
    actions = _enum_values(FinalActionEnum)
    reasons = _enum_values(ReasonCodeEnum)

    actions_by_rule_json = json.dumps({k: sorted(list(v)) for k, v in ALLOWED_ACTIONS_BY_RULE.items()}, ensure_ascii=False)
    reasons_by_action_json = json.dumps({k: sorted(list(v)) for k, v in ALLOWED_REASONS_BY_ACTION.items()}, ensure_ascii=False)
    
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
        avg_triage_seconds=avg_triage_seconds,
        actions_by_rule_json=actions_by_rule_json,
        reasons_by_action_json=reasons_by_action_json,
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

    if payload.opened_at:
        try:
            obj.opened_at = datetime.fromisoformat(payload.opened_at.replace('Z', '+00:00'))
        except ValueError:
            obj.opened_at = _utcnow()
    elif obj.opened_at is None:
        obj.opened_at = _utcnow()

    obj.final_action = FinalActionEnum(final_action)
    obj.reason_code = ReasonCodeEnum(reason_code)
    obj.operator_id = operator_id
    obj.decided_at = _utcnow()
    obj.sop_version = obj.sop_version or "SOP_v1"

    # --- SAVE NEW FIELDS ---
    if hasattr(obj, 'operator_comment'):
        obj.operator_comment = payload.operator_comment
    if hasattr(obj, 'flagged'):
        obj.flagged = payload.flagged

    if final_action == FinalActionEnum.REQUEST_DOCS.value:
        obj.status = StatusEnum.IN_REVIEW
    elif final_action == FinalActionEnum.APPROVE.value:
        obj.status = StatusEnum.APPROVED
    elif final_action == FinalActionEnum.REJECT.value:
        obj.status = StatusEnum.REJECTED
    else:
        obj.status = StatusEnum.IN_REVIEW

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
                # Research Data
                "operator_comment": payload.operator_comment,
                "flagged": payload.flagged,
                "decision_support_shown": bool(getattr(obj, "decision_support_shown", False)),
                "risk_score": obj.risk_score,
                "override_flag": obj.override_flag,
                "sop_version": obj.sop_version,
                "latency_seconds": (obj.decided_at - obj.opened_at).total_seconds() if obj.opened_at else None
            },
            ensure_ascii=False,
        ),
    )
    db.add(evt)
    db.commit()

    return JSONResponse({"ok": True})