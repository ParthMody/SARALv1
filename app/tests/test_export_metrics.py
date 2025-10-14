from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_export_and_metrics():
    # Seed one
    r = client.post("/cases/", json={
        "citizen_hash":"hash_exp","scheme_code":"UJJ","source":"SMS","locale":"hi"
    })
    assert r.status_code == 201

    # Metrics all-time
    m = client.get("/metrics/")
    assert m.status_code == 200
    assert "by_status" in m.json()

    # Metrics since today
    m2 = client.get("/metrics/?since=2025-10-01")
    assert m2.status_code == 200

    # Export CSV
    e = client.get("/cases/export.csv?flags=false&min_conf=0.0")
    assert e.status_code == 200
    assert e.headers["content-type"].startswith("text/csv")
    assert "id,scheme_code,status" in e.text.splitlines()[0]
