import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Analysis, AnalysisStep, Cluster, Docket, Document
from app.services.embeddings import FakeEmbedder
from app.services.llm import FakeLLM
from app.services.pipeline import run_docket_analysis, run_text_check

GROUP_A_TEXT = (
    "I am writing to express my strong opposition to this proposed rule because it "
    "would harm small businesses across the region and fails to consider long-term "
    "economic impacts on our community members and families."
)
GROUP_B_TEXT = (
    "As a longtime resident I fully support this proposed rule because it protects "
    "public health and the environment for future generations in our community and "
    "beyond our immediate region as well."
)

AI_SCORE_RESPONSE = json.dumps(
    {
        "scores": [
            {"id": "hashA", "score": 0.4, "reason": "formal tone"},
            {"id": "hashB", "score": 0.4, "reason": "formal tone"},
        ]
    }
)
VERDICT_RESPONSE = json.dumps(
    {
        "thought": "Identical wording across many submitters.",
        "action": "submit_verdict",
        "args": {
            "type": "form_letter",
            "confidence": "high",
            "rationale": "Near-identical text across all members.",
            "cited_document_ids": [0],  # deliberately invalid; proves correction still yields a verdict
            "recommend_review": True,
        },
    }
)
SUMMARY_RESPONSE = json.dumps({"summary": "Two form-letter families were found in this docket."})


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_docket(session: Session, docket_id: str = "E2E-DOCKET") -> None:
    session.add(Docket(id=docket_id, source="sample"))
    base = datetime(2024, 5, 1, tzinfo=timezone.utc)
    for i in range(10):
        session.add(
            Document(
                docket_id=docket_id,
                external_id=f"a-{i}",
                submitter_label=f"Group A Person {i}",
                submitter_hash=f"hash_a_{i}",
                text=GROUP_A_TEXT,
                text_hash="hashA",
                word_count=30,
                posted_at=base + timedelta(hours=i),
            )
        )
    for i in range(10):
        session.add(
            Document(
                docket_id=docket_id,
                external_id=f"b-{i}",
                submitter_label=f"Group B Person {i}",
                submitter_hash=f"hash_b_{i}",
                text=GROUP_B_TEXT,
                text_hash="hashB",
                word_count=30,
                posted_at=base + timedelta(hours=i),
            )
        )
    session.commit()


@pytest.mark.asyncio
async def test_run_docket_analysis_end_to_end_with_fakes_on_20_comments() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_docket(session)

        analysis = Analysis(id="analysis-e2e", mode="docket", docket_id="E2E-DOCKET", params={})
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        embedder = FakeEmbedder()
        llm = FakeLLM([AI_SCORE_RESPONSE, AI_SCORE_RESPONSE, VERDICT_RESPONSE, VERDICT_RESPONSE, SUMMARY_RESPONSE])

        await run_docket_analysis(session, analysis, embedder, llm)

        session.refresh(analysis)
        assert analysis.status == "done"
        assert analysis.error is None
        assert analysis.embed_calls == 1  # 2 unique texts, batched in one call
        assert analysis.llm_calls == 5
        assert analysis.summary == "Two form-letter families were found in this docket."

        steps = session.exec(
            select(AnalysisStep).where(AnalysisStep.analysis_id == analysis.id)
        ).all()
        step_names = {s.name for s in steps}
        assert step_names == {"normalize", "embed", "cluster", "measure", "ai_score", "aggregate", "agent"}
        assert all(s.status == "done" for s in steps)

        clusters = session.exec(select(Cluster).where(Cluster.analysis_id == analysis.id)).all()
        assert len(clusters) == 2
        for cluster in clusters:
            assert cluster.size == 10
            assert cluster.preliminary_type == "form_letter"
            assert cluster.verdict_type == "form_letter"
            assert cluster.confidence in ("low", "medium", "high")
            assert cluster.rationale == "Near-identical text across all members."
            # the scripted citation (doc id 0) never exists -> must be corrected away
            assert cluster.cited_document_ids == []
            assert cluster.citations_corrected is True


@pytest.mark.asyncio
async def test_run_docket_analysis_marks_failed_on_exception() -> None:
    engine = _engine()
    with Session(engine) as session:
        # no docket/documents seeded at all -> embed_texts gets an empty dict, which is
        # harmless, so force a real failure via a docket_id that doesn't exist is fine
        # (zero documents just produces zero clusters, not a failure) - instead, break
        # the LLM to simulate a genuine pipeline failure during ai_score/agent.
        _seed_docket(session, docket_id="FAIL-DOCKET")
        analysis = Analysis(id="analysis-fail", mode="docket", docket_id="FAIL-DOCKET", params={})
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        embedder = FakeEmbedder()
        llm = FakeLLM([])  # no scripted responses at all -> first complete_json call raises

        await run_docket_analysis(session, analysis, embedder, llm)

        session.refresh(analysis)
        assert analysis.status == "failed"
        assert analysis.error is not None

        steps = session.exec(
            select(AnalysisStep).where(AnalysisStep.analysis_id == analysis.id)
        ).all()
        failed_steps = [s for s in steps if s.status == "failed"]
        # the ai_score step is where the LLM is first called in this pipeline
        assert any(s.name == "ai_score" for s in failed_steps)


@pytest.mark.asyncio
async def test_run_text_check_reports_no_family_found_with_too_few_neighbours() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(Docket(id="TC-DOCKET", source="sample"))
        session.commit()
        # no documents at all ingested -> zero candidates -> zero neighbours

        analysis = Analysis(
            id="analysis-tc",
            mode="text",
            docket_id="TC-DOCKET",
            input_text="Some pasted comment text that is long enough to pass the floor.",
            params={},
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        embedder = FakeEmbedder()
        llm = FakeLLM([])

        await run_text_check(session, analysis, embedder, llm)

        session.refresh(analysis)
        assert analysis.status == "done"
        assert analysis.summary == "No family found."

        clusters = session.exec(select(Cluster).where(Cluster.analysis_id == analysis.id)).all()
        assert clusters == []

        steps = {
            s.name: s.status
            for s in session.exec(
                select(AnalysisStep).where(AnalysisStep.analysis_id == analysis.id)
            ).all()
        }
        assert steps["embed"] == "done"
        assert steps["cluster"] == "done"
        assert steps["measure"] == "skipped"
        assert steps["ai_score"] == "skipped"
        assert steps["aggregate"] == "skipped"
        assert steps["agent"] == "skipped"
