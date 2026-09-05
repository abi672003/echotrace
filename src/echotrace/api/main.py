"""EchoTrace API: wires the real retrieval/detection/aggregation/agent
pipeline to HTTP endpoints for the frontend.

Detection/agent endpoints depend on the fine-tuned RoBERTa checkpoint and
an ANTHROPIC_API_KEY respectively — until those are in place, this returns
a clear 503 rather than crashing or fabricating a result.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from echotrace.aggregation.aggregate import aggregate
from echotrace.db import get_connection
from echotrace.retrieval.search import find_near_duplicates

app = FastAPI(title="EchoTrace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    text: str
    article_id: str | None = None
    k: int = 5


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/articles/sample")
def sample_articles(limit: int = 20):
    """Real articles from clusters with 2+ members, for the case-file
    browser to pick an investigation target from."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, substr(text, 1, 240) AS preview, cluster_id FROM articles
        WHERE source = 'news-copy-eval-clusters'
        AND cluster_id IN (
            SELECT cluster_id FROM articles WHERE source='news-copy-eval-clusters'
            GROUP BY cluster_id HAVING COUNT(*) >= 2
        )
        ORDER BY RANDOM() LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [{"id": r[0], "preview": r[1], "cluster_id": r[2]} for r in rows]


@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, text, cluster_id, source FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "article not found")
    return {"id": row[0], "text": row[1], "cluster_id": row[2], "source": row[3]}


def _try_score(text: str) -> float | None:
    try:
        from echotrace.detection.detector import score_text

        return score_text(text)
    except FileNotFoundError:
        return None


@app.post("/api/investigate")
def investigate(req: InvestigateRequest):
    """Real pipeline run: retrieval (always available) + detection (only if
    the fine-tuned checkpoint is present) + aggregation."""
    duplicates_raw = find_near_duplicates(req.text, k=req.k, exclude_id=req.article_id)

    target_score = _try_score(req.text)
    model_available = target_score is not None

    if model_available:
        duplicates = [
            {"id": d["id"], "similarity": d["similarity"], "score": _try_score(d["text"])}
            for d in duplicates_raw
        ]
        result = aggregate(target_score, duplicates)
        return {"model_available": True, **result.to_dict()}

    return {
        "model_available": False,
        "message": "Detection scores unavailable — fine-tuned RoBERTa checkpoint not found. "
        "Run notebooks/finetune_roberta_mdaigt.ipynb and drop the result into models/echotrace-detector/.",
        "evidence": [{"id": d["id"], "similarity": d["similarity"], "score": None} for d in duplicates_raw],
    }


@app.post("/api/verdict")
def verdict(req: InvestigateRequest):
    """Full agentic verdict — requires both the detector checkpoint and
    ANTHROPIC_API_KEY."""
    try:
        from echotrace.agent.decision import run_agent

        return run_agent(req.text, req.article_id)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
