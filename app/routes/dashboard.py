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
# SOP CONSTRAINTS (PILOT v1.3)
# -------------------------
RISK_HIGH_THRESHOLD = 0.70

ALLOWED_REASONS_BY_ACTION: dict[str, set[str]] = {
    "APPROVE": {"OTHER"},
    "REQUEST_DOCS": {"DOCS_MISSING", "MISMATCH", "OTHER"},
    "ESCALATE": {"MISMATCH", "OTHER"},
    "REJECT": {"RULE_FAIL", "MISMATCH", "FRAUD_SUSPECTED", "DOCS_MISSING", "OTHER"},
}

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


# --- Centralized Logic for "Eligibility Conflict Indicator" ---
# Checks for unstructured text indicating housing ineligibility (e.g., "pakka house")
def _check_housing_risk(note: str | None) -> bool:
    if not note:
        return False

    text = note.lower()

    # DANGER WORDS: suggest possible ownership / conflict
    danger_keywords = ["pakka", "owns", "owned", "flat", "apartment", "bungalow", "already has"]

    # DANGER PHRASES: generic words only risky in specific phrases
    danger_phrases = ["has a house", "has house", "has a home", "has home"]

    # SAFETY BRAKES: likely clarifying eligibility
    safety_keywords = ["not", "no ", "doesn", "rent", "kuccha", "kutcha", "temporary", "tin shed"]

    has_danger = any(k in text for k in danger_keywords) or any(p in text for p in danger_phrases)
    has_safety = any(s in text for s in safety_keywords)

    return has_danger and not has_safety


def _require_comment_min(comment: str | None, n: int) -> bool:
    return bool(comment and len(comment.strip()) >= n)


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

    /* Pagination */
    .pagination { display: flex; justify-content: space-between; align-items: center; padding: 12px 4px; margin-top: 10px; border-top: 1px solid var(--border); }
    .page-info { font-size: 12px; color: var(--muted); }
    .page-controls { display: flex; gap: 8px; align-items: center; }
    .btn-page { padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; text-decoration: none; color: var(--text); background: white; cursor: pointer; }
    .btn-page:hover:not(.disabled) { background: #f1f5f9; }
    .btn-page.disabled { opacity: 0.5; pointer-events: none; color: var(--muted); }
    .page-current { font-size: 12px; font-weight: 600; }

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
    .btn-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
    .btn { padding: 12px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 13px; text-align: center; background: white; user-select: none; }

    .btn.approve:hover, .btn.approve.selected { background: var(--success); color: white; border-color: var(--success); }
    .btn.reject:hover, .btn.reject.selected { background: var(--danger); color: white; border-color: var(--danger); }
    .btn.review:hover, .btn.review.selected { background: var(--warn); color: white; border-color: var(--warn); }
    .btn.escalate:hover, .btn.escalate.selected { background: #0f766e; color: white; border-color: #0f766e; }

    .input-row { margin-bottom: 10px; }
    .input-row select, .input-row input, .input-row textarea { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border); font-size: 13px; font-family: inherit; }
    .submit-btn { width: 100%; padding: 14px; background: #334155; color: white; border: none; border-radius: 8px; font-weight: 800; cursor: pointer; margin-top: 10px; }

    .risk-badge { padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 10px; border: 1px solid transparent; }
    .risk-HIGH { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
    .risk-MED { background: #ffedd5; color: #9a3412; border-color: #fed7aa; }
    .risk-LOW { background: #dcfce7; color: #166534; border-color: #bbf7d0; }

    .mono { font-family: ui-monospace, monospace; }

    .locked { pointer-events: none; opacity: 0.35; filter: grayscale(0.2); }
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

        <td title="{{ c.docs_tooltip }}">{{ c.docs_count }} Required</td>

        <td>
            {% if c.verification_status == "ID_SEEN_PHYSICAL" %}
                <span style="color:var(--success); font-weight:800;">✓ Verified</span>
            {% elif c.verification_status == "NO_ID_PRESENTED" %}
                <span style="color:var(--danger); font-weight:800;">✗ No ID</span>
            {% else %}
                <span style="color:var(--muted); font-weight:800;">—</span>
            {% endif %}

            {% if c.has_house_risk %}
                <span title="Eligibility conflict indicator in notes (verify evidence)" style="cursor:help; margin-left:6px; font-size:14px;">⚑</span>
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

  <div class="pagination">
    <div class="page-info">
        Showing <strong>{{ start_index }}</strong> - <strong>{{ end_index }}</strong> of <strong>{{ total_count }}</strong> cases
    </div>
    <div class="page-controls">
        {% if page > 1 %}
            <a href="?page={{ page - 1 }}{{ filter_qs }}" class="btn-page">← Previous</a>
        {% else %}
            <span class="btn-page disabled">← Previous</span>
        {% endif %}

        <span class="page-current">Page {{ page }} of {{ total_pages }}</span>

        {% if page < total_pages %}
            <a href="?page={{ page + 1 }}{{ filter_qs }}" class="btn-page">Next →</a>
        {% else %}
            <span class="btn-page disabled">Next →</span>
        {% endif %}
    </div>
  </div>
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
                    <label>Required Documents (Scheme: {{ sel_scheme or "—" }})</label>
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
                    <label>Field Notes (From Kiosk/Op 0)</label>
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
            <strong>Protocol:</strong>
            <ul>
                <li>Notes can indicate conflicts; they are not verdicts.</li>
                <li>Conflict indicator (⚑) → REQUEST_DOCS or ESCALATE + record evidence needed.</li>
                <li>No ID presented → do not APPROVE; REQUEST_DOCS or REJECT per evidence.</li>
                <li>Control arm is blinded; ignore AI section.</li>
            </ul>
        </div>

        <div class="decision-area">
            <div class="section-title">Disposition</div>
            <input type="hidden" id="d-case-id">
            <input type="hidden" id="d-rule-res">
            <input type="hidden" id="d-allowed-actions">
            <input type="hidden" id="d-house-risk">
            <input type="hidden" id="d-no-id-risk">

            <div class="input-row">
                <label style="font-size:11px; font-weight:800;">Operator ID</label>
                <input type="text" id="d-op-id" placeholder="OP_ID" value="VOLUNTEER_1">
            </div>

            <div style="margin-bottom:12px; display:flex; align-items:center; gap:8px; font-size:13px; color:#b45309; font-weight:600;">
                <input type="checkbox" id="d-flag">
                <label for="d-flag">Flag for discussion (Uncertain / needs verification)</label>
            </div>

            <div class="btn-group">
                <div class="btn approve" id="btn-approve" onclick="selectAction('APPROVE')">APPROVE</div>
                <div class="btn reject" id="btn-reject" onclick="selectAction('REJECT')">REJECT</div>
                <div class="btn review" id="btn-docs" onclick="selectAction('REQUEST_DOCS')">REQUEST DOCS</div>
                <div class="btn escalate" id="btn-escalate" onclick="selectAction('ESCALATE')">ESCALATE</div>
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
                <textarea id="d-comment" rows="3" placeholder="Evidence note (required for REJECT/ESCALATE and for conflict cases)."></textarea>
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

  document.addEventListener("DOMContentLoaded", () => {
    const savedOp = localStorage.getItem("saral_operator_id");
    if (savedOp) document.getElementById('d-op-id').value = savedOp;
  });

  function _setLocked(el, locked) {
    if (!el) return;
    if (locked) el.classList.add('locked');
    else el.classList.remove('locked');
  }

  function _resetActionUI() {
    document.getElementById('d-action').value = "";
    document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('selected'));
  }

  function _applyAllowedActions(allowed) {
    const a = new Set(allowed || []);
    _setLocked(document.getElementById('btn-approve'), !a.has('APPROVE'));
    _setLocked(document.getElementById('btn-reject'), !a.has('REJECT'));
    _setLocked(document.getElementById('btn-docs'), !a.has('REQUEST_DOCS'));
    _setLocked(document.getElementById('btn-escalate'), !a.has('ESCALATE'));
  }

  function openCase(c) {
    currentCaseId = c.id;
    if (!caseTimers[c.id]) caseTimers[c.id] = new Date().toISOString();

    document.getElementById('m-id').innerText = c.id.substring(0, 8);
    document.getElementById('d-case-id').value = c.id;
    document.getElementById('d-rule-res').value = c.rule_result;

    const allowedActions = ACTIONS_BY_RULE[c.rule_result] || [];
    document.getElementById('d-allowed-actions').value = JSON.stringify(allowedActions);
    _applyAllowedActions(allowedActions);

    // Docs
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

    // Verification
    const vStat = document.getElementById('m-verif-status');
    const vNote = document.getElementById('m-verif-note');

    vStat.innerText = c.verification_status;

    if (c.verification_status === 'ID_SEEN_PHYSICAL') {
        vStat.style.color = '#15803d';
        vStat.style.fontWeight = '800';
    } else if (c.verification_status === 'NO_ID_PRESENTED') {
        vStat.style.color = '#ef4444';
        vStat.style.fontWeight = '800';
    } else {
        vStat.style.color = '#64748b';
        vStat.style.fontWeight = '800';
    }

    const housingRisk = !!c.has_house_risk;
    const noIdRisk = (c.verification_status === "NO_ID_PRESENTED");

    document.getElementById('d-house-risk').value = housingRisk ? "1" : "0";
    document.getElementById('d-no-id-risk').value = noIdRisk ? "1" : "0";

    let warningHTML = "";
    if (housingRisk) {
        warningHTML += "<div style='margin-top:10px; font-weight:800; color:#92400e; border-top:1px solid #fde68a; padding-top:8px;'>Verification required: notes suggest possible eligibility conflict (⚑). Use REQUEST_DOCS or ESCALATE; document evidence.</div>";
    }
    if (noIdRisk) {
        warningHTML += "<div style='margin-top:10px; font-weight:800; color:#b91c1c; border-top:1px solid #fecaca; padding-top:8px;'>No ID presented: do not APPROVE. Use REQUEST_DOCS or REJECT with evidence.</div>";
    }

    if (housingRisk || noIdRisk) {
        vNote.style.backgroundColor = housingRisk ? "#fffbeb" : "#fee2e2";
        vNote.style.borderLeftColor = housingRisk ? "#f59e0b" : "#ef4444";
        vNote.style.color = housingRisk ? "#78350f" : "#7f1d1d";
        vNote.innerHTML = (c.verification_note || "No notes") + warningHTML;
    } else {
        vNote.innerText = c.verification_note || "No notes provided.";
        vNote.style.backgroundColor = "#f1f5f9";
        vNote.style.borderLeftColor = "#cbd5e1";
        vNote.style.color = "#334155";
    }

    // Procedural lock: No ID → APPROVE not allowed (UI)
    if (noIdRisk) _setLocked(document.getElementById('btn-approve'), true);

    // Rules
    document.getElementById('m-rule-res').innerText = c.rule_result;

    // AI Risk
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

    // Reset controls
    _resetActionUI();
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
    const btnMap = {
      'APPROVE': document.getElementById('btn-approve'),
      'REJECT': document.getElementById('btn-reject'),
      'REQUEST_DOCS': document.getElementById('btn-docs'),
      'ESCALATE': document.getElementById('btn-escalate'),
    };
    const btn = btnMap[act];
    if (btn && btn.classList.contains('locked')) {
        alert("This action is not allowed for the current rule result / verification status.");
        return;
    }

    document.getElementById('d-action').value = act;
    document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('selected'));
    if (btn) btn.classList.add('selected');

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

    const housingRisk = document.getElementById('d-house-risk').value === "1";
    const noIdRisk = document.getElementById('d-no-id-risk').value === "1";

    if (!finalAction) { alert("Select Action"); return; }
    if (!reasonCode) { alert("Select Reason"); return; }
    if (!opId) { alert("Enter Operator ID"); return; }

    // Client-side guardrails to match server rules
    if ((finalAction === "REJECT" || finalAction === "ESCALATE") && (!comment || comment.trim().length < 12)) {
        alert("Comment required (min 12 chars) for REJECT/ESCALATE.");
        return;
    }
    if (housingRisk && (finalAction === "APPROVE") && (!flagged || !comment || comment.trim().length < 20)) {
        alert("Conflict indicator present: APPROVE requires Flag + evidence comment (min 20 chars).");
        return;
    }
    if (noIdRisk && finalAction === "APPROVE") {
        alert("No ID presented: cannot APPROVE.");
        return;
    }

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
        btn.disabled = false;
        btn.innerText = "CONFIRM";
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
    page: int = Query(1, ge=1),
):
    since_dt = _parse_since(since)

    base = db.query(Case)
    base = _apply_filters(base, scheme, status, arm, since_dt)

    total_count = base.count()
    limit = 50
    total_pages = (total_count + limit - 1) // limit
    start_index = (page - 1) * limit + 1
    end_index = min(page * limit, total_count)

    # Apply pagination and sorting
    items = (
        base.order_by(
            desc(Case.status == StatusEnum.IN_REVIEW),
            asc(Case.created_at),
        )
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    view: list[dict[str, Any]] = []
    for c in items:
        docs = c.documents or []
        docs_count = len(docs)
        docs_tooltip = "\n".join(docs) if docs else ""

        ver = _verification_value(c)
        rr = c.rule_result.value if c.rule_result else "-"

        has_house_risk = _check_housing_risk(getattr(c, "verification_note", None))

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
                "docs_tooltip": docs_tooltip,
                "verification_status": ver or "—",
                "verification_note": getattr(c, "verification_note", "") or "",
                "risk_disp": risk_disp,
                "risk_band_disp": risk_band_disp,
                "top_reasons_disp": top_reasons_disp,
                "top_reasons_tooltip": top_reasons_tooltip,
                "final_action": (c.final_action.value if c.final_action else ""),
                "reason_code": (c.reason_code.value if c.reason_code else ""),
                "operator_id": getattr(c, "operator_id", None),
                "has_house_risk": has_house_risk,
            }
        )

    # Filter counts reuse the filtered query, but not the paginated one
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

    # Construct query params string for pagination links
    # (preserving current filters)
    params = []
    if scheme: params.append(f"scheme={scheme}")
    if status: params.append(f"status={status}")
    if arm: params.append(f"arm={arm}")
    if since: params.append(f"since={since}")
    filter_qs = "&".join(params)
    if filter_qs:
        filter_qs = "&" + filter_qs

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
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        start_index=start_index,
        end_index=end_index,
        filter_qs=filter_qs,
    )


@router.post("/dashboard/disposition")
def dashboard_disposition(payload: DispositionIn, request: Request, db: Session = Depends(get_db)):
    case_id = (payload.id or "").strip()
    final_action = (payload.final_action or "").strip()
    reason_code = (payload.reason_code or "").strip()
    operator_id = (payload.operator_id or "").strip()
    rule_result_str = (payload.rule_result or "").strip()
    comment = payload.operator_comment or ""

    if not case_id:
        raise HTTPException(400, "Missing case id")
    if not operator_id:
        raise HTTPException(400, "operator_id is required")

    operator_id = operator_id.lower()

    obj = db.query(Case).filter(Case.id == case_id).first()
    if not obj:
        raise HTTPException(404, "Case not found")

    # prevent overwrite for integrity
    if obj.decided_at is not None:
        raise HTTPException(409, "Case already decided")

    if final_action not in _enum_values(FinalActionEnum):
        raise HTTPException(400, "Invalid final_action")
    if reason_code not in _enum_values(ReasonCodeEnum):
        raise HTTPException(400, "Invalid reason_code")

    rr_db = obj.rule_result.value if obj.rule_result else (rule_result_str or "-")
    if rr_db == "-":
        rr_db = "UNKNOWN_NEEDS_DOCS"

    # Enforce action allowed by rule_result
    allowed_actions = ALLOWED_ACTIONS_BY_RULE.get(rr_db, set())
    if allowed_actions and final_action not in allowed_actions:
        raise HTTPException(400, f"Action {final_action} not allowed for rule_result {rr_db}")

    # Enforce reason allowed by action
    allowed_reasons = ALLOWED_REASONS_BY_ACTION.get(final_action, set())
    if allowed_reasons and reason_code not in allowed_reasons:
        raise HTTPException(400, f"Reason {reason_code} not allowed for action {final_action}")

    # Derive procedural/indicator flags
    ver = _verification_value(obj) or "—"
    house_risk = _check_housing_risk(getattr(obj, "verification_note", None))

    # Procedural hard stop only: no ID -> cannot approve
    if ver == "NO_ID_PRESENTED" and final_action == FinalActionEnum.APPROVE.value:
        raise HTTPException(400, "No ID presented → cannot APPROVE")

    # Guardrails to keep conflict cases non-binary and evidence-based
    if final_action in {FinalActionEnum.REJECT.value, FinalActionEnum.ESCALATE.value}:
        if not _require_comment_min(comment, 12):
            raise HTTPException(400, "Comment required (min 12 chars) for REJECT/ESCALATE")

    # If conflict indicator and APPROVE, require flagged + stronger evidence note
    if house_risk and final_action == FinalActionEnum.APPROVE.value:
        if not payload.flagged or not _require_comment_min(comment, 20):
            raise HTTPException(400, "Conflict indicator present: APPROVE requires Flag + evidence comment (min 20 chars)")

    # timestamps
    if payload.opened_at:
        try:
            obj.opened_at = datetime.fromisoformat(payload.opened_at.replace("Z", "+00:00"))
        except ValueError:
            obj.opened_at = _utcnow()
    elif obj.opened_at is None:
        obj.opened_at = _utcnow()

    obj.final_action = FinalActionEnum(final_action)
    obj.reason_code = ReasonCodeEnum(reason_code)
    obj.operator_id = operator_id
    obj.decided_at = _utcnow()
    obj.sop_version = obj.sop_version or "SOP_v1"

    if hasattr(obj, "operator_comment"):
        obj.operator_comment = payload.operator_comment
    if hasattr(obj, "flagged"):
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

    ua = request.headers.get("user-agent")

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
                "operator_comment": payload.operator_comment,
                "flagged": payload.flagged,
                "decision_support_shown": bool(getattr(obj, "decision_support_shown", False)),
                "risk_score": obj.risk_score,
                "override_flag": obj.override_flag,
                "sop_version": obj.sop_version,
                "latency_seconds": (obj.decided_at - obj.opened_at).total_seconds() if obj.opened_at else None,
                "verification_status": ver,
                "house_conflict_indicator": house_risk,
                "allowed_actions_for_rule": sorted(list(ALLOWED_ACTIONS_BY_RULE.get(rr_db, set()))),
                "allowed_reasons_for_action": sorted(list(ALLOWED_REASONS_BY_ACTION.get(final_action, set()))),
                "user_agent": ua,
            },
            ensure_ascii=False,
        ),
    )
    db.add(evt)
    db.commit()

    return JSONResponse({"ok": True})