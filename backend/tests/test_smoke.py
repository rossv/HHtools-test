from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code in (200, 404)

def test_percent_capture():
    payload = {"inflow":[1,2,3], "captured":[1,2,2], "timestep_minutes":15}
    r = client.post("/api/percent-capture/compute", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "percent_capture" in data

def test_design_storm():
    payload = {"duration_minutes":60,"dt_minutes":5,"total_depth_inches":1.2}
    r = client.post("/api/design-storm/generate", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert len(data["time_minutes"]) > 0
