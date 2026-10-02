from fastapi.testclient import TestClient

from app.main import app


def test_unknown_route_returns_error_envelope() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "404", "message": "Not Found"}}
