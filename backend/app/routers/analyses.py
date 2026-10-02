import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, get_session
from app.models import AgentTrace, Analysis, AnalysisStep, Cluster, Document
from app.schemas import (
    AgentTraceOut,
    AnalysisCreate,
    AnalysisCreateOut,
    AnalysisOut,
    AnalysisStepOut,
    AnalysisSummary,
    AnalysisUsage,
    ClusterMetrics,
    ClusterSummary,
)
from app.security import require_admin
from app.services.embeddings import Embedder, GeminiEmbedder
from app.services.llm import LLM, FallbackLLM, GeminiLLM, GroqLLM
from app.services.pipeline import run_docket_analysis, run_text_check

router = APIRouter()


def _make_embedder() -> Embedder:
    return GeminiEmbedder()


def _make_llm() -> LLM:
    return FallbackLLM(GroqLLM(), GeminiLLM())


def _is_analysis_running(session: Session) -> bool:
    existing = session.exec(
        select(Analysis).where(Analysis.status.in_(["queued", "running"]))
    ).first()
    return existing is not None


async def _run_analysis_background(analysis_id: str, mode: str) -> None:
    with Session(engine) as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        embedder = _make_embedder()
        llm = _make_llm()
        if mode == "docket":
            await run_docket_analysis(session, analysis, embedder, llm)
        else:
            await run_text_check(session, analysis, embedder, llm)


def _analysis_to_summary(analysis: Analysis) -> AnalysisSummary:
    return AnalysisSummary(
        id=analysis.id,
        mode=analysis.mode,
        docket_id=analysis.docket_id,
        status=analysis.status,
        created_at=analysis.created_at,
        finished_at=analysis.finished_at,
    )


def _cluster_to_summary(session: Session, cluster: Cluster) -> ClusterSummary:
    medoid = session.get(Document, cluster.medoid_document_id)
    metrics = cluster.metrics
    return ClusterSummary(
        id=cluster.id,
        size=cluster.size,
        campaign_score=cluster.campaign_score,
        preliminary_type=cluster.preliminary_type,
        verdict_type=cluster.verdict_type,
        confidence=cluster.confidence,
        review_status=cluster.review_status,
        metrics=ClusterMetrics(
            reword_index=metrics["reword_index"],
            burst_24h=metrics["burst_24h"],
            name_diversity=metrics["name_diversity"],
            ai_agg=metrics["ai_agg"],
        ),
        medoid_excerpt=medoid.text[:300] if medoid else "",
    )


def _analysis_to_out(session: Session, analysis: Analysis) -> AnalysisOut:
    steps = session.exec(
        select(AnalysisStep).where(AnalysisStep.analysis_id == analysis.id)
    ).all()
    clusters = session.exec(select(Cluster).where(Cluster.analysis_id == analysis.id)).all()
    clusters_sorted = sorted(clusters, key=lambda c: -c.campaign_score)
    return AnalysisOut(
        id=analysis.id,
        mode=analysis.mode,
        docket_id=analysis.docket_id,
        status=analysis.status,
        steps=[
            AnalysisStepOut(
                name=s.name,
                status=s.status,
                detail=s.detail,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in steps
        ],
        summary=analysis.summary,
        usage=AnalysisUsage(llm_calls=analysis.llm_calls, embed_calls=analysis.embed_calls),
        clusters=[_cluster_to_summary(session, c) for c in clusters_sorted],
        created_at=analysis.created_at,
        finished_at=analysis.finished_at,
    )


@router.post(
    "/analyses",
    response_model=AnalysisCreateOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
def create_analysis(
    body: AnalysisCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AnalysisCreateOut:
    if _is_analysis_running(session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "analysis_running", "message": "An analysis is already running."},
        )

    settings = get_settings()
    analysis = Analysis(
        id=uuid.uuid4().hex,
        mode=body.mode,
        docket_id=body.docket_id,
        input_text=body.text,
        params={
            "SIM_EDGE": settings.SIM_EDGE,
            "SIM_MEMBER": settings.SIM_MEMBER,
            "MIN_FAMILY": settings.MIN_FAMILY,
            "MIN_CAMPAIGN": settings.MIN_CAMPAIGN,
            "GEMINI_EMBED_MODEL": settings.GEMINI_EMBED_MODEL,
            "GROQ_CHAT_MODEL": settings.GROQ_CHAT_MODEL,
            "GEMINI_CHAT_MODEL": settings.GEMINI_CHAT_MODEL,
        },
    )
    session.add(analysis)
    session.commit()

    background_tasks.add_task(_run_analysis_background, analysis.id, body.mode)
    return AnalysisCreateOut(analysis_id=analysis.id)


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(
    docket_id: str | None = None, session: Session = Depends(get_session)
) -> list[AnalysisSummary]:
    statement = select(Analysis)
    if docket_id:
        statement = statement.where(Analysis.docket_id == docket_id)
    analyses = session.exec(statement.order_by(Analysis.created_at.desc())).all()
    return [_analysis_to_summary(a) for a in analyses]


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, session: Session = Depends(get_session)) -> AnalysisOut:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "analysis_not_found", "message": f"No analysis {analysis_id!r}."},
        )
    return _analysis_to_out(session, analysis)


@router.get("/analyses/{analysis_id}/trace", response_model=list[AgentTraceOut])
def get_analysis_trace(
    analysis_id: str, cluster_id: int | None = None, session: Session = Depends(get_session)
) -> list[AgentTraceOut]:
    statement = select(AgentTrace).where(AgentTrace.analysis_id == analysis_id)
    if cluster_id is not None:
        statement = statement.where(AgentTrace.cluster_id == cluster_id)
    traces = session.exec(statement.order_by(AgentTrace.step_no)).all()
    return [
        AgentTraceOut(
            step_no=t.step_no,
            action=t.action,
            args=t.args,
            observation=t.observation,
            cluster_id=t.cluster_id,
            created_at=t.created_at,
        )
        for t in traces
    ]
