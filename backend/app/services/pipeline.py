import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np
from sqlmodel import Session, select

from app.agent.prompts import DOCKET_SUMMARY_SYSTEM_PROMPT, render_docket_summary_user_message
from app.agent.runner import review_family
from app.config import Settings, get_settings
from app.models import (
    Analysis,
    AnalysisStep,
    Cluster,
    ClusterMember,
    Document,
    EmbeddingCache,
)
from app.services.aggregation import family_ai_agg, single_comment_agg
from app.services.ai_scoring import score_members
from app.services.embeddings import Embedder, embed_texts
from app.services.features import (
    CampaignMetrics,
    FamilyMember,
    campaign_score,
    compute_metrics,
    jaccard,
    preliminary_type,
    word_shingles,
)
from app.services.llm import LLM
from app.services.normalize import normalize_for_hash, text_hash
from app.services.similarity import Family, build_families, nearest

_pipeline_lock = asyncio.Lock()


def pipeline_is_running() -> bool:
    return _pipeline_lock.locked()


def _metrics_to_dict(metrics: CampaignMetrics) -> dict:
    return {
        "mean_sem": metrics.mean_sem,
        "mean_lex": metrics.mean_lex,
        "reword_index": metrics.reword_index,
        "exact_dup_share": metrics.exact_dup_share,
        "burst_24h": metrics.burst_24h,
        "name_diversity": metrics.name_diversity,
        "anon_share": metrics.anon_share,
        "ai_agg": metrics.ai_agg,
    }


def _is_anonymous(document: Document) -> bool:
    return document.submitter_label in ("", "Anonymous")


@contextmanager
def _step(session: Session, analysis: Analysis, name: str) -> Iterator[AnalysisStep]:
    """Tracks one `AnalysisStep`: `running` -> `done` on success, or `failed` (with the
    exception message) if the block raises — a step is never left stuck in `running`."""
    step = AnalysisStep(
        analysis_id=analysis.id, name=name, status="running", started_at=datetime.now(timezone.utc)
    )
    session.add(step)
    analysis.current_step = name
    session.add(analysis)
    session.commit()
    session.refresh(step)
    try:
        yield step
        step.status = "done"
    except Exception as exc:
        step.status = "failed"
        step.detail = str(exc)
        raise
    finally:
        step.finished_at = datetime.now(timezone.utc)
        session.add(step)
        session.commit()


def _skip_remaining_steps(session: Session, analysis: Analysis, names: list[str], detail: str) -> None:
    for name in names:
        session.add(
            AnalysisStep(
                analysis_id=analysis.id,
                name=name,
                status="skipped",
                detail=detail,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        )
    session.commit()


async def _generate_docket_summary(llm: LLM, clusters: list[Cluster]) -> str | None:
    reviewed = [c for c in clusters if c.verdict_type is not None]
    if not reviewed:
        return None
    verdicts = [
        {
            "type": c.verdict_type,
            "confidence": c.confidence,
            "size": c.size,
            "campaign_score": c.campaign_score,
        }
        for c in reviewed
    ]
    messages = [{"role": "user", "content": render_docket_summary_user_message(verdicts)}]
    response = await llm.complete_json(DOCKET_SUMMARY_SYSTEM_PROMPT, messages, schema={})
    return str(response.get("summary", "")) or None


def _build_family_members(
    scored_docs: list[Document], family: Family, similarity: np.ndarray
) -> list[FamilyMember]:
    return [
        FamilyMember(
            sim_to_medoid=float(similarity[family.medoid, i]),
            text=scored_docs[i].text,
            text_hash=scored_docs[i].text_hash,
            submitter_hash=scored_docs[i].submitter_hash,
            is_anonymous=_is_anonymous(scored_docs[i]),
            posted_at=scored_docs[i].posted_at,
        )
        for i in family.members
    ]


async def _store_family_as_cluster(
    session: Session,
    settings: Settings,
    analysis: Analysis,
    scored_docs: list[Document],
    family: Family,
    similarity: np.ndarray,
) -> Cluster:
    family_members = _build_family_members(scored_docs, family, similarity)
    medoid_position = family.members.index(family.medoid)
    metrics = compute_metrics(family_members, family_members[medoid_position], ai_agg=0.0)
    prelim_type = preliminary_type(metrics, settings.MIN_CAMPAIGN)

    cluster = Cluster(
        analysis_id=analysis.id,
        medoid_document_id=scored_docs[family.medoid].id,
        size=metrics.size,
        metrics=_metrics_to_dict(metrics),
        campaign_score=campaign_score(metrics),
        preliminary_type=prelim_type,
    )
    session.add(cluster)
    session.commit()
    session.refresh(cluster)

    medoid_shingles = word_shingles(scored_docs[family.medoid].text)
    for i in family.members:
        doc = scored_docs[i]
        session.add(
            ClusterMember(
                cluster_id=cluster.id,
                document_id=doc.id,
                sim_to_medoid=float(similarity[family.medoid, i]),
                lex_to_medoid=jaccard(word_shingles(doc.text), medoid_shingles),
                is_medoid=(i == family.medoid),
            )
        )
    session.commit()
    return cluster


async def _score_and_aggregate_cluster(
    session: Session, settings: Settings, llm: LLM, cluster: Cluster
) -> None:
    members = session.exec(
        select(ClusterMember).where(ClusterMember.cluster_id == cluster.id)
    ).all()
    documents = {
        d.id: d
        for d in session.exec(
            select(Document).where(Document.id.in_([m.document_id for m in members]))
        ).all()
    }

    ordered = sorted(members, key=lambda m: (not m.is_medoid, -m.sim_to_medoid))
    sample = ordered[: settings.AI_SAMPLE_PER_FAMILY]
    items = [(documents[m.document_id].text_hash, documents[m.document_id].text) for m in sample]
    scores = await score_members(session, llm, items)

    for member in sample:
        text_hash_value = documents[member.document_id].text_hash
        if text_hash_value in scores:
            member.ai_score = scores[text_hash_value][0]
            session.add(member)
    session.commit()

    scored_members = [m for m in members if m.ai_score is not None]
    ai_agg = family_ai_agg(
        [m.ai_score for m in scored_members], [m.sim_to_medoid for m in scored_members]
    )

    metrics_dict = dict(cluster.metrics)
    metrics_dict["ai_agg"] = ai_agg
    metrics = CampaignMetrics(
        size=cluster.size,
        mean_sem=metrics_dict["mean_sem"],
        mean_lex=metrics_dict["mean_lex"],
        reword_index=metrics_dict["reword_index"],
        exact_dup_share=metrics_dict["exact_dup_share"],
        burst_24h=metrics_dict["burst_24h"],
        name_diversity=metrics_dict["name_diversity"],
        anon_share=metrics_dict["anon_share"],
        ai_agg=ai_agg,
    )
    cluster.metrics = metrics_dict
    cluster.campaign_score = campaign_score(metrics)
    session.add(cluster)
    session.commit()


async def run_docket_analysis(
    session: Session, analysis: Analysis, embedder: Embedder, llm: LLM
) -> None:
    """§4.2-4.10 end to end for `mode="docket"`: normalize -> embed -> cluster -> measure
    -> ai_score -> aggregate -> agent, writing an `AnalysisStep` row per stage. Only one
    analysis runs at a time process-wide (`_pipeline_lock`)."""
    async with _pipeline_lock:
        settings = get_settings()
        analysis.status = "running"
        session.add(analysis)
        session.commit()

        try:
            with _step(session, analysis, "normalize") as step:
                documents = session.exec(
                    select(Document).where(Document.docket_id == analysis.docket_id)
                ).all()
                eligible = [d for d in documents if d.word_count >= settings.MIN_WORDS]
                step.detail = f"{len(eligible)} of {len(documents)} documents eligible"

            with _step(session, analysis, "embed") as step:
                texts_by_hash = {d.text_hash: d.text for d in eligible}
                vectors_by_hash = await embed_texts(session, embedder, texts_by_hash)
                step.detail = f"{len(vectors_by_hash)} unique texts embedded"

            with _step(session, analysis, "cluster") as step:
                scored_docs = [d for d in eligible if d.text_hash in vectors_by_hash]
                if scored_docs:
                    matrix = np.stack([vectors_by_hash[d.text_hash] for d in scored_docs])
                    families, similarity = build_families(
                        matrix, settings.SIM_EDGE, settings.SIM_MEMBER, settings.MIN_FAMILY
                    )
                else:
                    families, similarity = [], np.zeros((0, 0))
                step.detail = f"{len(families)} families found"

            with _step(session, analysis, "measure") as step:
                clusters = [
                    await _store_family_as_cluster(
                        session, settings, analysis, scored_docs, family, similarity
                    )
                    for family in families
                ]
                step.detail = f"{len(clusters)} clusters stored"

            with _step(session, analysis, "ai_score") as step:
                for cluster in clusters:
                    await _score_and_aggregate_cluster(session, settings, llm, cluster)
                step.detail = f"{len(clusters)} clusters scored"

            with _step(session, analysis, "aggregate") as step:
                step.detail = "campaign_score finalised with ai_agg"

            with _step(session, analysis, "agent") as step:
                ranked = sorted(clusters, key=lambda c: -c.campaign_score)
                for cluster in ranked[: settings.AGENT_MAX_FAMILIES]:
                    await review_family(session, llm, cluster, analysis.docket_id)
                step.detail = f"{min(len(clusters), settings.AGENT_MAX_FAMILIES)} families reviewed"

            analysis.summary = await _generate_docket_summary(llm, clusters)
            analysis.status = "done"
        except Exception as exc:  # noqa: BLE001 - reported visibly on the Analysis
            analysis.status = "failed"
            analysis.error = str(exc)
        finally:
            analysis.finished_at = datetime.now(timezone.utc)
            analysis.llm_calls = llm.call_count
            analysis.embed_calls = getattr(embedder, "call_count", 0)
            session.add(analysis)
            session.commit()


async def run_text_check(
    session: Session, analysis: Analysis, embedder: Embedder, llm: LLM
) -> None:
    """§4.10 single-comment check: embed the pasted text, find neighbours among the
    docket's cached vectors, and either report "no family found" (fewer than 2
    neighbours) or build a temporary family from the neighbours and run §4.5-4.9 on it."""
    async with _pipeline_lock:
        settings = get_settings()
        analysis.status = "running"
        session.add(analysis)
        session.commit()

        try:
            with _step(session, analysis, "normalize") as step:
                normalized = normalize_for_hash(analysis.input_text or "")
                target_hash = text_hash(normalized)
                step.detail = "target text normalised"

            with _step(session, analysis, "embed") as step:
                vectors = await embed_texts(
                    session, embedder, {target_hash: analysis.input_text or ""}
                )
                target_vector = vectors[target_hash]
                step.detail = "target text embedded"

            with _step(session, analysis, "cluster") as step:
                docket_docs = session.exec(
                    select(Document).where(Document.docket_id == analysis.docket_id)
                ).all()
                candidate_docs: list[Document] = []
                candidate_vectors: list[np.ndarray] = []
                for doc in docket_docs:
                    cache = session.get(EmbeddingCache, (doc.text_hash, embedder.model))
                    if cache is not None:
                        candidate_docs.append(doc)
                        candidate_vectors.append(np.frombuffer(cache.vector, dtype=np.float32))

                neighbors = (
                    nearest(
                        target_vector, np.stack(candidate_vectors), k=10, min_sim=settings.SIM_MEMBER
                    )
                    if candidate_vectors
                    else []
                )
                step.detail = f"{len(neighbors)} neighbours >= SIM_MEMBER"

            if len(neighbors) < 2:
                _skip_remaining_steps(
                    session,
                    analysis,
                    ["measure", "ai_score", "aggregate", "agent"],
                    "fewer than 2 neighbours",
                )
                analysis.summary = "No family found."
                analysis.status = "done"
                return

            with _step(session, analysis, "measure") as step:
                neighbor_docs = [candidate_docs[n.index] for n in neighbors]
                medoid_doc = neighbor_docs[0]
                medoid_vector = candidate_vectors[neighbors[0].index]
                family_members = [
                    FamilyMember(
                        sim_to_medoid=(
                            1.0
                            if doc.id == medoid_doc.id
                            else float(np.dot(candidate_vectors[n.index], medoid_vector))
                        ),
                        text=doc.text,
                        text_hash=doc.text_hash,
                        submitter_hash=doc.submitter_hash,
                        is_anonymous=_is_anonymous(doc),
                        posted_at=doc.posted_at,
                    )
                    for n, doc in zip(neighbors, neighbor_docs, strict=True)
                ]
                metrics = compute_metrics(family_members, family_members[0], ai_agg=0.0)
                prelim_type = preliminary_type(metrics, settings.MIN_CAMPAIGN)

                cluster = Cluster(
                    analysis_id=analysis.id,
                    medoid_document_id=medoid_doc.id,
                    size=metrics.size,
                    metrics=_metrics_to_dict(metrics),
                    campaign_score=campaign_score(metrics),
                    preliminary_type=prelim_type,
                )
                session.add(cluster)
                session.commit()
                session.refresh(cluster)

                medoid_shingles = word_shingles(medoid_doc.text)
                for n, doc in zip(neighbors, neighbor_docs, strict=True):
                    session.add(
                        ClusterMember(
                            cluster_id=cluster.id,
                            document_id=doc.id,
                            sim_to_medoid=n.similarity if doc.id != medoid_doc.id else 1.0,
                            lex_to_medoid=jaccard(word_shingles(doc.text), medoid_shingles),
                            is_medoid=(doc.id == medoid_doc.id),
                        )
                    )
                session.commit()
                step.detail = f"1 ad-hoc family, size={metrics.size}"

            with _step(session, analysis, "ai_score") as step:
                sample_items = [(target_hash, analysis.input_text or "")] + [
                    (m.text_hash, m.text) for m in family_members[: settings.AI_SAMPLE_PER_FAMILY]
                ]
                scores = await score_members(session, llm, sample_items)
                members = session.exec(
                    select(ClusterMember).where(ClusterMember.cluster_id == cluster.id)
                ).all()
                doc_by_id = {d.id: d for d in neighbor_docs}
                for member in members:
                    doc = doc_by_id[member.document_id]
                    if doc.text_hash in scores:
                        member.ai_score = scores[doc.text_hash][0]
                        session.add(member)
                session.commit()
                step.detail = "target and neighbours scored"

            with _step(session, analysis, "aggregate") as step:
                target_score = scores.get(target_hash, (0.0, ""))[0]
                neighbor_scores = [
                    scores[fm.text_hash][0] for fm in family_members if fm.text_hash in scores
                ]
                neighbor_sims = [
                    fm.sim_to_medoid for fm in family_members if fm.text_hash in scores
                ]
                agg = single_comment_agg(target_score, neighbor_scores, neighbor_sims)

                metrics_dict = dict(cluster.metrics)
                metrics_dict["ai_agg"] = agg
                updated_metrics = CampaignMetrics(
                    size=metrics.size,
                    mean_sem=metrics.mean_sem,
                    mean_lex=metrics.mean_lex,
                    reword_index=metrics.reword_index,
                    exact_dup_share=metrics.exact_dup_share,
                    burst_24h=metrics.burst_24h,
                    name_diversity=metrics.name_diversity,
                    anon_share=metrics.anon_share,
                    ai_agg=agg,
                )
                cluster.metrics = metrics_dict
                cluster.campaign_score = campaign_score(updated_metrics)
                session.add(cluster)
                session.commit()
                step.detail = "campaign_score finalised with ai_agg"

            with _step(session, analysis, "agent") as step:
                await review_family(session, llm, cluster, analysis.docket_id)
                step.detail = "family reviewed"

            analysis.status = "done"
        except Exception as exc:  # noqa: BLE001 - reported visibly on the Analysis
            analysis.status = "failed"
            analysis.error = str(exc)
        finally:
            analysis.finished_at = datetime.now(timezone.utc)
            analysis.llm_calls = llm.call_count
            analysis.embed_calls = getattr(embedder, "call_count", 0)
            session.add(analysis)
            session.commit()
