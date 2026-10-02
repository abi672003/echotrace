# EchoTrace — Build Checklist

Work top to bottom. One task = one focused change. Tick `[x]` only when its **Done when** is true. Section numbers (§) refer to `ARCHITECTURE.md`; design references to `DESIGN_SYSTEM.md`.

---

## Phase 1 — Setup & scaffolding

- [x] **1.1 Repo skeleton** — create folders from §3; move docs into `docs/`; root `.gitignore` (`.venv/`, `node_modules/`, `.env`, `*.db`, `dist/`, `__pycache__/`).
  Done when: tree matches §3 (empty files allowed).
- [x] **1.2 `backend/requirements.txt`** — `fastapi`, `uvicorn[standard]`, `sqlmodel`, `pydantic-settings`, `httpx`, `numpy`, `google-genai`, `groq`, `psycopg[binary]`, `python-dotenv`, `pytest`, `pytest-asyncio`, `respx`. Pin exact versions after first successful install.
  Done when: `pip install -r requirements.txt` succeeds in a fresh venv on Windows.
- [x] **1.3 `backend/.env.example`** — copy §8 exactly.
- [x] **1.4 `backend/app/config.py`** — `Settings(BaseSettings)` with every §8 key and types; `get_settings()` cached.
  Done when: `python -c "from app.config import get_settings; print(get_settings().SIM_EDGE)"` prints `0.86`.
- [x] **1.5 `backend/scripts/check_connectivity.py`** — for Regulations.gov (`/v4/dockets?page[size]=5`), Gemini (embed "hello"), Groq (1-token completion): print OK / HTTP status / "blocked by network" per provider; never print keys.
  Done when: run on the company laptop and results recorded in `docs/NOTES.md`. **If any host is blocked, stop and report before Phase 3.**
- [x] **1.6 `backend/app/main.py` + `routers/health.py`** — app factory, CORS from settings, `/api/v1/health` per §6.
  Done when: `uvicorn app.main:app --reload` serves `/api/v1/health` and `/docs`.
- [x] **1.7 Frontend scaffold** — `npm create vite@latest frontend -- --template react-ts`; add `tailwindcss @tailwindcss/vite react-router-dom @tanstack/react-query @xyflow/react`; add `vitest` dev dep.
  Done when: `npm run dev` shows the default page; `npm run build` passes.
- [x] **1.8 `frontend/src/styles/tokens.css`** — all tokens from Design §2 (light + `prefers-color-scheme: dark`), Google Fonts import for Public Sans and Source Serif 4, Tailwind `@theme` mapping.
- [x] **1.9 `frontend/src/api/client.ts`** — `apiGet/apiPost` using `VITE_API_BASE`, JSON error unwrapping to `{code,message}`, optional `X-Admin-Token` header taken from a small settings dialog (held in React context; persisting it to `localStorage` is optional).
  Done when: health call renders provider status in a temporary page.

## Phase 2 — Backend & database

- [x] **2.1 `app/db.py`** — engine from `DATABASE_URL` (`check_same_thread=False` for SQLite; `pool_pre_ping` for Postgres), `get_session` dependency, `create_all` on startup.
- [x] **2.2 `app/models.py`** — all tables exactly as §5, with `created_at` defaults.
  Done when: startup creates tables in `echotrace.db`; `tests/test_models.py` inserts and reads one row per table.
- [x] **2.3 `app/schemas.py`** — request/response models for §6 (`DocketOut`, `DocumentOut`, `AnalysisCreate`, `AnalysisOut`, `ClusterSummary`, `ClusterOut`, `GraphOut`, `CompareOut`, `ReviewIn/Out`, `AgentTraceOut`, `ErrorOut`).
- [x] **2.4 `app/security.py`** — `require_admin` dependency: if `ADMIN_TOKEN` set, header must match, else 401.
- [x] **2.5 `services/ratelimit.py`** — async token bucket + `with_retries(fn)` (429/5xx backoff with jitter, `Retry-After`).
  Done when: unit test proves retries and bucket timing with a fake clock.
- [x] **2.6 `services/normalize.py`** — `clean_text`, `normalize_for_hash`, `text_hash`, `word_count`, `is_attachment_only`, `submitter_hash`.
  Done when: tests cover HTML stripping, whitespace, attachment detection.
- [x] **2.7 `services/sources/base.py`** — `SourceAdapter` protocol + `RawItem` dataclass.
- [x] **2.8 `services/sources/regulations_gov.py`** — list pages + detail per comment (§4.1), rate-limited, resumable, updates `Docket` progress fields, maps fields to `Document`.
  Done when: `respx`-mocked test ingests 3 comments, skips 1 attachment-only, and a second run inserts nothing new.
- [x] **2.9 `scripts/fetch_sample.py`** — `python scripts/fetch_sample.py <DOCKET_ID> --max 500` saves raw real API responses to `data/samples/<DOCKET_ID>.json`.
  Done when: at least one real sample committed (pick an open or recent docket with many comments; record why in `docs/NOTES.md`).
- [x] **2.10 `services/sources/sample_loader.py`** — loads a sample file through the same mapping as 2.8.
- [x] **2.11 `routers/dockets.py`** — `GET/POST /dockets`, `GET /samples`, `POST /dockets/samples/{name}`, `GET /dockets/{id}`, `GET /dockets/{id}/documents` (ingest runs via `BackgroundTasks`).
  Done when: loading the sample via `/docs` returns counts matching the file.
- [x] **2.12 `routers/documents.py`** — `GET /documents/{id}`; `/documents/compare` stub returning 501 until 3.6.

## Phase 3 — AI service integration & pipeline

- [x] **3.1 `services/embeddings.py`** — `Embedder` protocol; `GeminiEmbedder` (batches ≤100, task type CLUSTERING, dim from settings, L2-normalise, cache read/write in `EmbeddingCache`); `FakeEmbedder` for tests (deterministic vectors from hash).
  Done when: embedding the sample twice makes zero API calls the second time.
- [x] **3.2 `services/llm.py`** — `LLM` protocol `complete_json(system, messages, schema) -> dict`; `GroqLLM`, `GeminiLLM` (JSON mode / response schema), `FallbackLLM(primary, secondary)`, `FakeLLM(scripted_responses)`; strips code fences, one repair retry on invalid JSON; increments a call counter.
- [x] **3.3 `services/similarity.py`** — load docket vectors into a matrix; `cosine_matrix`; union-find clustering; medoid; chaining guard (§4.4); `nearest(vec, k, min_sim)`.
  Done when: tests with hand-set vectors produce expected families and drop a chained outlier.
- [ ] **3.4 `scripts/calibrate.py`** — prints histogram of max-neighbour similarity and family sizes at several `SIM_EDGE` values for a docket. Record chosen thresholds in `docs/NOTES.md`.
  **BLOCKED: script is implemented and mechanically verified (synthetic DB, see NOTES.md). A real docket is now ingested (`USCIS-2026-0364`, 2.9) and the pipeline has already embedded+clustered it successfully once (3.14), but that cache was lost in a later DB reset, and re-embedding today hit real, sustained Gemini free-tier quota exhaustion from this session's extensive API testing. Needs a quota reset (next day) to re-embed and record real thresholds — no code gap remains.**
- [x] **3.5 `services/features.py`** — shingles, Jaccard, all §4.5 metrics; `preliminary_type` and `campaign_score` (§4.8) including the AI-only guard.
  Done when: tests cover each type branch and prove `ai_agg=1.0` alone never yields a campaign.
- [x] **3.6 `services/compare.py`** — shared word 5-gram spans between two texts, merged into character ranges; wire `/documents/compare`.
- [x] **3.7 `services/ai_scoring.py`** — batch prompt (≤8 comments, returns `[{id, score, reason}]`), cache in `AiScoreCache`, clamp 0–1.
- [x] **3.8 `services/aggregation.py`** — family and single-comment formulas (§4.7).
  Done when: tests check both formulas against hand-computed values.
- [x] **3.9 `agent/prompts.py`** — system prompt verbatim from §7, tool spec rendering, docket-summary prompt.
- [x] **3.10 `agent/tools.py`** — the six tools of §7, each returning JSON-serialisable dicts, observations truncated to 4 KB.
- [x] **3.11 `agent/citations.py`** — validation rules of §7.
- [x] **3.12 `agent/runner.py`** — loop with `AGENT_MAX_STEPS`, writes `AgentTrace`, applies verdict or fallback.
  Done when: `FakeLLM` tests cover: normal verdict; invalid JSON then repair; hallucinated citation removed and confidence lowered; step budget exhausted → fallback.
- [x] **3.13 `services/pipeline.py`** — `run_docket_analysis(analysis_id)` and `run_text_check(analysis_id)` executing §4.2–4.10, writing `AnalysisStep` rows, counting calls, single global lock.
  Done when: end-to-end test with fakes on 20 fixture comments produces clusters, verdicts, and all steps `done`.
- [x] **3.14 `routers/analyses.py` + `routers/clusters.py`** — all remaining §6 routes incl. graph, reviews, CSV export (`scripts/export_reviews.py` shares the code).
  Done when: real run on the committed sample with real keys completes, and the numbers in `docs/NOTES.md` (time, llm_calls, embed_calls) are recorded.

## Phase 4 — Frontend UI

- [x] **4.1 `src/api/types.ts` + `src/api/hooks.ts`** — TS types mirroring §6; TanStack hooks incl. polling (`refetchInterval` while running).
- [x] **4.2 `App.tsx` + `components/AppShell.tsx`** — routes `/`, `/dockets/:id`, `/analyses/:id`, `/check`; provider status; "Hide names" toggle (context).
- [x] **4.3 `pages/DocketsPage.tsx`** — `DocketForm`, `SampleList`, docket list with `IngestProgress`, empty state copy.
- [x] **4.4 `pages/DocketPage.tsx`** — stats, document search list (serif excerpts), "Analyse docket" button, previous analyses.
- [x] **4.5 `components/PipelineStepper.tsx`** — seven steps, live region announcements, error state.
- [x] **4.6 `components/FamilyList.tsx` + `VerdictTag.tsx`** — ranked rows per Design §5.
- [x] **4.7 `components/CommentSheet.tsx`** — serif text, submitter label (respects Hide names), posted time.
- [x] **4.8 `components/EvidenceBoard.tsx`** — encoding table in Design §4 exactly (radius, thickness, dashed vs solid, AI dot, citation outline); click/shift-click; "View as list" alternative; settle animation with reduced-motion guard.
  Done when: a 60-node family renders smoothly and the dashed/solid rule is verifiable against `lex` values.
- [x] **4.9 `components/VerdictDrawer.tsx`** — verdict sentence (Design §6 phrasing), `CitationChip`s, `MetricTable` with formula tooltips, `ReviewBar`, collapsible `AgentTrace`.
- [x] **4.10 `components/CompareTray.tsx`** — two sheets, shared spans on `--marker`, sem/lex values.
- [x] **4.11 `pages/AnalysisPage.tsx`** — three-column layout from Design §3 with responsive behaviour.
- [x] **4.12 `pages/CheckPage.tsx`** — docket picker (ingested only), textarea (min 25 words), result: family link or "No family found", aggregate, verdict.
- [x] **4.13 Copy + a11y pass** — search codebase for banned words (Design §6); keyboard-only walkthrough; contrast check.

## Phase 5 — Testing & deployment

- [x] **5.1 Backend test suite green** — `pytest -q` with no network (respx blocks real HTTP).
- [x] **5.2 Frontend checks** — `npm run build` (type-check) and Vitest for formatting/verdict-phrase utils.
- [x] **5.3 Demo script `docs/DEMO.md`** — load sample → analyse → open top family → compare two dashed-thread members → read cited rationale → confirm review → paste a comment in Check. Include expected timings and the limitations from PRD §8.
- [ ] **5.4 Evaluation** — review ≥30 families in the UI; export CSV; `docs/RESULTS.md` with precision of the campaign label, form-letter sanity check result, and 2 failure cases explained.
  **BLOCKED: needs ≥30 *real*, human-reviewed families from a real docket. Depends on 2.9 (real sample) and 3.14 (real pipeline run) first, then genuine analyst review — per AGENTS.md this can never be fabricated ("Reviews are human decisions").**
- [ ] **5.5 Supabase** — set `DATABASE_URL`, start backend locally against it, seed sample.
  **BLOCKED: requires a Supabase account (external sign-up/credentials) — a human decision, not something the agent can create.**
- [ ] **5.6 Render backend** — per ARCHITECTURE §11; `/api/v1/health` reachable.
  **BLOCKED: requires a Render account (external sign-up/credentials).**
- [ ] **5.7 Vercel/Netlify frontend** — per §11; CORS verified from deployed origin.
  **BLOCKED: requires a Vercel or Netlify account (external sign-up/credentials); also depends on 5.6 for the backend origin to point at.**
- [x] **5.8 `README.md`** — what it is (two sentences), screenshot, local run steps, keys needed, limitations, links to docs.
