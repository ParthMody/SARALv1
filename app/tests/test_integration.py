# app/tests/test_integration.py
import pytest
import sys
import os
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.main import app

client = TestClient(app)

def test_scheme_logic_ujjwala():
    """Rural woman applying for Ujjwala."""
    response = client.post("/cases/", json={
        "citizen_hash": "TestUser_UJJ_01", # Odd -> CONTROL
        "scheme_code": "UJJ",
        "source": "WEB",
        "session_id": "test_sess_1",
        "meta_duration_seconds": 30,
        "profile": {
            "age": 30, "gender": "F", "income": 50000, 
            "education_years": 5, "rural": 1, "caste_marginalized": 1
        }
    })
    
    assert response.status_code == 201
    data = response.json()
    
    # 1. Documents (Fixed String Match)
    assert "Gram Panchayat Certificate" in data["documents"]
    assert "Caste Certificate (SC/ST)" in data["documents"]
    
    # 2. Blinding (Control)
    assert data["review_confidence"] is None

def test_alternatives_logic():
    """Male applying for Ujjwala."""
    response = client.post("/cases/", json={
        "citizen_hash": "TestUser_Male_02", # Even -> TREATMENT
        "scheme_code": "UJJ",
        "source": "WEB",
        "profile": {
            "age": 35, "gender": "M", "income": 150000, 
            "education_years": 8, "rural": 1, "caste_marginalized": 0
        }
    })
    
    data = response.json()
    # Should flag
    assert data["audit_flag"] is True
    # Should suggest PMAY
    assert "PMAY" in data["alternatives"]

def test_near_miss_logic():
    """PMAY applicant just above income limit."""
    response = client.post("/cases/", json={
        "citizen_hash": "TestUser_NearMiss_02", 
        "scheme_code": "PMAY",
        "source": "WEB",
        "profile": {
            "age": 40, "gender": "F", 
            "income": 310000, # Limit 3L
            "education_years": 10, "rural": 0, "caste_marginalized": 0
        }
    })
    
    data = response.json()
    assert "Near Miss" in data["flag_reason"]

def test_invalid_scheme():
    """Ensures 400 Bad Request."""
    response = client.post("/cases/", json={
        "citizen_hash": "UserX", 
        "scheme_code": "INVALID_SCHEME",
        "source": "WEB",
        "profile": {"age": 20, "gender": "M", "income": 0, "education_years": 0, "rural": 0, "caste_marginalized": 0}
    })
    assert response.status_code == 400