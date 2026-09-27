import pytest
from fastapi.testclient import TestClient

import agent as agent_module
import agent_api
from config import VERSION

client = TestClient(agent_api.app)
ASK = {"question": "Which clinics need an amoxicillin reorder?"}


def login(username="mercy", password="logistics2026"):
    r = client.post("/token", json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def fake_agent(monkeypatch):
    calls = []

    async def fake_run(question, trace_id, role="coordinator", **_):
        calls.append({"question": question, "trace_id": trace_id, "role": role})
        return agent_module.AgentRun(answer="Vihiga Health Post and Homa Bay Lakeside Clinic.",
                                     status="answered", tools_used=["check_stock"],
                                     model_calls=2, tokens_in=900, tokens_out=60)
    monkeypatch.setattr(agent_module, "run_agent", fake_run)
    return calls


def test_health_open():
    assert client.get("/health").json() == {"service": "agent-api", "version": VERSION, "status": "ok"}


def test_ask_requires_token(fake_agent):
    assert client.post("/ask-logistics", json=ASK).status_code == 401
    assert fake_agent == []                      # the agent (and the bill) never ran


def test_ask_rejects_bad_input_before_the_agent(fake_agent):
    headers = login()
    assert client.post("/ask-logistics", json={"question": "hi"}, headers=headers).status_code == 422
    assert client.post("/ask-logistics", json={"question": "x" * 501}, headers=headers).status_code == 422
    assert fake_agent == []


def test_ask_passes_role_and_trace_id(fake_agent):
    r = client.post("/ask-logistics", json=ASK, headers=login("guest", "viewonly2026"))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "viewer" and body["asked_by"] == "guest"
    assert fake_agent[0]["role"] == "viewer"
    assert fake_agent[0]["trace_id"] == body["trace_id"] == r.headers["X-Request-ID"]


def test_agent_failure_is_503_with_trace_id(monkeypatch):
    async def broken(*_, **__):
        raise RuntimeError("openai down")
    monkeypatch.setattr(agent_module, "run_agent", broken)
    r = client.post("/ask-logistics", json=ASK, headers=login())
    assert r.status_code == 503
    assert r.headers["X-Request-ID"] in r.json()["detail"]


def test_viewer_tools_are_restricted():
    assert agent_module.ROLE_TOOLS["viewer"] == {"check_stock"}


def test_reorder_propose_then_confirm_rails():
    guest, mercy = login("guest", "viewonly2026"), login()
    r = client.post("/reorders/propose", json={"clinic_id": "C04", "item": "amoxicillin", "units": 50},
                    headers=guest)
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    pid = r.json()["id"]

    assert client.post(f"/reorders/{pid}/confirm").status_code == 401              # no token
    assert client.post(f"/reorders/{pid}/confirm", headers=guest).status_code == 403  # viewer
    assert client.post("/reorders/nope/confirm", headers=mercy).status_code == 404

    first = client.post(f"/reorders/{pid}/confirm", headers=mercy)
    again = client.post(f"/reorders/{pid}/confirm", headers=mercy)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()                                              # idempotent
    assert first.json()["confirmed_by"] == "mercy"


@pytest.mark.parametrize("body", [
    {"clinic_id": "C99", "item": "amoxicillin", "units": 5},
    {"clinic_id": "C01", "item": "bandages", "units": 5},
    {"clinic_id": "C01", "item": "amoxicillin", "units": 0},
    {"clinic_id": "C01", "item": "amoxicillin", "units": 501},
])
def test_reorder_validation_422(body):
    assert client.post("/reorders/propose", json=body, headers=login()).status_code == 422
