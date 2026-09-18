"""End-to-end API tests: real auth, real DB, real aggregation/detector-guard
logic, with only the network-touching pieces (GDELT search, article fetch)
mocked — this sandbox can't reach the live web (see retrieval/gdelt.py)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-only-32b")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from fastapi.testclient import TestClient

from echotrace.db import reset_engine_for_tests


@pytest.fixture
def client(tmp_path, monkeypatch):
    reset_engine_for_tests(f"sqlite:///{(tmp_path / 'api_test.sqlite').as_posix()}")

    async def fake_find_live_near_duplicates(target_text, k=5, timespan="1w", exclude_url=None):
        return [
            {"id": "https://example.com/dup1", "text": "a near-duplicate story", "similarity": 0.92,
             "title": "Dup 1", "domain": "example.com"},
            {"id": "https://example.com/dup2", "text": "a loosely related story", "similarity": 0.3,
             "title": "Dup 2", "domain": "example.com"},
        ]

    monkeypatch.setattr(
        "echotrace.api.main.find_live_near_duplicates", fake_find_live_near_duplicates
    )

    from echotrace.api.main import app

    with TestClient(app) as c:
        yield c


def _register_and_login(client, username="alice", password="correcthorsebattery"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_unauthenticated_request_rejected(client):
    resp = client.post("/api/investigate", json={"text": "some article text"})
    assert resp.status_code == 401


def test_register_then_investigate_by_text(client):
    token = _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/investigate", json={"text": "some article text about a city council vote"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "model_available" in body
    assert len(body["evidence"]) == 2
    # evidence carries through title/domain metadata from live_search
    assert body["evidence"][0]["title"] in ("Dup 1", "Dup 2")


def test_investigate_requires_exactly_one_of_text_or_url(client):
    token = _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/investigate", json={}, headers=headers)
    assert resp.status_code == 422

    resp = client.post(
        "/api/investigate",
        json={"text": "abc", "url": "https://example.com/x"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_investigation_appears_in_history(client):
    token = _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/investigate", json={"text": "story about a budget vote"}, headers=headers)
    resp = client.get("/api/investigations", headers=headers)
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 1
    assert history[0]["target_text_preview"].startswith("story about a budget vote")


def test_history_is_scoped_per_user(client):
    token_a = _register_and_login(client, "alice2", "correcthorsebattery")
    token_b = _register_and_login(client, "bob2", "correcthorsebattery")

    client.post(
        "/api/investigate", json={"text": "alice's article"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    resp_b = client.get("/api/investigations", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.json() == []


def test_login_rate_limited_after_repeated_failures(client):
    _register_and_login(client, "carol2", "correcthorsebattery")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "carol2", "password": "wrongpassword"})
    resp = client.post("/api/auth/login", json={"username": "carol2", "password": "wrongpassword"})
    assert resp.status_code == 429


def test_detector_sandbox_endpoints_require_auth(client):
    assert client.get("/api/articles/sample").status_code == 401
    assert client.get("/api/mdaigt/sample").status_code == 401
