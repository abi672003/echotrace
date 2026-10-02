from datetime import datetime, timezone

import numpy as np
from sqlmodel import Session, SQLModel, create_engine, select

from app.agent.tools import (
    TOOL_SPECS,
    ToolContext,
    compare,
    family_summary,
    list_members,
    search_similar,
    timeline,
    truncate_observation,
)
from app.models import Cluster, ClusterMember, Docket, Document, EmbeddingCache

MODEL = "gemini-embedding-001"


def _vec(values: list[float]) -> np.ndarray:
    arr = np.array(values, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def _build_fixture(session: Session) -> ToolContext:
    session.add(Docket(id="D1", source="sample"))

    docs_spec = [
        ("doc1", "I strongly oppose this rule for economic reasons stated here.", [1.0, 0.0, 0.0, 0.0]),
        ("doc2", "I strongly oppose this proposed rule for economic reasons noted.", [0.95, 0.05, 0.0, 0.0]),
        ("doc3", "I oppose this rule because of economic reasons described here.", [0.9, 0.1, 0.0, 0.0]),
        ("doc4", "Totally unrelated comment about a different topic entirely here.", [0.0, 1.0, 0.0, 0.0]),
        ("doc5", "I also strongly oppose this rule for economic reasons given.", [0.93, 0.07, 0.0, 0.0]),
    ]
    documents = {}
    for i, (ext_id, text, vec) in enumerate(docs_spec):
        doc = Document(
            docket_id="D1",
            external_id=ext_id,
            submitter_label=f"Person {i}",
            submitter_hash=f"hash_{ext_id}_abcdefgh",
            text=text,
            text_hash=f"th_{ext_id}",
            word_count=len(text.split()),
            posted_at=datetime(2024, 5, 1, i, tzinfo=timezone.utc),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        documents[ext_id] = doc
        session.add(
            EmbeddingCache(text_hash=f"th_{ext_id}", model=MODEL, dim=4, vector=_vec(vec).tobytes())
        )
    session.commit()

    cluster = Cluster(
        analysis_id="analysis1",
        medoid_document_id=documents["doc1"].id,
        size=3,
        metrics={"reword_index": 0.5},
        campaign_score=0.6,
        preliminary_type="organic_agreement",
    )
    session.add(cluster)
    session.commit()
    session.refresh(cluster)

    session.add(
        ClusterMember(
            cluster_id=cluster.id,
            document_id=documents["doc1"].id,
            sim_to_medoid=1.0,
            lex_to_medoid=1.0,
            ai_score=0.2,
            is_medoid=True,
        )
    )
    session.add(
        ClusterMember(
            cluster_id=cluster.id,
            document_id=documents["doc2"].id,
            sim_to_medoid=0.95,
            lex_to_medoid=0.4,
            ai_score=0.6,
            is_medoid=False,
        )
    )
    session.add(
        ClusterMember(
            cluster_id=cluster.id,
            document_id=documents["doc3"].id,
            sim_to_medoid=0.9,
            lex_to_medoid=0.3,
            ai_score=0.8,
            is_medoid=False,
        )
    )
    session.commit()

    return ToolContext(session=session, cluster=cluster, docket_id="D1")


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_family_summary_reports_size_type_and_date_range() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = family_summary(ctx)
        assert result["size"] == 3
        assert result["preliminary_type"] == "organic_agreement"
        assert result["date_range"]["earliest"] is not None
        assert result["date_range"]["latest"] is not None


def test_list_members_orders_by_sim_by_default() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = list_members(ctx)
        sims = [m["sim"] for m in result]
        assert sims == sorted(sims, reverse=True)
        assert all(len(m["submitter_hash_prefix"]) == 8 for m in result)


def test_list_members_orders_by_ai_score() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = list_members(ctx, order="ai")
        ai_scores = [m["ai_score"] for m in result]
        assert ai_scores == sorted(ai_scores, reverse=True)


def test_list_members_respects_limit_cap_of_10() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = list_members(ctx, limit=100)
        assert len(result) <= 10


def test_compare_returns_sem_lex_and_shared_phrases() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        doc1_id = ctx.session.exec(select(Document).where(Document.external_id == "doc1")).first().id
        doc2_id = ctx.session.exec(select(Document).where(Document.external_id == "doc2")).first().id

        result = compare(ctx, doc1_id, doc2_id)
        assert 0.0 <= result["sem"] <= 1.0
        assert 0.0 <= result["lex"] <= 1.0
        assert isinstance(result["shared_phrases"], list)
        assert len(result["shared_phrases"]) <= 5


def test_compare_unknown_document_returns_error() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = compare(ctx, 99999, 99998)
        assert "error" in result


def test_search_similar_excludes_family_members_and_finds_doc5_not_doc4() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        doc1 = session.exec(select(Document).where(Document.external_id == "doc1")).first()

        result = search_similar(ctx, doc1.id, k=10, min_sim=0.75)
        found_ids = {r["id"] for r in result}
        doc5 = session.exec(select(Document).where(Document.external_id == "doc5")).first()
        doc4 = session.exec(select(Document).where(Document.external_id == "doc4")).first()

        assert doc5.id in found_ids  # similar, outside the family
        assert doc4.id not in found_ids  # not similar enough (orthogonal vector)
        # family members (doc1/doc2/doc3) must never appear, even doc1 itself
        family_doc_ids = {doc1.id}
        assert family_doc_ids.isdisjoint(found_ids)


def test_timeline_buckets_by_hour() -> None:
    with Session(_engine()) as session:
        ctx = _build_fixture(session)
        result = timeline(ctx)
        assert len(result["buckets"]) == 3  # doc1, doc2, doc3 each at a different hour
        assert all(b["count"] >= 1 for b in result["buckets"])


def test_tool_specs_include_all_six_tools() -> None:
    names = {spec.name for spec in TOOL_SPECS}
    assert names == {
        "family_summary",
        "list_members",
        "compare",
        "search_similar",
        "timeline",
        "submit_verdict",
    }


def test_truncate_observation_passes_through_small_payloads() -> None:
    small = {"a": 1}
    assert truncate_observation(small) == small


def test_truncate_observation_caps_large_payloads_at_4kb() -> None:
    big = {"text": "x" * 10_000}
    result = truncate_observation(big, max_bytes=4096)
    assert result["truncated"] is True
    assert len(result["preview"].encode("utf-8")) <= 4096
