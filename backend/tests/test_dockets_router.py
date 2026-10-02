import json
from pathlib import Path

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, SQLModel, create_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_session
from app.main import _http_exception_handler
from app.routers import dockets, documents
from app.services.sources.regulations_gov import REGULATIONS_BASE_URL

SUBSTANTIVE_TEXT = (
    "I am writing to express my strong opposition to this proposed rule because it "
    "would harm small businesses across the region and fails to consider long-term "
    "economic impacts on our community."
)


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(dockets, "engine", engine)
    monkeypatch.setattr(dockets, "SAMPLES_DIR", tmp_path)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.include_router(dockets.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.dependency_overrides[get_session] = override_get_session
    return app


def _write_sample(tmp_path: Path, name: str, docket_id: str) -> None:
    payload = {
        "docket_id": docket_id,
        "fetched_at": "2024-05-01T00:00:00+00:00",
        "remote_comment_count": 2,
        "comments": [
            {
                "id": "s1",
                "type": "comments",
                "attributes": {
                    "comment": SUBSTANTIVE_TEXT + " First.",
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "organization": None,
                    "postedDate": "2024-05-01T12:00:00Z",
                    "title": None,
                },
            },
            {
                "id": "s2",
                "type": "comments",
                "attributes": {
                    "comment": "See attached.",
                    "firstName": None,
                    "lastName": None,
                    "organization": None,
                    "postedDate": "2024-05-02T12:00:00Z",
                    "title": None,
                },
            },
        ],
    }
    (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_list_samples_and_load_sample_matches_file_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sample(tmp_path, "DEMO-DOCKET", "DEMO-DOCKET-0001")
    app = _make_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        samples_response = client.get("/api/v1/samples")
        assert samples_response.status_code == 200
        assert samples_response.json() == [
            {"name": "DEMO-DOCKET", "docket_id": "DEMO-DOCKET-0001", "count": 2}
        ]

        create_response = client.post("/api/v1/dockets/samples/DEMO-DOCKET")
        assert create_response.status_code == 201
        docket_out = create_response.json()
        assert docket_out["id"] == "DEMO-DOCKET-0001"

        get_response = client.get("/api/v1/dockets/DEMO-DOCKET-0001")
        assert get_response.status_code == 200
        body = get_response.json()
        # counts must match the sample file: 2 comments, 1 stored + 1 skipped as attachment-only
        assert body["ingested_count"] == 1
        assert body["skipped_count"] == 1
        assert body["remote_comment_count"] == 2
        assert body["ingest_status"] == "done"

        docs_response = client.get("/api/v1/dockets/DEMO-DOCKET-0001/documents")
        assert docs_response.status_code == 200
        docs_body = docs_response.json()
        assert docs_body["total"] == 1
        assert docs_body["items"][0]["external_id"] == "s1"


def test_create_docket_from_sample_404_for_unknown_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/dockets/samples/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "sample_not_found"


def test_get_unknown_docket_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/dockets/NOPE")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "docket_not_found"


def test_get_unknown_document_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/documents/999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "document_not_found"


def test_compare_404s_when_a_document_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/documents/compare", params={"a": 1, "b": 2})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "document_not_found"


def test_create_docket_rejects_invalid_id_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/dockets", json={"docket_id": "lowercase-not-allowed"})
        assert response.status_code == 422


@respx.mock
def test_create_docket_ingests_via_regulations_gov(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx.get(f"{REGULATIONS_BASE_URL}/comments").mock(
        return_value=Response(
            200,
            json={
                "data": [{"id": "c1", "type": "comments", "attributes": {}}],
                "meta": {"hasNextPage": False, "totalElements": 1},
            },
        )
    )
    respx.get(f"{REGULATIONS_BASE_URL}/comments/c1").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "id": "c1",
                    "type": "comments",
                    "attributes": {
                        "comment": SUBSTANTIVE_TEXT,
                        "firstName": "Jane",
                        "lastName": "Doe",
                        "organization": None,
                        "postedDate": "2024-05-01T12:00:00Z",
                        "title": None,
                    },
                }
            },
        )
    )

    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/dockets", json={"docket_id": "EPA-HQ-OAR-2021-0317", "max_comments": 10}
        )
        assert response.status_code == 202

        docket_response = client.get("/api/v1/dockets/EPA-HQ-OAR-2021-0317")
        assert docket_response.json()["ingested_count"] == 1
