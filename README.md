# EchoTrace

Agentic system that judges whether a news article is independent reporting
or an AI-reworded content-farm copy, by retrieving its near-duplicate
versions **live from the web** and aggregating detection signal across the
whole cluster.

## Status

Production build. Retrieval is live (GDELT DOC 2.0 API + article
fetch/extract) — no dataset stands in for real near-duplicate evidence
anymore; paste any article's text or URL and it's checked against the real
web. The RoBERTa detector is fine-tuned and committed
(`models/echotrace-detector/`). The app is behind real authentication —
every user has a real account (hashed password, rate-limited login) and
every API request carries a signed session token. The data layer runs on
Postgres in production (SQLite for zero-setup local dev), and the whole
stack (backend + React frontend + Postgres) ships as Docker Compose
services — see `DEPLOYMENT.md`.

The original static-corpus pipeline (NEWS-COPY + M-DAIGT datasets) is still
real and still here — it's what the ablation script and the in-app
**Detector Sandbox** page use, since a live web article has no
ground-truth label to check the detector against. See
`docs/DATA_PROVENANCE.md` for that data's provenance and
`docs/ABLATION_DESIGN.md` for the aggregation-vs-single-instance result.

## Quickest way to run it: Docker Compose

```bash
cp .env.example .env
# edit .env: set JWT_SECRET (generate with: python3 -c "import secrets; print(secrets.token_hex(32))")
# ANTHROPIC_API_KEY is optional — only needed for the agentic /api/verdict endpoint

docker compose up -d --build
```

Open `http://localhost:8080` (or your `FRONTEND_PORT`). Create an account,
log in, paste an article's text or URL. See `DEPLOYMENT.md` for putting a
real domain in front of it (automatic HTTPS via the bundled `caddy`
profile) or pointing it at your own reverse proxy.

## Running it without Docker (local dev)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set JWT_SECRET

# one-time: seed the static demo corpus (Detector Sandbox + ablation only —
# the live investigate flow needs no seeding)
python3 scripts/build_sqlite.py
python3 scripts/build_chroma.py

# backend (defaults to a local SQLite file; set DATABASE_URL for Postgres)
python3 -m uvicorn echotrace.api.main:app --app-dir src --port 8010

# frontend, separate terminal
cd frontend && npm install && npm run dev
```

## Layout

- `docs/DATA_PROVENANCE.md` — where the static demo/ablation datasets came from and how they were verified
- `docs/ABLATION_DESIGN.md` — the aggregation-vs-single-instance ablation and its honest scope
- `DEPLOYMENT.md` — Docker Compose deployment, domains/HTTPS, environment variables
- `src/echotrace/db.py` — SQLAlchemy schema (SQLite dev / Postgres production via `DATABASE_URL`)
- `src/echotrace/auth/` — password hashing, JWT session tokens, login rate limiting
- `src/echotrace/retrieval/live_search.py` — live near-duplicate retrieval: GDELT search → fetch/extract → embedding rank
- `src/echotrace/retrieval/search.py` — the static ChromaDB corpus lookup (Detector Sandbox / ablation only)
- `src/echotrace/detection/`, `src/echotrace/aggregation/`, `src/echotrace/agent/` — detector, aggregation formula, agentic verdict loop
- `src/echotrace/api/main.py` — FastAPI app: auth, live investigate (+ SSE streaming), history, Detector Sandbox endpoints
- `frontend/` — the production client: React + Vite, animated case-board UI, login, live investigate, history, Detector Sandbox
- `streamlit_app/app.py` — earlier Streamlit client, kept for reference; no longer the primary frontend
- `scripts/run_ablation.py` — the aggregated-vs-single-instance ablation
- `tests/` — `pytest tests/` (network-touching pieces mocked; everything else runs for real)
