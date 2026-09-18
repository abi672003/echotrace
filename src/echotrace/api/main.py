"""EchoTrace API: wires the real retrieval/detection/aggregation/agent
pipeline to HTTP endpoints for the frontend, behind real authentication.

Retrieval is live: every investigation searches the real web (GDELT DOC
2.0 API + article fetch/extract, see retrieval/live_search.py) rather than
a static pre-embedded corpus. Detection/agent endpoints still depend on the
fine-tuned RoBERTa checkpoint and an ANTHROPIC_API_KEY respectively — until
those are in place, this returns a clear 503/degraded response rather than
crashing or fabricating a result.

The static NEWS-COPY/M-DAIGT dataset endpoints (`/api/articles/*`,
`/api/mdaigt/sample`, `/api/detect`) are kept as the "Detector Sandbox"
feature — the only way to demo the detector against ground-truth-labeled
text, since live web articles have no known label.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env")

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, select, text

from echotrace.aggregation.aggregate import aggregate
from echotrace.auth.security import (
    AuthError,
    authenticate_user,
    check_rate_limit,
    clear_failed_attempts,
    decode_access_token,
    get_user_id,
    record_failed_attempt,
    register_user,
)
from echotrace.db import get_connection, investigations
from echotrace.detection.detector import score_text
from echotrace.retrieval.fetch import DEFAULT_TIMEOUT_SECONDS, fetch_and_extract
from echotrace.retrieval.live_search import find_live_near_duplicates

app = FastAPI(title="EchoTrace API")

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:8501"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if credentials is None:
        raise HTTPException(401, "Not authenticated — missing bearer token.")
    try:
        return decode_access_token(credentials.credentials)
    except AuthError as e:
        raise HTTPException(401, str(e))


class InvestigateRequest(BaseModel):
    text: str | None = None
    url: str | None = None
    k: int = Field(default=5, ge=1, le=15)
    timespan: str = "7d"

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if bool(self.text and self.text.strip()) == bool(self.url and self.url.strip()):
            raise ValueError("Provide exactly one of `text` or `url`.")
        return self


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=TokenResponse)
def register(req: AuthRequest):
    conn = get_connection()
    try:
        register_user(conn, req.username, req.password)
        token = authenticate_user(conn, req.username, req.password)
    except AuthError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()
    return TokenResponse(access_token=token, username=req.username.strip())


@app.post("/api/auth/login", response_model=TokenResponse)
def login(req: AuthRequest, request: Request):
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{req.username.strip().lower()}"

    try:
        check_rate_limit(rate_key)
    except AuthError as e:
        raise HTTPException(429, str(e))

    conn = get_connection()
    try:
        token = authenticate_user(conn, req.username, req.password)
    except AuthError as e:
        record_failed_attempt(rate_key)
        raise HTTPException(401, str(e))
    finally:
        conn.close()

    clear_failed_attempts(rate_key)
    return TokenResponse(access_token=token, username=req.username.strip())


# ---------------------------------------------------------------------------
# Detector Sandbox — real, labeled example articles (NEWS-COPY: genuinely
# human, pre-LLM; M-DAIGT: real human/machine ground truth) for demoing the
# detector against known-correct answers, since live web articles carry no
# ground-truth label of their own.
# ---------------------------------------------------------------------------


@app.get("/api/articles/sample")
def sample_articles(limit: int = 20, user: str = Depends(get_current_user)):
    """Real historical NEWS-COPY articles from clusters with 2+ members."""
    conn = get_connection()
    rows = conn.execute(
        text(
            """
            SELECT id, substr(text, 1, 240) AS preview, cluster_id FROM articles
            WHERE source = 'news-copy-eval-clusters'
            AND cluster_id IN (
                SELECT cluster_id FROM articles WHERE source='news-copy-eval-clusters'
                GROUP BY cluster_id HAVING COUNT(*) >= 2
            )
            ORDER BY RANDOM() LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()
    conn.close()
    return [{"id": r[0], "preview": r[1], "cluster_id": r[2]} for r in rows]


@app.get("/api/articles/{article_id}")
def get_article(article_id: str, user: str = Depends(get_current_user)):
    conn = get_connection()
    row = conn.execute(
        text("SELECT id, text, cluster_id, source FROM articles WHERE id = :id"), {"id": article_id}
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "article not found")
    return {"id": row[0], "text": row[1], "cluster_id": row[2], "source": row[3]}


@app.get("/api/mdaigt/sample")
def mdaigt_sample(limit: int = 20, split: str = "test", user: str = Depends(get_current_user)):
    """Real M-DAIGT samples with their real human/machine label, so the
    detector can be demonstrated against genuine AI-authored text."""
    conn = get_connection()
    rows = conn.execute(
        text(
            """
            SELECT id, substr(text, 1, 240) AS preview, label FROM articles
            WHERE source = 'mdaigt-task1-news' AND split = :split
            ORDER BY RANDOM() LIMIT :limit
            """
        ),
        {"split": split, "limit": limit},
    ).fetchall()
    conn.close()
    return [{"id": r[0], "preview": r[1], "label": r[2]} for r in rows]


def _try_score(target_text: str) -> float | None:
    try:
        return score_text(target_text)
    except FileNotFoundError:
        return None


@app.post("/api/detect")
def detect(req: InvestigateRequest, user: str = Depends(get_current_user)):
    """Single-instance detection only (no retrieval/aggregation) — used to
    demonstrate the detector directly against labeled M-DAIGT examples."""
    score = _try_score(req.text or "")
    if score is None:
        return {
            "model_available": False,
            "message": "Detection scores unavailable — fine-tuned RoBERTa checkpoint not found.",
        }
    return {"model_available": True, "score": score}


# ---------------------------------------------------------------------------
# Live investigation — the production pipeline. Paste raw text or a URL;
# either way, near-duplicate evidence is gathered live from the web.
# ---------------------------------------------------------------------------


async def _resolve_target(req: InvestigateRequest) -> tuple[str, str | None]:
    """Returns (target_text, target_url). Fetches `req.url` server-side
    when given; otherwise uses `req.text` directly (target_url stays None)."""
    if req.url:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            fetched = await fetch_and_extract(req.url, client)
        if fetched is None:
            raise HTTPException(
                422,
                "Could not fetch or extract article text from that URL "
                "(blocked by robots.txt, paywalled, timed out, or not parseable as an article).",
            )
        return fetched["text"], req.url
    return req.text, None  # validated non-empty by InvestigateRequest


async def _score_and_aggregate(target_text: str, duplicates_raw: list[dict]) -> dict:
    target_score = None
    try:
        target_score = await asyncio.to_thread(score_text, target_text)
    except FileNotFoundError:
        pass
    model_available = target_score is not None

    if not model_available:
        return {
            "model_available": False,
            "message": "Detection scores unavailable — fine-tuned RoBERTa checkpoint not found. "
            "Run notebooks/finetune_roberta_mdaigt.ipynb and drop the result into models/echotrace-detector/.",
            "evidence": [
                {
                    "id": d["id"],
                    "similarity": d["similarity"],
                    "score": None,
                    "title": d.get("title"),
                    "domain": d.get("domain"),
                }
                for d in duplicates_raw
            ],
        }

    async def _score(dup: dict) -> dict:
        try:
            s = await asyncio.to_thread(score_text, dup["text"])
        except FileNotFoundError:
            s = None
        return {**dup, "score": s}

    scored = await asyncio.gather(*(_score(d) for d in duplicates_raw))
    result = aggregate(target_score, list(scored))
    payload = {"model_available": True, **result.to_dict()}

    meta_by_id = {d["id"]: d for d in duplicates_raw}
    for e in payload["evidence"]:
        meta = meta_by_id.get(e["id"], {})
        e["title"] = meta.get("title")
        e["domain"] = meta.get("domain")
    return payload


def _verdict_for(payload: dict) -> str | None:
    if not payload.get("model_available"):
        return None
    return "ai_reworded_copy" if payload["aggregated_score"] >= 0.5 else "independent_reporting"


def _persist_investigation(
    user_id: int, target_text: str, target_url: str | None, verdict: str | None, payload: dict
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            investigations.insert().values(
                user_id=user_id,
                target_url=target_url,
                target_text=target_text[:20000],
                verdict=verdict,
                aggregated_score=payload.get("aggregated_score"),
                single_instance_score=payload.get("single_instance_score"),
                evidence_json=json.dumps(payload.get("evidence", [])),
            )
        )
        conn.commit()
    finally:
        conn.close()


async def _run_investigation(
    user_id: int | None, target_text: str, target_url: str | None, k: int, timespan: str
) -> dict:
    duplicates_raw = await find_live_near_duplicates(target_text, k=k, timespan=timespan, exclude_url=target_url)
    payload = await _score_and_aggregate(target_text, duplicates_raw)
    verdict = _verdict_for(payload)
    payload["verdict"] = verdict
    if user_id is not None:
        _persist_investigation(user_id, target_text, target_url, verdict, payload)
    return payload


@app.post("/api/investigate")
async def investigate(req: InvestigateRequest, user: str = Depends(get_current_user)):
    target_text, target_url = await _resolve_target(req)
    conn = get_connection()
    try:
        user_id = get_user_id(conn, user)
    finally:
        conn.close()
    return await _run_investigation(user_id, target_text, target_url, req.k, req.timespan)


async def _investigation_event_stream(
    user_id: int | None, target_text: str, target_url: str | None, k: int, timespan: str
):
    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    try:
        yield sse("progress", {"stage": "searching", "message": "Searching the live web for near-duplicate coverage..."})
        duplicates_raw = await find_live_near_duplicates(target_text, k=k, timespan=timespan, exclude_url=target_url)

        yield sse(
            "progress",
            {
                "stage": "scoring",
                "message": f"Found {len(duplicates_raw)} candidate(s) — running the detector...",
                "count": len(duplicates_raw),
            },
        )
        payload = await _score_and_aggregate(target_text, duplicates_raw)

        yield sse("progress", {"stage": "aggregating", "message": "Combining evidence across duplicates..."})
        verdict = _verdict_for(payload)
        payload["verdict"] = verdict
        if user_id is not None:
            _persist_investigation(user_id, target_text, target_url, verdict, payload)

        yield sse("done", payload)
    except Exception as e:  # keep the stream alive long enough to tell the client what happened
        yield sse("error", {"message": str(e)})


@app.post("/api/investigate/stream")
async def investigate_stream(req: InvestigateRequest, user: str = Depends(get_current_user)):
    target_text, target_url = await _resolve_target(req)
    conn = get_connection()
    try:
        user_id = get_user_id(conn, user)
    finally:
        conn.close()
    return StreamingResponse(
        _investigation_event_stream(user_id, target_text, target_url, req.k, req.timespan),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/investigations")
def list_investigations(limit: int = 20, user: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        user_id = get_user_id(conn, user)
        if user_id is None:
            return []
        rows = conn.execute(
            select(investigations)
            .where(investigations.c.user_id == user_id)
            .order_by(desc(investigations.c.id))
            .limit(min(max(limit, 1), 100))
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r.id,
            "target_url": r.target_url,
            "target_text_preview": (r.target_text or "")[:200],
            "verdict": r.verdict,
            "aggregated_score": r.aggregated_score,
            "single_instance_score": r.single_instance_score,
            "evidence": json.loads(r.evidence_json) if r.evidence_json else [],
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.post("/api/verdict")
async def verdict(req: InvestigateRequest, user: str = Depends(get_current_user)):
    """Full agentic verdict — requires both the detector checkpoint and
    ANTHROPIC_API_KEY."""
    target_text, target_url = await _resolve_target(req)
    try:
        from echotrace.agent.decision import run_agent

        return await run_agent(target_text, target_url)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
