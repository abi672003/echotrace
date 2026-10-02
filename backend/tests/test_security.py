import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.security import require_admin


def _make_client(admin_token: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = Settings(ADMIN_TOKEN=admin_token)
    monkeypatch.setattr("app.security.get_settings", lambda: settings)

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_admin)])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_no_admin_token_configured_allows_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client("", monkeypatch)
    response = client.get("/protected")
    assert response.status_code == 200


def test_correct_token_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client("secret123", monkeypatch)
    response = client.get("/protected", headers={"X-Admin-Token": "secret123"})
    assert response.status_code == 200


def test_missing_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client("secret123", monkeypatch)
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "unauthorized",
        "message": "Missing or invalid X-Admin-Token.",
    }


def test_wrong_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client("secret123", monkeypatch)
    response = client.get("/protected", headers={"X-Admin-Token": "wrong"})
    assert response.status_code == 401
