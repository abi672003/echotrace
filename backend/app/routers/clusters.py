import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models import Analysis, Cluster, ClusterMember, Document, Review
from app.schemas import (
    ClusterMemberOut,
    ClusterOut,
    GraphEdge,
    GraphNode,
    GraphOut,
    ReviewIn,
    ReviewOut,
)
from app.security import require_admin

router = APIRouter()

CSV_COLUMNS = [
    "review_id",
    "cluster_id",
    "decision",
    "note",
    "created_at",
    "size",
    "campaign_score",
    "preliminary_type",
    "verdict_type",
    "confidence",
    "reword_index",
    "burst_24h",
    "name_diversity",
    "ai_agg",
]


def _cluster_member_to_out(member: ClusterMember) -> ClusterMemberOut:
    return ClusterMemberOut(
        document_id=member.document_id,
        sim_to_medoid=member.sim_to_medoid,
        lex_to_medoid=member.lex_to_medoid,
        ai_score=member.ai_score,
        is_medoid=member.is_medoid,
    )


@router.get("/clusters/{cluster_id}", response_model=ClusterOut)
def get_cluster(
    cluster_id: int, limit: int = 50, offset: int = 0, session: Session = Depends(get_session)
) -> ClusterOut:
    cluster = session.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cluster_not_found", "message": f"No cluster {cluster_id}."},
        )
    members = session.exec(
        select(ClusterMember)
        .where(ClusterMember.cluster_id == cluster_id)
        .offset(offset)
        .limit(limit)
    ).all()
    return ClusterOut(
        id=cluster.id,
        analysis_id=cluster.analysis_id,
        size=cluster.size,
        metrics=cluster.metrics,
        campaign_score=cluster.campaign_score,
        preliminary_type=cluster.preliminary_type,
        verdict_type=cluster.verdict_type,
        confidence=cluster.confidence,
        rationale=cluster.rationale,
        cited_document_ids=cluster.cited_document_ids,
        citations_corrected=cluster.citations_corrected,
        recommend_review=cluster.recommend_review,
        review_status=cluster.review_status,
        members=[_cluster_member_to_out(m) for m in members],
    )


@router.get("/clusters/{cluster_id}/graph", response_model=GraphOut)
def get_cluster_graph(
    cluster_id: int, max_nodes: int = 60, session: Session = Depends(get_session)
) -> GraphOut:
    cluster = session.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cluster_not_found", "message": f"No cluster {cluster_id}."},
        )
    all_members = session.exec(
        select(ClusterMember).where(ClusterMember.cluster_id == cluster_id)
    ).all()
    members = sorted(all_members, key=lambda m: (not m.is_medoid, -m.sim_to_medoid))[:max_nodes]
    docs = {
        d.id: d
        for d in session.exec(
            select(Document).where(Document.id.in_([m.document_id for m in members]))
        ).all()
    }

    nodes = [
        GraphNode(
            id=m.document_id,
            excerpt=docs[m.document_id].text[:300],
            submitter_label=docs[m.document_id].submitter_label,
            posted_at=docs[m.document_id].posted_at,
            ai_score=m.ai_score,
            sim=m.sim_to_medoid,
            lex=m.lex_to_medoid,
            is_medoid=m.is_medoid,
        )
        for m in members
    ]
    medoid_id = cluster.medoid_document_id
    edges = [
        GraphEdge(source=medoid_id, target=m.document_id, sim=m.sim_to_medoid, lex=m.lex_to_medoid)
        for m in members
        if m.document_id != medoid_id
    ]
    return GraphOut(nodes=nodes, edges=edges)


@router.post(
    "/clusters/{cluster_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_review(
    cluster_id: int, body: ReviewIn, session: Session = Depends(get_session)
) -> ReviewOut:
    cluster = session.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cluster_not_found", "message": f"No cluster {cluster_id}."},
        )
    review = Review(cluster_id=cluster_id, decision=body.decision, note=body.note)
    session.add(review)
    cluster.review_status = body.decision
    session.add(cluster)
    session.commit()
    session.refresh(review)
    return ReviewOut(
        id=review.id,
        cluster_id=review.cluster_id,
        decision=review.decision,
        note=review.note,
        created_at=review.created_at,
    )


def build_reviews_csv(session: Session, docket_id: str | None) -> str:
    """Shared by `GET /reviews/export.csv` and `scripts/export_reviews.py`."""
    statement = select(Review, Cluster).join(Cluster, Review.cluster_id == Cluster.id)  # type: ignore[arg-type]
    if docket_id:
        statement = statement.join(Analysis, Cluster.analysis_id == Analysis.id).where(  # type: ignore[arg-type]
            Analysis.docket_id == docket_id
        )
    rows = session.exec(statement).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for review, cluster in rows:
        metrics = cluster.metrics
        writer.writerow(
            [
                review.id,
                review.cluster_id,
                review.decision,
                review.note or "",
                review.created_at.isoformat(),
                cluster.size,
                cluster.campaign_score,
                cluster.preliminary_type,
                cluster.verdict_type or "",
                cluster.confidence or "",
                metrics.get("reword_index"),
                metrics.get("burst_24h"),
                metrics.get("name_diversity"),
                metrics.get("ai_agg"),
            ]
        )
    return buffer.getvalue()


@router.get("/reviews/export.csv")
def export_reviews_csv(
    docket_id: str | None = None, session: Session = Depends(get_session)
) -> StreamingResponse:
    csv_text = build_reviews_csv(session, docket_id)
    return StreamingResponse(iter([csv_text]), media_type="text/csv")
