import json

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.agent.runner import FALLBACK_RATIONALE, review_family
from app.models import AgentTrace, Analysis, Cluster, ClusterMember, Docket, Document
from app.services.llm import FakeLLM


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _build_fixture(session: Session) -> tuple[Cluster, int, int]:
    session.add(Docket(id="D1", source="sample"))

    doc1 = Document(
        docket_id="D1",
        external_id="doc1",
        submitter_label="A",
        submitter_hash="h1",
        text="I strongly oppose this proposed rule for economic reasons.",
        text_hash="th1",
        word_count=9,
    )
    doc2 = Document(
        docket_id="D1",
        external_id="doc2",
        submitter_label="B",
        submitter_hash="h2",
        text="I also strongly oppose this proposed rule for economic reasons.",
        text_hash="th2",
        word_count=10,
    )
    session.add(doc1)
    session.add(doc2)
    session.commit()
    session.refresh(doc1)
    session.refresh(doc2)

    session.add(Analysis(id="analysis1", mode="docket", docket_id="D1", params={}))
    session.commit()

    cluster = Cluster(
        analysis_id="analysis1",
        medoid_document_id=doc1.id,
        size=2,
        metrics={"reword_index": 0.5, "burst_24h": 0.2, "name_diversity": 1.0, "ai_agg": 0.0},
        campaign_score=0.4,
        preliminary_type="organic_agreement",
    )
    session.add(cluster)
    session.commit()
    session.refresh(cluster)

    session.add(
        ClusterMember(
            cluster_id=cluster.id, document_id=doc1.id, sim_to_medoid=1.0, lex_to_medoid=1.0, is_medoid=True
        )
    )
    session.add(
        ClusterMember(
            cluster_id=cluster.id, document_id=doc2.id, sim_to_medoid=0.9, lex_to_medoid=0.4, is_medoid=False
        )
    )
    session.commit()

    return cluster, doc1.id, doc2.id


@pytest.mark.asyncio
async def test_review_family_applies_a_normal_verdict() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, doc1_id, doc2_id = _build_fixture(session)
        turn = {
            "thought": "Varied wording, low burst, high diversity.",
            "action": "submit_verdict",
            "args": {
                "type": "organic_agreement",
                "confidence": "high",
                "rationale": "Independently worded, spread-out timing.",
                "cited_document_ids": [doc1_id, doc2_id],
                "recommend_review": True,
            },
        }
        llm = FakeLLM([json.dumps(turn)])

        result = await review_family(session, llm, cluster, docket_id="D1")

        assert result.verdict_type == "organic_agreement"
        assert result.confidence == "high"
        assert result.citations_corrected is False
        assert set(result.cited_document_ids) == {doc1_id, doc2_id}
        assert result.rationale == "Independently worded, spread-out timing."


@pytest.mark.asyncio
async def test_review_family_recovers_from_invalid_json_via_one_repair() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, doc1_id, doc2_id = _build_fixture(session)
        valid_turn = {
            "thought": "ok",
            "action": "submit_verdict",
            "args": {
                "type": "organic_agreement",
                "confidence": "medium",
                "rationale": "Repaired turn.",
                "cited_document_ids": [doc1_id, doc2_id],
                "recommend_review": True,
            },
        }
        # first reply is garbage; complete_json's own repair retry recovers on the 2nd
        llm = FakeLLM(["this is not json at all", json.dumps(valid_turn)])

        result = await review_family(session, llm, cluster, docket_id="D1")

        assert llm.call_count == 2
        assert result.verdict_type == "organic_agreement"
        assert result.rationale == "Repaired turn."
        assert result.citations_corrected is False


@pytest.mark.asyncio
async def test_review_family_falls_back_when_json_is_invalid_twice_in_a_row() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, _, _ = _build_fixture(session)
        # both the first attempt AND its one repair retry are invalid -> LLMJSONError
        llm = FakeLLM(["garbage one", "garbage two"])

        result = await review_family(session, llm, cluster, docket_id="D1")

        assert result.verdict_type == cluster.preliminary_type
        assert result.confidence == "low"
        assert result.rationale == FALLBACK_RATIONALE
        assert result.cited_document_ids == []


@pytest.mark.asyncio
async def test_review_family_removes_hallucinated_citation_and_lowers_confidence() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, doc1_id, doc2_id = _build_fixture(session)
        turn = {
            "thought": "ok",
            "action": "submit_verdict",
            "args": {
                "type": "organic_agreement",
                "confidence": "high",
                "rationale": "Cites a document never seen.",
                "cited_document_ids": [999999],  # hallucinated, not a family member or seen via tools
                "recommend_review": True,
            },
        }
        llm = FakeLLM([json.dumps(turn)])

        result = await review_family(session, llm, cluster, docket_id="D1")

        assert result.cited_document_ids == []
        assert result.citations_corrected is True
        assert result.confidence == "medium"  # stepped down one level from "high"


@pytest.mark.asyncio
async def test_review_family_keeps_a_valid_citation_seen_via_a_tool_not_the_family() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, doc1_id, _ = _build_fixture(session)
        turns = [
            json.dumps({"thought": "look at members", "action": "list_members", "args": {}}),
            json.dumps(
                {
                    "thought": "ok",
                    "action": "submit_verdict",
                    "args": {
                        "type": "organic_agreement",
                        "confidence": "high",
                        "rationale": "Two valid, seen citations.",
                        "cited_document_ids": [doc1_id],  # only 1 valid -> should still lower confidence
                        "recommend_review": True,
                    },
                }
            ),
        ]
        llm = FakeLLM(turns)

        result = await review_family(session, llm, cluster, docket_id="D1", max_steps=5)

        # only one valid citation -> confidence still drops even though it IS a real id
        assert result.cited_document_ids == [doc1_id]
        assert result.confidence == "medium"
        assert result.citations_corrected is True


@pytest.mark.asyncio
async def test_review_family_writes_agent_trace_rows_for_tool_steps() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, doc1_id, doc2_id = _build_fixture(session)
        turns = [
            json.dumps({"thought": "check timeline", "action": "timeline", "args": {}}),
            json.dumps(
                {
                    "thought": "done",
                    "action": "submit_verdict",
                    "args": {
                        "type": "organic_agreement",
                        "confidence": "high",
                        "rationale": "ok",
                        "cited_document_ids": [doc1_id, doc2_id],
                        "recommend_review": True,
                    },
                }
            ),
        ]
        llm = FakeLLM(turns)

        await review_family(session, llm, cluster, docket_id="D1", max_steps=5)

        traces = session.exec(
            select(AgentTrace).where(AgentTrace.analysis_id == "analysis1")
        ).all()
        actions = [t.action for t in traces]
        assert actions == ["timeline", "submit_verdict"]


@pytest.mark.asyncio
async def test_review_family_falls_back_when_step_budget_exhausted() -> None:
    engine = _engine()
    with Session(engine) as session:
        cluster, _, _ = _build_fixture(session)
        # two turns that never call submit_verdict, with max_steps=2
        turns = [
            json.dumps({"thought": "look", "action": "timeline", "args": {}}),
            json.dumps({"thought": "look again", "action": "timeline", "args": {}}),
        ]
        llm = FakeLLM(turns)

        result = await review_family(session, llm, cluster, docket_id="D1", max_steps=2)

        assert llm.call_count == 2
        assert result.verdict_type == cluster.preliminary_type
        assert result.confidence == "low"
        assert result.rationale == FALLBACK_RATIONALE
