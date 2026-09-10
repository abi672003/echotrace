# EchoTrace

Agentic system that judges whether a news article is independent reporting
or an AI-reworded content-farm copy, by retrieving its near-duplicate
versions and aggregating detection signal across the whole cluster.

## Status

Every dataset is real (see `docs/DATA_PROVENANCE.md`) and every pipeline
stage is implemented and tested against real data. The RoBERTa detector is
fine-tuned and committed (`models/echotrace-detector/`). The app is behind
real authentication — every user has a real account (hashed password) and
every API request carries a signed session token.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# one-time data layer build (already done once — only needed after a fresh clone)
python3 scripts/build_sqlite.py
python3 scripts/build_chroma.py

cp .env.example .env
# edit .env: set JWT_SECRET (generate with: python3 -c "import secrets; print(secrets.token_hex(32))")
# and ANTHROPIC_API_KEY if you want the agentic verdict layer live
```

## Running it

```bash
# backend
python3 -m uvicorn echotrace.api.main:app --app-dir src --port 8010

# Streamlit frontend (separate terminal, production client)
streamlit run streamlit_app/app.py
```

Open the URL Streamlit prints (usually http://localhost:8501). First run:
create an account on the "Create account" tab, then log in — every request
after that carries your session token.

The old React frontend (`frontend/`) is still in the repo but is no longer
the primary client — Streamlit is.

## Layout

- `docs/DATA_PROVENANCE.md` — where every dataset actually came from and how it was verified
- `docs/ABLATION_DESIGN.md` — the aggregation-vs-single-instance ablation and its honest scope
- `src/echotrace/auth/` — password hashing + JWT session tokens
- `src/echotrace/` — retrieval, detection, aggregation, agent, API
- `streamlit_app/app.py` — the production frontend (login → case investigation)
- `scripts/run_ablation.py` — the aggregated-vs-single-instance ablation
- `tests/` — `pytest tests/`
