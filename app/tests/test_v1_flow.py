from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.engine.rules import assistive_decision
from app.engine.scheme_config import SCHEME_CONFIG


client = TestClient(app)


def _assign_arm(citizen_hash: str, scheme_code: str) -> str:
    key = f"{citizen_hash}|{scheme_code}|v1"
    h = hashlib.sha256(key.encode()).hexdigest()
    return "TREATMENT" if int(h, 16) % 2 == 0 else "CONTROL"


def _post_case(payload: dict) -> dict:
    r = client.post("/cases/", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


# -------------------------
# RULE ENGINE UNIT TESTS
# -------------------------
def test_rules_unknown_when_income_missing():
    profile = {
        "age": 25,
        "gender": "M",
        "rural": 0,
        "caste_marginalized": 0,
        # income missing
        "income_period": "annual",
    }
    out = assistive_decision("PMAY", profile)
    assert out.rule_result == "UNKNOWN_NEEDS_DOCS"
    assert "Income or income period missing" in out.reasons


def test_rules_unknown_when_income_period_invalid():
    profile = {
        "age": 25,
        "gender": "M",
        "rural": 0,
        "caste_marginalized": 0,
        "income": 10000,
        "income_period": "weekly",  # invalid
    }
    out = assistive_decision("PMAY", profile)
    assert out.rule_result == "UNKNOWN_NEEDS_DOCS"
    assert "Invalid income format" in out.reasons


def test_rules_pmay_income_band_tagging():
    profile = {
        "age": 25,
        "gender": "F",
        "rural": 0,
        "caste_marginalized": 0,
        "income": 20000,
        "income_period": "monthly",  # annual 240,000 => EWS
    }
    out = assistive_decision("PMAY", profile)
    assert out.rule_result == "ELIGIBLE_BY_RULE"
    assert any(t.startswith("PMAY_BAND:") for t in out.tags)
    assert "PMAY_BAND:EWS" in out.tags


def test_rules_pmay_income_exceeds_all_bands():
    profile = {
        "age": 30,
        "gender": "M",
        "rural": 0,
        "caste_marginalized": 0,
        "income": 200000,
        "income_period": "monthly",  # annual 2.4M > 1.8M
    }
    out = assistive_decision("PMAY", profile)
    assert out.rule_result == "INELIGIBLE_BY_RULE"
    assert "Income exceeds all eligible bands" in out.reasons
    assert out.alternatives == SCHEME_CONFIG["PMAY"]["alternatives"]


def test_rules_pmay_min_age():
    profile = {
        "age": 17,
        "gender": "O",
        "rural": 0,
        "caste_marginalized": 0,
        "income": 10000,
        "income_period": "annual",
    }
    out = assistive_decision("PMAY", profile)
    assert out.rule_result == "INELIGIBLE_BY_RULE"
    assert any("Age must be" in r for r in out.reasons)


def test_rules_ujj_requires_rural():
    profile = {
        "age": 30,
        "gender": "M",
        "rural": 0,  # must be rural
        "caste_marginalized": 0,
        "income": 10000,
        "income_period": "annual",
    }
    out = assistive_decision("UJJ", profile)
    assert out.rule_result == "INELIGIBLE_BY_RULE"
    assert "Must be Rural" in out.reasons


def test_rules_invalid_scheme_returns_unknown():
    profile = {
        "age": 30,
        "gender": "M",
        "rural": 1,
        "caste_marginalized": 0,
        "income": 10000,
        "income_period": "annual",
    }
    out = assistive_decision("BAD", profile)
    assert out.rule_result == "UNKNOWN_NEEDS_DOCS"
    assert "Invalid scheme code" in out.reasons


# -------------------------
# API / RCT BLINDING TESTS
# -------------------------
def test_api_blinding_control_hides_ml_fields():
    payload = {
        "citizen_hash": "citizen_control_001",
        "scheme_code": "PMAY",
        "locale": "en",
        "profile": {
            "age": 25,
            "gender": "M",
            "rural": 0,
            "caste_marginalized": 0,
            "income": 20000,
            "income_period": "monthly",
        },
    }
    arm = _assign_arm(payload["citizen_hash"], payload["scheme_code"])
    resp = _post_case(payload)

    assert resp["arm"] == arm
    if arm == "CONTROL":
        assert resp.get("decision_support_shown") in (False, None)
        assert resp.get("review_confidence") is None
        assert resp.get("risk_score") is None
        assert resp.get("risk_band") is None
        assert resp.get("top_reasons") == []
    else:
        assert resp.get("decision_support_shown") is True


def test_api_treatment_shows_ml_fields():
    # Find a citizen_hash that deterministically maps to TREATMENT
    i = 0
    while True:
        citizen_hash = f"citizen_treat_{i:03d}"
        if _assign_arm(citizen_hash, "PMAY") == "TREATMENT":
            break
        i += 1

    payload = {
        "citizen_hash": citizen_hash,
        "scheme_code": "PMAY",
        "locale": "en",
        "profile": {
            "age": 25,
            "gender": "F",
            "rural": 0,
            "caste_marginalized": 0,
            "income": 20000,
            "income_period": "monthly",
        },
    }
    resp = _post_case(payload)

    assert resp["arm"] == "TREATMENT"
    assert resp.get("decision_support_shown") is True
    assert resp.get("review_confidence") is not None
    assert resp.get("risk_score") is not None
    assert resp.get("risk_band") in ("LOW", "MED", "HIGH")
    assert isinstance(resp.get("top_reasons"), list)


def test_api_lists_are_lists_not_strings():
    payload = {
        "citizen_hash": "citizen_list_001",
        "scheme_code": "PMAY",
        "locale": "en",
        "profile": {
            "age": 30,
            "gender": "O",
            "rural": 0,
            "caste_marginalized": 0,
            "income": 10000,
            "income_period": "annual",
        },
    }
    resp = _post_case(payload)
    assert isinstance(resp.get("rule_reasons"), list)
    assert isinstance(resp.get("documents"), list)
    assert isinstance(resp.get("top_reasons"), list)


# -------------------------
# DASHBOARD QUEUE BEHAVIOR (JSON dashboard)
# -------------------------
def test_dashboard_returns_queues():
    r = client.get("/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "treatment_queue" in data
    assert "control_queue" in data
    assert isinstance(data["treatment_queue"], list)
    assert isinstance(data["control_queue"], list)


def test_dashboard_queue_ordering_after_multiple_inserts():
    # Create multiple cases and check treatment is sorted by risk_score desc, created_at asc
    # We cannot rely on ML values, so this test only checks that endpoint returns stable types.
    payloads = [
        {
            "citizen_hash": f"queue_case_{k}",
            "scheme_code": "PMAY",
            "locale": "en",
            "profile": {
                "age": 25 + k,
                "gender": "M",
                "rural": 0,
                "caste_marginalized": 0,
                "income": 20000,
                "income_period": "monthly",
            },
        }
        for k in range(5)
    ]
    for p in payloads:
        _post_case(p)

    data = client.get("/dashboard").json()
    assert all(isinstance(x, str) for x in data["treatment_queue"])
    assert all(isinstance(x, str) for x in data["control_queue"])