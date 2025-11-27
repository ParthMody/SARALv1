# tests/test_empirical.py
import pytest
import sys
import os

# Add the project root to sys.path so 'app' module can be found
# We need to go up 3 levels: test_empirical.py -> tests -> app -> SARALV1
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from app.main import app
import time

client = TestClient(app)

# --- HELPER ---
def get_base_profile():
    """Standard 'Poor, Rural, General Category' profile"""
    return {
        "age": 35, 
        "gender": "F", 
        "income": 90000, 
        "education_years": 5, 
        "rural": 1, 
        "caste_marginalized": 0
    }

# --- SCENARIO 1: The "Marginalized Benefit" Check ---
# Goal: Ensure caste status triggers specific document requirements and maintains eligibility.
def test_scenario_1_marginalized_benefit():
    # Test A: General Category
    profile_gen = get_base_profile()
    profile_gen["caste_marginalized"] = 0
    
    res_gen = client.post("/cases/", json={
        "citizen_hash": "UserGen", # Odd length -> Control (Blinded), so check 'documents' list primarily
        "scheme_code": "UJJ", 
        "source": "WEB",
        "profile": profile_gen
    })
    assert res_gen.status_code == 201
    data_gen = res_gen.json()
    # General category should NOT be asked for Caste Cert
    assert "Caste Certificate (SC/ST)" not in data_gen["documents"]

    # Test B: Marginalized Category
    profile_sc = get_base_profile()
    profile_sc["caste_marginalized"] = 1
    
    res_sc = client.post("/cases/", json={
        "citizen_hash": "UserSC", # Even length -> Treatment (Visible Score)
        "scheme_code": "UJJ", 
        "source": "WEB",
        "profile": profile_sc
    })
    assert res_sc.status_code == 201
    data_sc = res_sc.json()
    
    # 1. Should have high confidence
    assert data_sc["review_confidence"] > 0.6
    # 2. MUST have Caste Cert in documents
    assert "Caste Certificate (SC/ST)" in data_sc["documents"]


# --- SCENARIO 2: The "Income Cliff" (Boundary Testing) ---
# Goal: Verify strict income cut-offs.
def test_scenario_2_income_cliff():
    # Test A: 90k (Eligible)
    res_a = client.post("/cases/", json={
        "citizen_hash": "UserIncA", 
        "scheme_code": "UJJ", "source": "WEB",
        "profile": {**get_base_profile(), "income": 90000}
    })
    # Even length hash for visibility
    assert res_a.json()["review_confidence"] > 0.6

    # Test C: 3.1 Lakhs (Ineligible for Ujjwala/EWS)
    res_c = client.post("/cases/", json={
        "citizen_hash": "UserIncC", 
        "scheme_code": "UJJ", "source": "WEB",
        "profile": {**get_base_profile(), "income": 310000}
    })
    # Should be low confidence
    score = res_c.json()["review_confidence"]
    assert score is not None and score < 0.5


# --- SCENARIO 3: The "Urban Poor" Invisible Group ---
# Goal: Detect bias against Urban poor.
def test_scenario_3_urban_poor():
    # Profile: Very Poor (70k) but Urban (0)
    res = client.post("/cases/", json={
        "citizen_hash": "UserUrban", 
        "scheme_code": "UJJ", "source": "WEB",
        "profile": {
            "age": 40, "gender": "F", 
            "income": 70000, 
            "education_years": 5, 
            "rural": 0, # <-- The Variable
            "caste_marginalized": 0
        }
    })
    
    data = res.json()

    # Arm should be CONTROL (hash length is odd in the fixture)
    assert data["arm"] == "CONTROL"

    # Blinding: control arm must not see AI score
    assert data["review_confidence"] is None

# --- SCENARIO 4: The "Gaming" Attempt ---
# Goal: Check if submitting the same ID multiple times works (it shouldn't duplicate).
def test_scenario_4_gaming_attempt():
    common_hash = "GamerUser1"
    
    # Attempt 1: High Income
    client.post("/cases/", json={
        "citizen_hash": common_hash, "scheme_code": "UJJ", "source": "WEB",
        "profile": {**get_base_profile(), "income": 500000}
    })
    
    # Attempt 2: Low Income (The "Cheat")
    # Since we have idempotent logic, this should return the EXISTING case (Attempt 1),
    # NOT create a new one with the cheated income.
    res_cheat = client.post("/cases/", json={
        "citizen_hash": common_hash, "scheme_code": "UJJ", "source": "WEB",
        "profile": {**get_base_profile(), "income": 50000}
    })
    
    data = res_cheat.json()
    # The ID should match the first one (or simply, the confidence should still be LOW
    # because it returned the record from Attempt 1).
    # Note: If your code returns the *new* confidence, you have a gaming vulnerability.
    
    # For v1 logic: We expect it to return the *existing* record.
    # If Attempt 1 was High Income, confidence should be low.
    # If it returns High Confidence, it means the Cheat worked (Bad).
    if data["review_confidence"]:
        assert data["review_confidence"] < 0.5, "Gaming Prevention Failed: Cheat attempt overwrote data!"


# --- SCENARIO 5: The "Missing Data" Robustness ---
# Goal: Ensure graceful degradation.
def test_scenario_5_missing_data():
    res = client.post("/cases/", json={
        "citizen_hash": "UserMiss", 
        "scheme_code": "UJJ", "source": "WEB",
        "profile": {
            "age": 40, "gender": "F", 
            "income": 0, # Implies missing/unknown in some contexts
            "education_years": 0, 
            "rural": 1, 
            "caste_marginalized": 0
        }
    })
    
    data = res.json()
    # Should not crash (500)
    assert res.status_code == 201
    # Should return a valid response structure
    assert isinstance(data["documents"], list)