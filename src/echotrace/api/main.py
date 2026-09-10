"""EchoTrace API: wires the real retrieval/detection/aggregation/agent
pipeline to HTTP endpoints for the frontend, behind real authentication.

Detection/agent endpoints depend on the fine-tuned RoBERTa checkpoint and
an ANTHROPIC_API_KEY respectively — until those are in place, this returns
a clear 503 rather than crashing or fabricating a result.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from echotrace.aggregation.aggregate import aggregate
from echotrace.auth.security import AuthError, authenticate_user, decode_access_token, register_user
from echotrace.db import get_connection
from echotrace.retrieval.search import find_near_duplicates

app = FastAPI(title="EchoTrace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8501"],
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
    text: str
    article_id: str | None = None
    k: int = 5


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
def login(req: AuthRequest):
    conn = get_connection()
    try:
        token = authenticate_user(conn, req.username, req.password)
    except AuthError as e:
        raise HTTPException(401, str(e))
    finally:
        conn.close()
    return TokenResponse(access_token=token, username=req.username.strip())


@app.get("/api/articles/sample")
def sample_articles(limit: int = 20, user: str = Depends(get_current_user)):
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
def get_article(article_id: str, user: str = Depends(get_current_user)):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, text, cluster_id, source FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "article not found")
    return {"id": row[0], "text": row[1], "cluster_id": row[2], "source": row[3]}


@app.get("/api/mdaigt/sample")
def mdaigt_sample(limit: int = 20, split: str = "test", user: str = Depends(get_current_user)):
    """Real M-DAIGT samples with their real human/machine label, so the
    detector can be demonstrated against genuine AI-authored text — the
    NEWS-COPY corpus used for /api/articles/sample is entirely real
    historical (pre-LLM) newspaper text, so it can never show a positive
    AI-text result; this is the real dataset that can."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, substr(text, 1, 240) AS preview, label FROM articles
        WHERE source = 'mdaigt-task1-news' AND split = ?
        ORDER BY RANDOM() LIMIT ?
        """,
        (split, limit),
    ).fetchall()
    conn.close()
    return [{"id": r[0], "preview": r[1], "label": r[2]} for r in rows]


def _try_score(text: str) -> float | None:
    try:
        from echotrace.detection.detector import score_text

        return score_text(text)
    except FileNotFoundError:
        return None


@app.post("/api/detect")
def detect(req: InvestigateRequest, user: str = Depends(get_current_user)):
    """Single-instance detection only (no retrieval/aggregation) — used to
    demonstrate the detector directly against labeled M-DAIGT examples."""
    score = _try_score(req.text)
    if score is None:
        return {
            "model_available": False,
            "message": "Detection scores unavailable — fine-tuned RoBERTa checkpoint not found.",
        }
    return {"model_available": True, "score": score}


@app.post("/api/investigate")
def investigate(req: InvestigateRequest, user: str = Depends(get_current_user)):
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
def verdict(req: InvestigateRequest, user: str = Depends(get_current_user)):
    """Full agentic verdict — requires both the detector checkpoint and
    ANTHROPIC_API_KEY."""
    try:
        from echotrace.agent.decision import run_agent

        return run_agent(req.text, req.article_id)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
