from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

import auth
import triage_api
from config import VERSION
from triage_model import ModelUnavailable

client = TestClient(triage_api.app)
GOOD = {"patient_message": "I have chest pain and feel dizzy", "county": "Kisumu"}


def login(username="mercy", password="logistics2026"):
    r = client.post("/token", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_is_open_and_reports_version():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"service": "triage-api", "version": VERSION, "status": "ok",
                        "model_backend": "stub"}


def test_token_then_triage_200():
    r = client.post("/triage", json=GOOD, headers=login())
    assert r.status_code == 200
    body = r.json()
    assert body["urgency"] == "high" and body["handled_for"] == "mercy"
    assert r.headers["X-Request-ID"] == body["request_id"]


def test_token_payload_carries_role():
    token = login()["Authorization"].split()[1]
    payload = jwt.decode(token, auth.JWT_SECRET, algorithms=["HS256"], issuer=auth.ISSUER)
    assert payload["sub"] == "mercy" and payload["role"] == "coordinator"


@pytest.mark.parametrize("headers,detail", [
    ({}, "Not authenticated"),
    ({"Authorization": "Bearer not.a.token"}, "Invalid token"),
    ({"Authorization": "Basic bWVyY3k6eA=="}, "Not authenticated"),
])
def test_triage_401_without_valid_token(headers, detail):
    r = client.post("/triage", json=GOOD, headers=headers)
    assert r.status_code == 401
    assert detail in r.json()["detail"]
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_triage_401_expired_token():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode({"sub": "mercy", "role": "coordinator", "iss": auth.ISSUER,
                        "iat": past, "exp": past + timedelta(minutes=1)}, auth.JWT_SECRET)
    r = client.post("/triage", json=GOOD, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_triage_401_token_signed_with_wrong_secret():
    forged = jwt.encode({"sub": "mercy", "role": "coordinator", "iss": auth.ISSUER,
                         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "attacker-key" * 4)
    r = client.post("/triage", json=GOOD, headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_wrong_password_401_and_unknown_user_401():
    assert client.post("/token", json={"username": "mercy", "password": "wrongpass1"}).status_code == 401
    assert client.post("/token", json={"username": "nobody", "password": "wrongpass1"}).status_code == 401


def test_viewer_gets_403_not_401():
    r = client.post("/triage", json=GOOD, headers=login("guest", "viewonly2026"))
    assert r.status_code == 403
    assert "viewer" in r.json()["detail"]


@pytest.mark.parametrize("body", [
    {"patient_message": "hi", "county": "Kisumu"},                         # too short
    {"patient_message": "I feel unwell today"},                            # missing county
    {"patient_message": "I feel unwell today", "county": "K1$umu"},        # bad characters
    {"patient_message": "x" * 1001, "county": "Kisumu"},                   # too long
    {**GOOD, "priority": "vip"},                                           # unknown field
])
def test_invalid_body_422(body):
    assert client.post("/triage", json=body, headers=login()).status_code == 422


def test_non_json_body_422():
    r = client.post("/triage", content="not json at all",
                    headers={**login(), "Content-Type": "application/json"})
    assert r.status_code == 422


def test_rate_limit_429_on_sixth_call():
    headers = login()
    codes = [client.post("/triage", json=GOOD, headers=headers).status_code for _ in range(7)]
    assert codes == [200] * 5 + [429] * 2


def test_login_is_rate_limited():
    codes = [client.post("/token", json={"username": "mercy", "password": "wrongpass1"}).status_code
             for _ in range(6)]
    assert codes == [401] * 5 + [429]


def test_model_failure_is_honest_503(monkeypatch):
    def broken(*_):
        raise ModelUnavailable("APITimeoutError")
    monkeypatch.setattr(triage_api, "triage_model", broken)
    r = client.post("/triage", json=GOOD, headers=login())
    assert r.status_code == 503
    assert r.json()["detail"] == "The AI model is unavailable. Try again shortly."
