# app/tests/test_export_metrics.py
import pytest
import sys
import os
from fastapi.testclient import TestClient

# Fix path to import app correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app

client = TestClient(app)

def test_export_and_metrics():
    # 1. Seed a case so we have data
    r = client.post("/cases/", json={
        "citizen_hash": "hash_exp_01",
        "scheme_code": "UJJ",
        "source": "WEB", # Valid enum
        "locale": "hi",
        "profile": {
            "age": 30, "gender": "F", "income": 50000, 
            "education_years": 5, "rural": 1, "caste_marginalized": 1
        }
    })
    assert r.status_code == 201

    # 2. Test Metrics (All Time)
    m = client.get("/metrics/")
    assert m.status_code == 200
    data = m.json()
    assert "by_status" in data
    assert "by_scheme" in data
    # Check that UJJ count exists
    assert "UJJ" in data["by_scheme"]

    # 3. Test Metrics (Since)
    m2 = client.get("/metrics/?since=2025-01-01")
    assert m2.status_code == 200

    # 4. Test Export CSV
    e = client.get("/cases/export?flags=false&min_conf=0.0")
    # Note: your route is /cases/export (no .csv extension in route definition in updated cases.py)
    # If it fails with 404, check route path. Based on previous turn it was /export
    if e.status_code == 404:
        e = client.get("/cases/export.csv?flags=false&min_conf=0.0")
        
    assert e.status_code == 200
    # Check simple CSV content presence
    assert "id" in e.text
    assert "scheme_code" in e.text
    assert "status" in e.text