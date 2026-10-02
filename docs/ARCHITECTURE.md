# EchoTrace — Architecture

Read `PRD.md` first. This document is the technical source of truth; if code and this file disagree, fix one of them in the same change.

---

## 1. Tech stack (all free, no Docker)

| Layer | Choice | Why |
|---|---|---|
| Frontend | **React 18 + Vite + TypeScript**, Tailwind CSS v4 (`@tailwindcss/vite`), React Router, TanStack Query, **@xyflow/react** (evidence board) | Fast local dev on Windows, static build deploys free anywhere |
| Backend | **Python 3.11 + FastAPI + Uvicorn**, SQLModel (SQLAlchemy), Pydantic v2, httpx, numpy | Async API, typed schemas, numpy is enough for similarity at MVP scale |
| Database | **SQLite** locally (`echotrace.db`); **Supabase Postgres** free tier for the deployed demo, same SQLModel code via `DATABASE_URL` | Zero setup locally; no ephemeral-disk problems when deployed |
| Vector search | **numpy brute-force cosine** over float32 vectors stored as BLOB/BYTEA | A docket has hundreds to low thousands of comments, which brute force handles in milliseconds; no extra service to install |
| Embeddings | **Gemini API embeddings** (`gemini-embedding-001`, 768 dims via output dimensionality) | Free tier, batch endpoint, no Hugging Face |
| LLM (agent + AI-style scoring) | **Groq** primary (e.g., `openai/gpt-oss-120b`), **Gemini Flash** fallback | Both free tiers; provider-agnostic JSON protocol so either works |
| Data source | **Regulations.gov API v4** with a free api.data.gov key | Real, live public comments |
| Background work | FastAPI `BackgroundTasks` + a single in-process lock | No Redis/Celery needed for one user |
| Tests | pytest + a `FakeLLM`/`FakeEmbedder`; Vitest for a few frontend utils | Tests never hit the network |
| Hosting (optional) | Backend: **Render** free web service (native Python runtime); Frontend: **Vercel** or **Netlify** static; DB: **Supabase** | All native builds, no containers |

> Model names and free-tier limits change. Every model name lives in `.env`, never in code. Verify current names in Google AI Studio and the Groq console before Phase 3.

**Corporate network warning:** Hugging Face is blocked on the dev laptop; other hosts might be too. `scripts/check_connectivity.py` (Phase 1) must pass for `api.regulations.gov`, `generativelanguage.googleapis.com`, and `api.groq.com` before building on them.

---

## 2. System overview

```
 ┌──────────────────────────── Browser ─────────────────────────────┐
 │ React (Vite)  Dockets · Analysis/Evidence board · Check comment   │
 └───────────────▲──────────────────────────────────────────────────┘
                 │ REST /api/v1 (JSON, polling for progress)
 ┌───────────────┴──────────────── FastAPI ─────────────────────────┐
 │ routers/        services/                        agent/           │
 │  dockets   ──►  regulations_client (source)      runner (loop)    │
 │  analyses  ──►  pipeline ─► normalize            tools            │
 │  clusters                  ─► embeddings  ──► Gemini embed API    │
 │  documents                 ─► similarity  (numpy)                 │
 │                            ─► features   (campaign shape)         │
 │                            ─► ai_scoring ──► llm ──► Groq/Gemini  │
 │                            ─► aggregation                          │
 │                            ─► agent.runner ──► llm                 │
 └───────────────┬──────────────────────────────────────────────────┘
                 │ SQLModel
          SQLite (local) / Supabase Postgres (deployed)
```

---

## 3. Repository layout

```
echotrace/
├── AGENTS.md
├── docs/  PRD.md  ARCHITECTURE.md  DESIGN_SYSTEM.md  TASKS.md
├── data/samples/            # real cached Regulations.gov responses (committed)
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py          # app factory, CORS, routers, startup create_all
│   │   ├── config.py        # pydantic-settings; all thresholds + model names
│   │   ├── db.py            # engine, session dependency
│   │   ├── models.py        # SQLModel tables (section 5)
│   │   ├── schemas.py       # API request/response models (section 6)
│   │   ├── security.py      # X-Admin-Token check for write routes
│   │   ├── routers/  health.py dockets.py analyses.py clusters.py documents.py
│   │   ├── services/
│   │   │   ├── sources/base.py            # SourceAdapter protocol
│   │   │   ├── sources/regulations_gov.py # API client + ingest
│   │   │   ├── sources/sample_loader.py
│   │   │   ├── normalize.py   embeddings.py   llm.py
│   │   │   ├── similarity.py  features.py     ai_scoring.py
│   │   │   ├── aggregation.py compare.py      pipeline.py
│   │   │   └── ratelimit.py   # token-bucket + retry/backoff helper
│   │   └── agent/  prompts.py tools.py runner.py citations.py
│   ├── scripts/  check_connectivity.py fetch_sample.py calibrate.py export_reviews.py
│   └── tests/
└── frontend/
    ├── package.json  vite.config.ts  index.html
    └── src/
        ├── main.tsx  App.tsx  styles/tokens.css
        ├── api/client.ts  api/types.ts  api/hooks.ts
        ├── pages/  DocketsPage.tsx DocketPage.tsx AnalysisPage.tsx CheckPage.tsx
        └── components/  (see DESIGN_SYSTEM.md §5)
```

---

## 4. The pipeline (algorithms)

All thresholds below are **starting values** in `config.py`; `scripts/calibrate.py` prints similarity distributions on a real docket so they can be tuned.

### 4.1 Ingest (source adapter)
- `GET /v4/comments?filter[docketId]=X&page[size]=250&page[number]=n&sort=postedDate` for the list, then `GET /v4/comments/{id}` per comment for the body text (`attributes.comment`), submitter fields, and posted date. Each detail call costs one request, so ingest is rate-limited to stay under the hourly quota and is **resumable** (skip `external_id`s already stored).
- Skip bodies that are empty or only reference attachments (regex like `see attached`, length < 25 words after normalisation); count them in `docket.skipped_count`.
- `SourceAdapter` protocol: `list_ids(scope)`, `fetch(id) -> RawItem`. Regulations.gov and the sample loader implement it; future sources plug in here.

### 4.2 Normalise
Lowercase copy for hashing only; strip HTML, collapse whitespace, remove boilerplate salutations. `text_hash = sha256(normalised)`. Exact-hash groups are recorded (form-letter evidence) before embedding.

### 4.3 Embed
Batch unique `text_hash`es (up to 100 per request) to Gemini with task type `CLUSTERING`, output dimensionality 768; L2-normalise; cache in `embedding_cache` keyed by `(text_hash, model)`. Never re-embed a cached hash.

### 4.4 Cluster
1. Matrix `S = V @ V.T` (vectors are normalised, so this is cosine).
2. Edges where `S >= SIM_EDGE` (0.86). Union-find → connected components.
3. Chaining guard: pick the **medoid** (member with highest mean similarity to others); drop members with similarity to medoid `< SIM_MEMBER` (0.82) back to singletons.
4. Keep families with `size >= MIN_FAMILY` (3). Singletons are not stored as clusters.

### 4.5 Campaign-shape features (per family, relative to medoid)
| Metric | Definition |
|---|---|
| `size` | members n |
| `mean_sem` | mean cosine to medoid |
| `mean_lex` | mean Jaccard of word 3-gram shingles to medoid |
| `reword_index` | `mean_sem × (1 − mean_lex)` — high means same meaning, different words |
| `exact_dup_share` | share of members in the largest exact-hash group |
| `burst_24h` | max members inside any 24-hour window ÷ n |
| `name_diversity` | distinct submitter-name hashes ÷ n |
| `anon_share` | share with anonymous/empty submitter |
| `ai_agg` | similarity-weighted AI-style score (§4.7) |

### 4.6 AI-style score (LLM, no training)
- Score at most `AI_SAMPLE_PER_FAMILY` (8) members per family, medoid always included, in **one batched LLM call** returning JSON `[{id, score 0–1, reason}]`.
- Cached in `ai_score_cache` by `(text_hash, model)`.
- Shown in the UI as "AI-style signal (unverified)". It is weak evidence by design.

### 4.7 Aggregation (the core idea, kept inspectable)
- Family mode: `ai_agg = Σ(sᵢ·wᵢ) / Σwᵢ`, where `wᵢ` = similarity to medoid (medoid weight 1), over scored members.
- Single-comment mode (target t plus neighbours): `agg = (s_t·1 + Σ sᵢ·simᵢ) / (1 + Σ simᵢ)`.

### 4.8 Campaign score and preliminary type (rule-based)
```
size_norm  = min(1, ln(n) / ln(50))
campaign_score = 0.35·size_norm + 0.25·reword_index + 0.20·burst_24h + 0.20·ai_agg

type =
  form_letter                     if exact_dup_share ≥ 0.5 or mean_lex ≥ 0.6
  coordinated_paraphrase_campaign if n ≥ MIN_CAMPAIGN(5) and reword_index ≥ 0.45
                                     and (burst_24h ≥ 0.5 or name_diversity ≥ 0.8)
  organic_agreement               if reword_index ≥ 0.45 and burst_24h < 0.3
  insufficient_evidence           otherwise
```
**Guard:** `ai_agg` can raise a score but can never on its own move a family into `coordinated_paraphrase_campaign`.

### 4.9 Agent review
Top `AGENT_MAX_FAMILIES` (10) families by `campaign_score` go to the runtime agent (§7), which may confirm or change the preliminary type, sets confidence, and writes the cited rationale. It then writes a short docket-level summary.

### 4.10 Single-comment check
Embed pasted text → cosine against the docket's cached vectors → neighbours with sim ≥ `SIM_MEMBER`. If the neighbours overlap an existing family, report that family; else build a temporary family from the neighbours and run §4.5–4.9 for it. Fewer than 2 neighbours → `insufficient_evidence` / "no family found", regardless of AI-style score.

### 4.11 Quota budget (500-comment docket)
Regulations.gov ≈ 502 requests (ingest once) · Gemini embeddings ≈ 5–6 batch calls · LLM ≈ 10 scoring calls + ≤ 10 × 6 agent steps + 1 summary ≈ 71 calls. `analysis.llm_calls` records the real count. Only one analysis runs at a time.

---

## 5. Data model (SQLModel)

`id` columns are integers unless noted. All timestamps UTC.

```python
class Docket(SQLModel, table=True):
    id: str = Field(primary_key=True)            # e.g. "EPA-HQ-OAR-2021-0317"
    agency_id: str | None
    title: str | None
    source: str                                   # "regulations_gov" | "sample"
    remote_comment_count: int | None
    ingested_count: int = 0
    skipped_count: int = 0
    ingest_status: str = "idle"                   # idle|running|done|partial|failed
    ingest_error: str | None
    last_ingested_at: datetime | None
    created_at: datetime

class Document(SQLModel, table=True):            # one public comment
    id: int = Field(primary_key=True)
    docket_id: str = Field(foreign_key="docket.id", index=True)
    external_id: str = Field(unique=True)         # Regulations.gov comment ID
    title: str | None
    submitter_label: str                           # display name as provided, "Anonymous" if none
    submitter_hash: str                            # sha256(lower(name)) for diversity metrics
    organization: str | None
    text: str
    text_hash: str = Field(index=True)
    word_count: int
    posted_at: datetime | None = Field(index=True)
    url: str | None
    created_at: datetime

class EmbeddingCache(SQLModel, table=True):
    text_hash: str = Field(primary_key=True)
    model: str = Field(primary_key=True)
    dim: int
    vector: bytes                                  # float32, L2-normalised
    created_at: datetime

class AiScoreCache(SQLModel, table=True):
    text_hash: str = Field(primary_key=True)
    model: str = Field(primary_key=True)
    score: float
    reason: str
    created_at: datetime

class Analysis(SQLModel, table=True):
    id: str = Field(primary_key=True)              # uuid4 hex
    mode: str                                      # "docket" | "text"
    docket_id: str = Field(foreign_key="docket.id", index=True)
    input_text: str | None
    status: str = "queued"                          # queued|running|done|failed
    current_step: str | None
    error: str | None
    summary: str | None                             # agent's docket-level summary
    params: dict = Field(sa_column=Column(JSON))    # thresholds + model names used
    llm_calls: int = 0
    embed_calls: int = 0
    created_at: datetime
    finished_at: datetime | None

class AnalysisStep(SQLModel, table=True):
    id: int = Field(primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    name: str          # normalize|embed|cluster|measure|ai_score|aggregate|agent
    status: str        # pending|running|done|failed|skipped
    detail: str | None
    started_at: datetime | None
    finished_at: datetime | None

class Cluster(SQLModel, table=True):               # a "family"
    id: int = Field(primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    medoid_document_id: int = Field(foreign_key="document.id")
    size: int
    metrics: dict = Field(sa_column=Column(JSON))   # §4.5 keys
    campaign_score: float
    preliminary_type: str
    verdict_type: str | None                         # set by agent (same enum)
    confidence: str | None                           # low|medium|high
    rationale: str | None
    cited_document_ids: list = Field(sa_column=Column(JSON), default=[])
    citations_corrected: bool = False
    recommend_review: bool = True
    review_status: str = "unreviewed"               # unreviewed|confirmed|rejected|unsure

class ClusterMember(SQLModel, table=True):
    cluster_id: int = Field(foreign_key="cluster.id", primary_key=True)
    document_id: int = Field(foreign_key="document.id", primary_key=True)
    sim_to_medoid: float
    lex_to_medoid: float
    ai_score: float | None
    is_medoid: bool = False

class AgentTrace(SQLModel, table=True):
    id: int = Field(primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    cluster_id: int | None
    step_no: int
    action: str
    args: dict = Field(sa_column=Column(JSON))
    observation: dict = Field(sa_column=Column(JSON))   # truncated to 4 KB
    created_at: datetime

class Review(SQLModel, table=True):
    id: int = Field(primary_key=True)
    cluster_id: int = Field(foreign_key="cluster.id", index=True)
    decision: str                                    # confirmed|rejected|unsure
    note: str | None
    created_at: datetime
```

Type enum used everywhere: `coordinated_paraphrase_campaign | form_letter | organic_agreement | insufficient_evidence`.

---

## 6. REST API (`/api/v1`)

Write routes require header `X-Admin-Token` when `ADMIN_TOKEN` is set. Errors use `{"error": {"code": str, "message": str}}` with proper HTTP status. Long work returns `202` and is polled.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | – | `{status, db, providers: {regulations, gemini, groq}: "configured"|"missing"}` |
| GET | `/dockets` | – | `DocketOut[]` |
| POST | `/dockets` | `{docket_id, max_comments=500}` | `202 DocketOut` (ingest started or resumed) |
| POST | `/dockets/samples/{sample_name}` | – | `201 DocketOut` |
| GET | `/samples` | – | `[{name, docket_id, count}]` |
| GET | `/dockets/{docket_id}` | – | `DocketOut` incl. ingest progress |
| GET | `/dockets/{docket_id}/documents` | `limit=50, offset=0, q=` | `{items: DocumentOut[], total}` |
| POST | `/analyses` | `{mode:"docket", docket_id}` or `{mode:"text", docket_id, text}` | `202 {analysis_id}`; `409` if one is running |
| GET | `/analyses` | `docket_id=` | `AnalysisSummary[]` |
| GET | `/analyses/{id}` | – | `AnalysisOut`: status, steps[], summary, usage, `clusters: ClusterSummary[]` sorted by score |
| GET | `/analyses/{id}/trace` | `cluster_id=` | `AgentTraceOut[]` |
| GET | `/clusters/{id}` | – | `ClusterOut`: metrics, verdict, rationale, citations, members (paged) |
| GET | `/clusters/{id}/graph` | `max_nodes=60` | `{nodes:[{id, excerpt, submitter_label, posted_at, ai_score, sim, lex, is_medoid}], edges:[{source, target, sim, lex}]}` (star edges from medoid) |
| POST | `/clusters/{id}/reviews` | `{decision, note?}` | `201 ReviewOut` |
| GET | `/reviews/export.csv` | `docket_id=` | CSV of reviews with metrics |
| GET | `/documents/{id}` | – | `DocumentOut` (full text) |
| GET | `/documents/compare` | `a=&b=` | `{a, b, sem, lex, shared: [{a_start, a_end, b_start, b_end, text}]}` |

`ClusterSummary` = `{id, size, campaign_score, preliminary_type, verdict_type, confidence, review_status, metrics:{reword_index, burst_24h, name_diversity, ai_agg}, medoid_excerpt}`.

Frontend polls `GET /analyses/{id}` every 1.5 s while `status` is `queued|running`, and `GET /dockets/{id}` every 3 s while ingesting.

---

## 7. Runtime agent (inside the app)

Provider-agnostic loop: the LLM replies with **one JSON object per turn**, validated by Pydantic. No provider-specific function calling, so Groq and Gemini are interchangeable.

**Turn format:** `{"thought": "<≤2 sentences>", "action": "<tool name>", "args": {...}}`
**Budget:** `AGENT_MAX_STEPS` = 6 per family; invalid JSON gets one repair retry, then the family falls back to its preliminary type with `confidence="low"` and rationale "Automatic review unavailable."

**Tools (`agent/tools.py`), all read-only except the final one:**
| Tool | Args | Observation |
|---|---|---|
| `family_summary` | – | metrics, preliminary type, size, date range |
| `list_members` | `limit≤10, offset, order: "sim"|"time"|"ai"` | id, 300-char excerpt, posted_at, submitter_hash prefix, sim, lex, ai_score |
| `compare` | `doc_a, doc_b` | sem, lex, top 5 shared phrases |
| `search_similar` | `doc_id, k≤10, min_sim≥0.75` | nearest docket comments **outside** the family |
| `timeline` | – | member counts per hour bucket |
| `submit_verdict` | `type, confidence, rationale (≤120 words), cited_document_ids (2–8), recommend_review` | ends the loop |

**Citation validation (`agent/citations.py`):** allowed IDs = members of the family ∪ IDs returned by any tool in this trace. Invalid IDs are removed; if fewer than 2 remain, confidence drops one level and `citations_corrected=true`.

**System prompt (`agent/prompts.py`, keep this wording):**
```
You review one family of public comments on a government regulation. The family was
grouped automatically because its comments share meaning. Decide which type fits best:
coordinated_paraphrase_campaign, form_letter, organic_agreement, insufficient_evidence.

Rules:
- Using AI to write is legitimate. Never conclude "campaign" from AI-style scores alone.
  A campaign needs a family pattern: same argument, different wording, and supporting
  signals such as a time burst or many distinct submitters in a short window.
- Many people independently agreeing is organic_agreement, not a campaign. Varied
  structure, personal details, and spread-out timing point that way.
- Identical or near-identical text is form_letter. That is a normal, legitimate practice.
- You cannot verify identities. Never call submitters fake, bots, or fraudulent.
- Cite only comment IDs you have seen in tool observations. Cite 2 to 8.
- Rationale: plain language, at most 120 words, name the metrics that decided it.
- Reply with exactly one JSON object per turn: {"thought","action","args"}. No prose.

Available tools: {tool_specs}
Family context: {family_summary_json}
```

**Docket summary:** one extra LLM call over the reviewed families' verdicts only (no raw text), ≤150 words, same wording rules.

---

## 8. Configuration (`backend/.env.example`)

```
DATABASE_URL=sqlite:///./echotrace.db
ADMIN_TOKEN=
CORS_ORIGINS=http://localhost:5173
REGULATIONS_API_KEY=
GEMINI_API_KEY=
GEMINI_EMBED_MODEL=gemini-embedding-001
GEMINI_EMBED_DIM=768
GEMINI_CHAT_MODEL=gemini-3.8-flash          # verify current free model in AI Studio
GROQ_API_KEY=
GROQ_CHAT_MODEL=openai/gpt-oss-120b     # verify in Groq console
LLM_PRIMARY=groq                            # groq|gemini
SIM_EDGE=0.86
SIM_MEMBER=0.82
MIN_FAMILY=3
MIN_CAMPAIGN=5
MIN_WORDS=25
AI_SAMPLE_PER_FAMILY=8
AGENT_MAX_FAMILIES=10
AGENT_MAX_STEPS=6
INGEST_MAX_COMMENTS=500
REGULATIONS_REQS_PER_HOUR=900
LLM_REQS_PER_MINUTE=25
```

Frontend: `frontend/.env` → `VITE_API_BASE=http://localhost:8000/api/v1`.

---

## 9. Reliability rules

- `ratelimit.py`: token bucket per provider; retry 429/5xx with exponential backoff + jitter (max 5 tries); honour `Retry-After`.
- LLM fallback: on repeated failure of the primary provider, switch to the other for the rest of the analysis and record it in `params`.
- Every step writes its `AnalysisStep` row before and after; an exception marks the step and analysis `failed` with a readable message.
- Observations stored in `AgentTrace` are truncated to 4 KB; raw comment text never leaves the DB except via tool observations and API responses.

---

## 10. Running locally (Windows 11, PowerShell, no Docker)

```powershell
# backend
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
copy .env.example .env               # then fill keys
python scripts\check_connectivity.py
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

## 11. Deployment (optional, free, no Docker)

1. **Supabase:** create project → copy the Postgres connection string (pooler) → `DATABASE_URL=postgresql+psycopg://...`. Tables are created on startup; seed by calling `POST /dockets/samples/{name}` once.
2. **Render:** New Web Service from the GitHub repo, root `backend`, runtime Python, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; set env vars; set `ADMIN_TOKEN`.
3. **Vercel/Netlify:** root `frontend`, build `npm run build`, output `dist`, env `VITE_API_BASE=https://<render-app>/api/v1`; add the site origin to `CORS_ORIGINS`.
4. Free web services sleep when idle and may stop long background jobs. The deployed demo should use pre-seeded samples; do large ingests locally.
