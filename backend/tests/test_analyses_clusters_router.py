import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_session
from app.main import _http_exception_handler
from app.models import Analysis, Docket, Document
from app.routers import analyses, clusters
from app.services.embeddings import FakeEmbedder
from app.services.llm import FakeLLM

GROUP_TEXT = (
    "I am writing to express my strong opposition to this proposed rule because it "
    "would harm small businesses across the region and fails to consider long-term "
    "economic impacts on our community members and families."
)

AI_SCORE_RESPONSE = json.dumps({"scores": [{"id": "hashA", "score": 0.3, "reason": "formal"}]})


def _verdict_response(doc_ids: list[int]) -> str:
    return json.dumps(
        {
            "thought": "Near-identical text.",
            "action": "submit_verdict",
            "args": {
                "type": "form_letter",
                "confidence": "high",
                "rationale": "Identical wording across members.",
                "cited_document_ids": doc_ids,
                "recommend_review": True,
            },
        }
    )


SUMMARY_RESPONSE = json.dumps({"summary": "One form-letter family was found."})


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(analyses, "engine", engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.include_router(analyses.router, prefix="/api/v1")
    app.include_router(clusters.router, prefix="/api/v1")
    app.dependency_overrides[get_session] = override_get_session
    return app, engine


def _seed_docket(engine, docket_id: str = "D1") -> list[int]:
    with Session(engine) as session:
        session.add(Docket(id=docket_id, source="sample"))
        base = datetime(2024, 5, 1, tzinfo=timezone.utc)
        ids = []
        for i in range(4):
            doc = Document(
                docket_id=docket_id,
                external_id=f"a-{i}",
                submitter_label=f"Person {i}",
                submitter_hash=f"hash_{i}",
                text=GROUP_TEXT,
                text_hash="hashA",
                word_count=30,
                posted_at=base + timedelta(hours=i),
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)
            ids.append(doc.id)
        return ids


def test_create_analysis_runs_and_get_analysis_returns_full_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, engine = _make_app(tmp_path, monkeypatch)
    doc_ids = _seed_docket(engine)

    monkeypatch.setattr(analyses, "_make_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(
        analyses,
        "_make_llm",
        lambda: FakeLLM([AI_SCORE_RESPONSE, _verdict_response(doc_ids[:2]), SUMMARY_RESPONSE]),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/analyses", json={"mode": "docket", "docket_id": "D1"}
        )
        assert create_response.status_code == 202
        analysis_id = create_response.json()["analysis_id"]

        get_response = client.get(f"/api/v1/analyses/{analysis_id}")
        assert get_response.status_code == 200
        body = get_response.json()

        assert body["status"] == "done"
        assert body["summary"] == "One form-letter family was found."
        assert {s["name"] for s in body["steps"]} == {
            "normalize", "embed", "cluster", "measure", "ai_score", "aggregate", "agent",
        }
        assert all(s["status"] == "done" for s in body["steps"])
        assert len(body["clusters"]) == 1
        cluster_summary = body["clusters"][0]
        assert cluster_summary["size"] == 4
        assert cluster_summary["verdict_type"] == "form_letter"
        assert body["usage"]["llm_calls"] == 3
        assert body["usage"]["embed_calls"] == 1

        list_response = client.get("/api/v1/analyses", params={"docket_id": "D1"})
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        trace_response = client.get(f"/api/v1/analyses/{analysis_id}/trace")
        assert trace_response.status_code == 200
        actions = [t["action"] for t in trace_response.json()]
        assert "submit_verdict" in actions

        cluster_id = cluster_summary["id"]
        cluster_response = client.get(f"/api/v1/clusters/{cluster_id}")
        assert cluster_response.status_code == 200
        cluster_body = cluster_response.json()
        assert len(cluster_body["members"]) == 4
        assert cluster_body["rationale"] == "Identical wording across members."

        graph_response = client.get(f"/api/v1/clusters/{cluster_id}/graph")
        assert graph_response.status_code == 200
        graph_body = graph_response.json()
        assert len(graph_body["nodes"]) == 4
        medoid_id = next(n["id"] for n in graph_body["nodes"] if n["is_medoid"])
        assert all(e["source"] == medoid_id for e in graph_body["edges"])
        assert len(graph_body["edges"]) == 3  # star edges, medoid excluded from edges' targets

        review_response = client.post(
            f"/api/v1/clusters/{cluster_id}/reviews",
            json={"decision": "confirmed", "note": "Looks correct."},
        )
        assert review_response.status_code == 201
        assert review_response.json()["decision"] == "confirmed"

        updated_cluster = client.get(f"/api/v1/clusters/{cluster_id}").json()
        assert updated_cluster["review_status"] == "confirmed"

        csv_response = client.get("/api/v1/reviews/export.csv", params={"docket_id": "D1"})
        assert csv_response.status_code == 200
        assert "confirmed" in csv_response.text
        assert "review_id" in csv_response.text.splitlines()[0]


def test_create_analysis_409_when_one_already_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, engine = _make_app(tmp_path, monkeypatch)
    _seed_docket(engine)

    with Session(engine) as session:
        session.add(
            Analysis(id="already-running", mode="docket", docket_id="D1", status="running", params={})
        )
        session.commit()

    with TestClient(app) as client:
        response = client.post("/api/v1/analyses", json={"mode": "docket", "docket_id": "D1"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "analysis_running"


def test_get_unknown_analysis_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/analyses/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"


def test_get_unknown_cluster_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/clusters/999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "cluster_not_found"


def test_review_on_unknown_cluster_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/clusters/999/reviews", json={"decision": "confirmed"})
        assert response.status_code == 404
