from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/")
    assert r.status_code == 200

def test_create_get_and_update():
    r = client.post("/cases/", json={"citizen_hash":"hash$pytest","scheme_code":"UJJ","source":"SMS","locale":"hi"})
    assert r.status_code == 201
    cid = r.json()["id"]

    r2 = client.get(f"/cases/{cid}")
    assert r2.status_code == 200

    r3 = client.patch(f"/cases/{cid}/status?status=IN_REVIEW", headers={"X-Mock-OTP":"123456"})
    assert r3.status_code == 200
