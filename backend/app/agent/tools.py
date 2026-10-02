import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlmodel import Session, select

from app.agent.prompts import ToolSpec
from app.config import get_settings
from app.models import Cluster, ClusterMember, Document, EmbeddingCache
from app.services.compare import lexical_similarity, semantic_similarity, shared_spans
from app.services.similarity import nearest


@dataclass
class ToolContext:
    session: Session
    cluster: Cluster
    docket_id: str


def _members_and_docs(ctx: ToolContext) -> tuple[list[ClusterMember], dict[int, Document]]:
    members = ctx.session.exec(
        select(ClusterMember).where(ClusterMember.cluster_id == ctx.cluster.id)
    ).all()
    doc_ids = [m.document_id for m in members]
    documents = ctx.session.exec(select(Document).where(Document.id.in_(doc_ids))).all()
    return list(members), {d.id: d for d in documents}


def family_summary(ctx: ToolContext) -> dict:
    members, docs = _members_and_docs(ctx)
    posted_dates = [docs[m.document_id].posted_at for m in members if docs[m.document_id].posted_at]
    return {
        "size": ctx.cluster.size,
        "preliminary_type": ctx.cluster.preliminary_type,
        "metrics": ctx.cluster.metrics,
        "date_range": {
            "earliest": min(posted_dates).isoformat() if posted_dates else None,
            "latest": max(posted_dates).isoformat() if posted_dates else None,
        },
    }


def list_members(ctx: ToolContext, limit: int = 10, offset: int = 0, order: str = "sim") -> list[dict]:
    members, docs = _members_and_docs(ctx)
    if order == "time":
        members.sort(key=lambda m: docs[m.document_id].posted_at or datetime.min)
    elif order == "ai":
        members.sort(key=lambda m: -(m.ai_score if m.ai_score is not None else 0.0))
    else:
        members.sort(key=lambda m: -m.sim_to_medoid)

    capped_limit = min(limit, 10)
    page = members[offset : offset + capped_limit]
    result = []
    for member in page:
        doc = docs[member.document_id]
        result.append(
            {
                "id": doc.id,
                "excerpt": doc.text[:300],
                "posted_at": doc.posted_at.isoformat() if doc.posted_at else None,
                "submitter_hash_prefix": doc.submitter_hash[:8],
                "sim": member.sim_to_medoid,
                "lex": member.lex_to_medoid,
                "ai_score": member.ai_score,
            }
        )
    return result


def compare(ctx: ToolContext, doc_a: int, doc_b: int) -> dict:
    document_a = ctx.session.get(Document, doc_a)
    document_b = ctx.session.get(Document, doc_b)
    if document_a is None or document_b is None:
        return {"error": "One or both document ids were not found."}

    settings = get_settings()
    sem = semantic_similarity(
        ctx.session, settings.GEMINI_EMBED_MODEL, document_a.text_hash, document_b.text_hash
    )
    lex = lexical_similarity(document_a.text, document_b.text)
    spans = shared_spans(document_a.text, document_b.text)
    spans.sort(key=lambda s: -(s["a_end"] - s["a_start"]))
    phrases = [span["text"] for span in spans[:5]]
    return {"doc_a": doc_a, "doc_b": doc_b, "sem": sem, "lex": lex, "shared_phrases": phrases}


def search_similar(ctx: ToolContext, doc_id: int, k: int = 10, min_sim: float = 0.75) -> list[dict]:
    document = ctx.session.get(Document, doc_id)
    if document is None:
        return []
    settings = get_settings()
    query_cache = ctx.session.get(EmbeddingCache, (document.text_hash, settings.GEMINI_EMBED_MODEL))
    if query_cache is None:
        return []
    query_vector = np.frombuffer(query_cache.vector, dtype=np.float32)

    family_document_ids = {
        m.document_id
        for m in ctx.session.exec(
            select(ClusterMember).where(ClusterMember.cluster_id == ctx.cluster.id)
        ).all()
    }
    docket_documents = ctx.session.exec(
        select(Document).where(Document.docket_id == ctx.docket_id)
    ).all()
    candidates = [d for d in docket_documents if d.id not in family_document_ids]

    vectors = []
    valid_docs = []
    for candidate in candidates:
        cache = ctx.session.get(EmbeddingCache, (candidate.text_hash, settings.GEMINI_EMBED_MODEL))
        if cache is not None:
            vectors.append(np.frombuffer(cache.vector, dtype=np.float32))
            valid_docs.append(candidate)
    if not vectors:
        return []

    neighbors = nearest(query_vector, np.stack(vectors), min(k, 10), max(min_sim, 0.75))
    return [
        {
            "id": valid_docs[n.index].id,
            "excerpt": valid_docs[n.index].text[:300],
            "sim": n.similarity,
        }
        for n in neighbors
    ]


def timeline(ctx: ToolContext) -> dict:
    members, docs = _members_and_docs(ctx)
    buckets: dict[str, int] = {}
    for member in members:
        posted_at = docs[member.document_id].posted_at
        if posted_at is None:
            continue
        hour = posted_at.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets[hour] = buckets.get(hour, 0) + 1
    return {"buckets": [{"hour": hour, "count": count} for hour, count in sorted(buckets.items())]}


TOOL_FUNCTIONS = {
    "family_summary": family_summary,
    "list_members": list_members,
    "compare": compare,
    "search_similar": search_similar,
    "timeline": timeline,
}

TOOL_SPECS = [
    ToolSpec(
        name="family_summary",
        description="Metrics, preliminary type, size, and date range for this family.",
        args={},
    ),
    ToolSpec(
        name="list_members",
        description="List family members with excerpts and per-member metrics.",
        args={"limit": "int <=10", "offset": "int", "order": '"sim"|"time"|"ai"'},
    ),
    ToolSpec(
        name="compare",
        description="Semantic/lexical similarity and shared phrases between two comments.",
        args={"doc_a": "int", "doc_b": "int"},
    ),
    ToolSpec(
        name="search_similar",
        description="Nearest docket comments outside this family.",
        args={"doc_id": "int", "k": "int <=10", "min_sim": "float >=0.75"},
    ),
    ToolSpec(
        name="timeline",
        description="Member counts per hour bucket.",
        args={},
    ),
    ToolSpec(
        name="submit_verdict",
        description="Submit the final verdict and end the review.",
        args={
            "type": "coordinated_paraphrase_campaign|form_letter|organic_agreement|insufficient_evidence",
            "confidence": '"low"|"medium"|"high"',
            "rationale": "<=120 words",
            "cited_document_ids": "2 to 8 ids",
            "recommend_review": "bool",
        },
    ),
]


def truncate_observation(observation: dict, max_bytes: int = 4096) -> dict:
    encoded = json.dumps(observation)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return observation
    truncated_text = encoded.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return {"truncated": True, "preview": truncated_text}
