# CLAUDE.md — EchoTrace

This file orients Claude Code (and any other coding agent) working in this repository. It is synthesised from `my-ai-project/PRD.md`, `my-ai-project/ARCHITECTURE.md`, `my-ai-project/TASKS.md`, `my-ai-project/DESIGN_SYSTEM.md`, and `my-ai-project/AGENTS.md`. Those documents are the source of truth; this file is a map to them, not a replacement. If anything here drifts from those docs, the docs win — update this file to match.

**No source code has been generated from this pass.** This is documentation only.

---

## 1. What EchoTrace is

EchoTrace finds families of reworded public comments on U.S. government rulemaking dockets, measures how coordinated each family looks, and has an AI agent explain the evidence to a human reviewer, with citations.

**One line:** it shows when many apparent voices are really one.

**Why it matters:** agencies weigh public comments partly by count. Exact-duplicate form letters are already handled by existing tools, but LLMs now let one actor submit thousands of *reworded* versions of the same argument — different wording, same meaning — which exact-match tools miss. EchoTrace's signal is the **family** (many texts, same meaning, different wording, arriving in a burst, under different names), not any single-text "is this AI-written" score.

### Non-negotiable product principles (PRD §2)
1. **Coordination is the finding, not AI use.** An AI-style score alone never produces a flag.
2. **Evidence, not accusations.** Output says "these 212 comments form one reworded campaign," never "these are fake" or "bots."
3. **Human decides.** The system triages and explains; a reviewer confirms or rejects. Nothing is deleted or hidden.
4. **Inspectable scoring.** Every number in a verdict traces to a formula and specific comments.
5. **Real data only.** Demo and evaluation data come from the real Regulations.gov API. Tiny handwritten strings are allowed only inside unit tests.

### Primary users
- **Comment analyst** (agency staff, primary persona) — runs a docket analysis, reviews ranked campaign families, confirms/rejects.
- **Civic-tech researcher / journalist** — checks a docket or single comment, exports evidence.
- **Academic reviewer / portfolio viewer** (demo audience) — loads a bundled real sample docket and inspects a verdict.

### Explicitly out of scope for MVP
Account system / multi-user auth (single shared admin token instead) · attachment/PDF text extraction · non-English text · identifying which comment is the "original" · live social-media sources (adapter interface allows this later) · model training or fine-tuning · any automatic removal or down-ranking.

---

## 2. Architecture & workflow

### Stack (all free, no Docker)
| Layer | Choice |
|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind CSS v4, React Router, TanStack Query, `@xyflow/react` (evidence board) |
| Backend | Python 3.11 + FastAPI + Uvicorn, SQLModel (SQLAlchemy), Pydantic v2, httpx, numpy |
| Database | SQLite locally (`echotrace.db`); Supabase Postgres free tier when deployed, same SQLModel code via `DATABASE_URL` |
| Vector search | numpy brute-force cosine over float32 vectors (BLOB/BYTEA) — no vector DB needed at this scale |
| Embeddings | Gemini API (`gemini-embedding-001`, 768 dims) |
| LLM | Groq primary (e.g. `llama-3.3-70b-versatile`), Gemini Flash fallback; provider-agnostic JSON protocol |
| Data source | Regulations.gov API v4, free api.data.gov key |
| Background work | FastAPI `BackgroundTasks` + one in-process lock (single user, no Redis/Celery) |
| Tests | pytest + `FakeLLM`/`FakeEmbedder` + `respx`; Vitest for frontend utils |
| Hosting (optional) | Render (backend), Vercel/Netlify (frontend static), Supabase (DB) — all native builds, no containers |

Model names and thresholds are not fixed forever — they live in `.env`/`config.py`, never hardcoded, and must be verified against each provider's current console before Phase 3 work begins.

### System flow
```
Browser (React/Vite) → REST /api/v1 (JSON, polling) → FastAPI
  routers/ (dockets, analyses, clusters, documents)
  services/ pipeline: normalize → embeddings (Gemini) → similarity (numpy)
            → features (campaign shape) → ai_scoring (Groq/Gemini)
            → aggregation → agent.runner (Groq/Gemini)
  SQLModel → SQLite (local) / Supabase Postgres (deployed)
```

### Repository layout (target)
```
echotrace/
├── AGENTS.md / CLAUDE.md
├── docs/  PRD.md  ARCHITECTURE.md  DESIGN_SYSTEM.md  TASKS.md  NOTES.md
├── data/samples/            # real cached Regulations.gov responses (committed)
├── backend/
│   ├── requirements.txt  .env.example
│   └── app/
│       ├── main.py  config.py  db.py  models.py  schemas.py  security.py
│       ├── routers/  health.py dockets.py analyses.py clusters.py documents.py
│       ├── services/
│       │   ├── sources/ base.py regulations_gov.py sample_loader.py
│       │   ├── normalize.py embeddings.py llm.py
│       │   ├── similarity.py features.py ai_scoring.py
│       │   ├── aggregation.py compare.py pipeline.py ratelimit.py
│       │   └── agent/ prompts.py tools.py runner.py citations.py
│   ├── scripts/ check_connectivity.py fetch_sample.py calibrate.py export_reviews.py
│   └── tests/
└── frontend/
    ├── package.json  vite.config.ts  index.html
    └── src/ main.tsx App.tsx styles/tokens.css
        ├── api/ client.ts types.ts hooks.ts
        ├── pages/ DocketsPage.tsx DocketPage.tsx AnalysisPage.tsx CheckPage.tsx
        └── components/ (see design system §5)
```

### The pipeline (algorithms — ARCHITECTURE §4, all thresholds are starting values from `config.py`, tunable via `scripts/calibrate.py`)
1. **Ingest** — Regulations.gov list + per-comment detail calls, rate-limited, resumable (skip already-stored `external_id`s). Skip attachment-only/empty bodies, count skipped.
2. **Normalise** — lowercase/strip HTML/collapse whitespace for hashing; `text_hash = sha256(normalised)`; exact-hash groups recorded as form-letter evidence pre-embedding.
3. **Embed** — batch unique hashes (≤100/request) to Gemini, task type CLUSTERING, 768 dims, L2-normalise, cache by `(text_hash, model)`; never re-embed a cached hash.
4. **Cluster** — cosine similarity matrix → union-find on edges `≥ SIM_EDGE (0.86)` → medoid-based chaining guard drops members `< SIM_MEMBER (0.82)` from medoid → keep families `size ≥ MIN_FAMILY (3)`.
5. **Campaign-shape features** (per family, relative to medoid): `size`, `mean_sem`, `mean_lex`, `reword_index = mean_sem × (1 − mean_lex)`, `exact_dup_share`, `burst_24h`, `name_diversity`, `anon_share`, `ai_agg`.
6. **AI-style score** — LLM batch-scores up to `AI_SAMPLE_PER_FAMILY (8)` members per family (medoid always included), one call, JSON `[{id, score, reason}]`, cached, shown as "AI-style signal (unverified)" — weak evidence by design.
7. **Aggregation** — similarity-weighted `ai_agg` for families; separate formula for single-comment mode.
8. **Campaign score & preliminary type** (rule-based):
   ```
   size_norm = min(1, ln(n) / ln(50))
   campaign_score = 0.35·size_norm + 0.25·reword_index + 0.20·burst_24h + 0.20·ai_agg

   type =
     form_letter                     if exact_dup_share ≥ 0.5 or mean_lex ≥ 0.6
     coordinated_paraphrase_campaign if n ≥ MIN_CAMPAIGN(5) and reword_index ≥ 0.45
                                        and (burst_24h ≥ 0.5 or name_diversity ≥ 0.8)
     organic_agreement               if reword_index ≥ 0.45 and burst_24h < 0.3
     insufficient_evidence           otherwise
   ```
   **Guard (hard rule):** `ai_agg` can raise a score but can never, on its own, move a family into `coordinated_paraphrase_campaign`. This guard lives in `services/features.py` and must have a dedicated test.
9. **Agent review** — top `AGENT_MAX_FAMILIES (10)` families go to the runtime agent, which may confirm/change the type, sets confidence, writes cited rationale, then writes a docket-level summary.
10. **Single-comment check** — embed pasted text → cosine vs. docket's cached vectors → neighbours `≥ SIM_MEMBER`; fewer than 2 neighbours → `insufficient_evidence` regardless of AI-style score.

### Runtime agent (ARCHITECTURE §7)
- Provider-agnostic loop: the LLM replies with **one JSON object per turn** (`{"thought", "action", "args"}`), validated by Pydantic — no provider-specific function calling, so Groq/Gemini are interchangeable.
- Budget: `AGENT_MAX_STEPS = 6` per family; invalid JSON gets one repair retry, then falls back to preliminary type with `confidence="low"`.
- Tools (all read-only except the last): `family_summary`, `list_members`, `compare`, `search_similar`, `timeline`, `submit_verdict` (ends the loop; args: `type, confidence, rationale ≤120 words, cited_document_ids (2–8), recommend_review`).
- **Citation validation is mandatory and server-side**: allowed IDs = family members ∪ IDs seen in tool observations this trace. Invalid IDs are stripped; if fewer than 2 remain, confidence drops one level and `citations_corrected=true`.
- System prompt wording is fixed in ARCHITECTURE §7 and must be kept verbatim — it encodes the product-ethics rules (never conclude "campaign" from AI-style alone, never call submitters fake/bots/fraudulent, cite only seen IDs, ≤120-word plain-language rationale, exactly one JSON object per turn).

### Data model, REST API, and .env keys
Full SQLModel schema (`Docket`, `Document`, `EmbeddingCache`, `AiScoreCache`, `Analysis`, `AnalysisStep`, `Cluster`, `ClusterMember`, `AgentTrace`, `Review`) is defined in `ARCHITECTURE.md` §5 — implement it exactly as written there, don't improvise fields. The full REST surface (`/api/v1/...`) is in §6; the `.env.example` key list is in §8. Treat both as literal specs to copy, not to redesign.

### Reliability rules
- `services/ratelimit.py`: async token bucket per provider; retry 429/5xx with exponential backoff + jitter (max 5 tries); honour `Retry-After`.
- LLM fallback: on repeated primary-provider failure, switch to the other provider for the rest of the analysis and record it in `Analysis.params`.
- Every pipeline step writes its `AnalysisStep` row before and after; an exception marks the step **and** the analysis `failed` with a human-readable message — never fail silently.
- `AgentTrace` observations are truncated to 4 KB; raw comment text never leaves the DB except via tool observations and normal API responses.

---

## 3. Hard constraints (do not violate)

- **Windows 11, PowerShell, VS Code.** Give every command in PowerShell syntax (`.venv\Scripts\Activate.ps1`, `copy`, backslash paths) — never bash syntax.
- **No Docker.** No docker-compose, no devcontainers, no Dockerfiles, ever.
- **Hugging Face is blocked on the network.** Never add `transformers`, `sentence-transformers`, `huggingface_hub`, or anything that downloads from Hugging Face at build or runtime. `scripts/check_connectivity.py` must confirm reachability of `api.regulations.gov`, `generativelanguage.googleapis.com`, and `api.groq.com` before Phase 3 work — if any is blocked, stop and report instead of continuing.
- **No model training or fine-tuning.** All intelligence comes from Gemini embeddings, Groq/Gemini LLM calls, and the formulas in ARCHITECTURE §4 — never from a trained/fine-tuned model.
- **Free tiers only.** Regulations.gov (free api.data.gov key, ~1,000 req/hr), Gemini free tier, Groq free tier. No paid services, no Redis, no Celery, no hosted vector DBs. Provider limits change — verify current numbers in each console before relying on them, don't trust stale numbers in docs.
- **Fixed frameworks.** Python 3.11 + FastAPI + SQLModel on the backend; React + Vite + TypeScript on the frontend. Do not swap frameworks.
- **Real data only for demos/evaluation.** Sourced via `scripts/fetch_sample.py` from the live Regulations.gov API. Never fabricate comments for demos, samples, or results. Tiny handwritten strings are allowed **only** inside unit-test fixtures, never as evaluation data.

---

## 4. Code conventions

- **No magic literals.** Every model name, similarity threshold, and limit comes from `app/config.py` (a `pydantic-settings` `Settings` object populated from `.env`). Code must never hardcode a model name or threshold.
- **Secrets discipline.** Secrets live only in `.env`; never log, print, commit, or echo API keys anywhere, including in error messages or debug output.
- **All outbound HTTP goes through `services/ratelimit.py`.** No direct `httpx`/`requests` calls to external providers that bypass the token-bucket + retry/backoff wrapper.
- **Tests never touch the network.** Use `FakeEmbedder`, `FakeLLM`, and `respx` to mock all HTTP. A test suite that makes a real network call is a bug.
- **Typed, small modules.** Type hints on all functions; **no `Any` in public signatures**. Prefer several small, focused modules over large ones (see the `services/` layout above).
- **Visible failure.** A failed pipeline step sets `AnalysisStep.status = "failed"` with a readable message — never swallow an exception silently or leave a step stuck in `running`.

---

## 5. UI / design system conventions (DESIGN_SYSTEM.md)

**Direction — "the analyst's light table":** a clean examination desk. Comments are physical **documents** on a cool neutral surface; relationships are **threads**. The evidence board is the one bold element; everything else is quiet and orderly. Deliberately avoided: dashboard card grids, dark "hacker" themes, newspaper pastiche, red-string conspiracy-board aesthetics. Tone: calm, exact, fair — this is civic infrastructure, not a true-crime app.

### Tokens (`frontend/src/styles/tokens.css`)
- Colour tokens (`--desk`, `--paper`, `--ink`, `--ink-soft`, `--rule`, `--thread`, `--marker`, `--campaign`, `--form`, `--organic`, `--unsure`) are defined for both light and dark (`prefers-color-scheme: dark`). **Colour never carries meaning alone** — every verdict colour always ships with a text label, and thread dash-pattern independently encodes reword vs. copy.
- **Type:** Public Sans (Google Fonts) for all interface text, tabular figures for every metric. **Source Serif 4 for comment text only** — this sans/serif split is the core typographic rule: serif = a real submitted document, sans = EchoTrace talking. Never mix these roles. Scale: 0.8125/0.875/1/1.125/1.375/1.75 rem; weights 400 and 600 only; sentence case everywhere, no all-caps labels; comment text line length ≤72ch.
- **Space/shape/depth:** 4px base spacing scale (4,8,12,16,24,32,48). Radius encodes object kind: sheets 2px, controls 6px, chips 999px. Only comment sheets on the board get a shadow (they're the "physical objects on the desk"); panels are flat with a `--rule` border.

### Layout
Three-column desktop layout (≥1200px): Families list (280px) | Evidence board (fluid) | Verdict drawer (360px), with a Compare tray along the bottom on member click. 768–1199px: list collapses to a top selector, drawer becomes a bottom sheet. <768px: board is replaced by a similarity-sorted member list (graphs are unusable at phone width). Text left-aligned; numbers right-aligned in tables.

### The evidence board (signature element, built with `@xyflow/react`)
Exact encoding table (implement literally, don't reinterpret):
| Visual | Meaning |
|---|---|
| Centre sheet, larger, `--ink` 2px border | Medoid (representative comment) |
| Surrounding sheets (3-line serif excerpt) | Members; radius from centre = `1 − sim` |
| Thread thickness 1–4px | Meaning similarity to medoid |
| Dashed thread | Low word overlap (lex < 0.35) — reworded |
| Solid thread | High word overlap — copied |
| Corner dot, `--thread` fill scaled by value | AI-style signal |
| Cited sheets | 2px verdict-colour outline + citation number |

The dashed/solid distinction is the product's core idea made visible — a board full of dashed threads *is* what a reworded campaign looks like. Interactions: click selects and opens compare tray vs. medoid; shift-click compares two sheets directly; citation chips in the drawer select/centre their sheet; max 60 nodes rendered, with a "Showing 60 of N — view all in list" fallback. One orchestrated settle animation (400ms ease-out) on analysis completion only, respecting `prefers-reduced-motion`.

### Components (see DESIGN_SYSTEM §5 for the full table)
`AppShell`, `DocketForm`, `SampleList`, `IngestProgress`, `PipelineStepper`, `FamilyList`, `VerdictTag`, `EvidenceBoard`, `CommentSheet`, `VerdictDrawer`, `CitationChip`, `MetricTable` (hover/focus reveals the formula), `CompareTray`, `ReviewBar` ("Confirm campaign" / "Reject" / "Mark unsure"), `AgentTrace`, `EmptyState`, `ErrorState`.

### Copy rules (binding on all UI and agent-generated text)
- **Use:** family, campaign (a coordinated family), representative comment (medoid), reworded, "AI-style signal (unverified)".
- **Never use:** fake, bot, fraud, sockpuppet, astroturf, "AI detected". The product cannot verify identities and must never imply it can.
- Verdict phrasing is fixed, e.g.: "Likely one coordinated campaign — 212 reworded comments, 81% within 24 hours." / "Form letter — 48 near-identical comments." / "Similar views, independently worded." / "Not enough evidence to call this a campaign."
- Empty/error states must name the next action, e.g.: "No dockets yet. Add a docket ID or load a sample." / "Gemini key missing. Add GEMINI_API_KEY to backend/.env and restart."
- **Privacy:** submitter names display as given (public record) but a "Hide names" header toggle replaces them with `Submitter a3f9` (hash prefix) — **default ON in demos**.

### Accessibility floor
WCAG AA contrast for all text; visible focus ring `2px solid var(--thread)` offset 2px; every evidence-board action must also be reachable from the plain member list; the graph needs an accessible "View as list" table alternative; a live region announces pipeline step changes; hit targets ≥40px.

---

## 6. Execution rules (from AGENTS.md)

### Read order
1. `docs/PRD.md` — what and why; §2 principles override convenience.
2. `docs/ARCHITECTURE.md` — stack, algorithms, schema, API, runtime agent; source of truth for anything technical.
3. `docs/DESIGN_SYSTEM.md` — read before touching any frontend file.
4. `docs/TASKS.md` — do the first unticked task.

### How to work
- **One task from `TASKS.md` at a time.** Finish it, meet its stated "Done when," tick it, then stop and summarise: files changed, how it was verified, anything left unresolved.
- **Do not start the next phase** while tasks in the current phase are unticked, unless the user explicitly says to.
- If a task conflicts with `ARCHITECTURE.md`, or a spec is ambiguous, **ask instead of guessing.** If a spec is changed, update the doc in the same change.
- Record decisions, calibrated thresholds, connectivity check results, and measured timings in `docs/NOTES.md` as they happen — not retroactively.

### Product-ethics rules (enforced in code review, non-negotiable)
- An AI-style score alone must never produce `coordinated_paraphrase_campaign` — this guard lives in `features.py` and must have its own test.
- UI and agent text must never say: fake, bot, fraud, sockpuppet, astroturf, "AI detected." Use the DESIGN_SYSTEM §6 vocabulary instead.
- Nothing is ever deleted, hidden, or down-ranked automatically — reviews are human decisions, full stop.
- Agent citations are validated server-side; an uncited or unvalidated claim must never be rendered.

### Definition of done (every task)
- Backend: `pytest -q` passes; `uvicorn app.main:app` starts cleanly.
- Frontend: `npm run build` passes with no type errors.
- The task's own "Done when" condition is demonstrably true.
- Docs updated if behaviour or specs changed as part of the task.

---

## 7. Known limitations to state in any demo (PRD §8)

- Cannot distinguish a real organisation's members each reworking a template from one actor using fake names — text alone can't prove identities. The verdict is "one campaign," never "fake people."
- The AI-style signal is an unverified LLM judgement and carries low weight by design.
- Quality depends on embeddings; very loose paraphrases may be missed; comments under 25 words are excluded from clustering.
- Regulations.gov only exposes text typed into the form; attachment-only comments are skipped and counted separately.
