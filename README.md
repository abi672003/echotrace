# EchoTrace

Agentic system that judges whether a news article is independent reporting
or an AI-reworded content-farm copy, by retrieving its near-duplicate
versions and aggregating detection signal across the whole cluster.

## What's real, what's pending

Every dataset here is real (see `docs/DATA_PROVENANCE.md`) and every
pipeline stage is implemented and tested against real data. The one thing
missing is the fine-tuned RoBERTa detector checkpoint — it must be trained
in Google Colab (this project can't reach Hugging Face from the eventual
deployment laptop, and this session can't run multi-hour Colab training
itself; see constraint 0.3 in the project brief).

**To finish setup:**
1. Open `notebooks/finetune_roberta_mdaigt.ipynb` in Google Colab (GPU
   runtime), upload `data/raw/mdaigt/train_mdaigt_task1.csv` when prompted,
   run all cells.
2. Download the resulting `echotrace-detector.zip`, unzip it into
   `models/echotrace-detector/` (replacing the empty placeholder).
3. `git add models/echotrace-detector && git commit` (already LFS-tracked).
4. Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY` (needed
   for the agentic verdict layer in `src/echotrace/agent/`).

## Running it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# one-time data layer build (already done once — only needed after a fresh clone)
python3 scripts/build_sqlite.py
python3 scripts/build_chroma.py

# backend
python3 -m uvicorn echotrace.api.main:app --app-dir src --port 8010

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Detection scores show "pending" until the
checkpoint from step 1 above is in place.

## Layout

- `docs/DATA_PROVENANCE.md` — where every dataset actually came from and how it was verified
- `docs/ABLATION_DESIGN.md` — the aggregation-vs-single-instance ablation and its honest scope
- `src/echotrace/` — retrieval, detection, aggregation, agent, API
- `scripts/run_ablation.py` — run once the detector checkpoint is in place
- `tests/` — `pytest tests/`
