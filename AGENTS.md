# AGENTS.md — Instructions for the coding agent

You are building **EchoTrace**, a prototype that finds families of reworded public comments on U.S. rulemaking dockets and explains, with cited evidence, whether a family looks like a coordinated campaign. (If you are Claude Code, this file may also be copied to `CLAUDE.md`.)

## Read first, in this order
1. `docs/PRD.md` — what and why; principles in §2 override convenience.
2. `docs/ARCHITECTURE.md` — stack, algorithms, schema, API, runtime agent. Source of truth.
3. `docs/DESIGN_SYSTEM.md` — before touching any frontend file.
4. `docs/TASKS.md` — do the first unticked task.

## How to work
- One task from `TASKS.md` at a time. Finish it, meet its **Done when**, tick it, then stop and summarise: files changed, how you verified, anything unresolved.
- Do not start the next phase while tasks in the current phase are unticked, unless the user says so.
- If a task conflicts with `ARCHITECTURE.md`, or a spec is ambiguous, ask instead of guessing. If you change a spec, update the doc in the same change.
- Record decisions, calibrated thresholds, connectivity results, and measured timings in `docs/NOTES.md`.

## Environment (hard constraints)
- Windows 11, PowerShell, VS Code. Give commands in PowerShell syntax (`.venv\Scripts\Activate.ps1`, `copy`, backslash paths).
- **No Docker**, no docker-compose, no devcontainers, no Dockerfiles.
- **Hugging Face is blocked.** Never add `transformers`, `sentence-transformers`, `huggingface_hub`, or anything that downloads from Hugging Face.
- **No model training or fine-tuning.** Intelligence comes from Gemini embeddings, Groq/Gemini LLM calls, and the formulas in ARCHITECTURE §4.
- Free tiers only. Do not add paid services, Redis, Celery, or hosted vector DBs.
- Python 3.11, FastAPI, SQLModel; React + Vite + TypeScript. Do not swap frameworks.

## Code rules
- Every model name, threshold, and limit comes from `app/config.py`. No literals in code.
- Secrets only in `.env`; never log, print, commit, or echo keys.
- All outbound HTTP goes through `services/ratelimit.py` retry/backoff.
- Tests never touch the network. Use `FakeEmbedder`, `FakeLLM`, and `respx`.
- Keep modules small and typed; type hints on all functions; no `Any` in public signatures.
- Handle failure visibly: a failed step sets `AnalysisStep.status="failed"` with a readable message.

## Data rules
- Demo and evaluation data must be **real** Regulations.gov responses (`scripts/fetch_sample.py`). Never generate fake comments for demos, samples, or results.
- Tiny handwritten strings are allowed only inside unit-test fixtures and must not be used as evaluation data.
- Comments are public records, but keep the "Hide names" feature working and on by default in demos.

## Product-ethics rules (enforced in code review)
- An AI-style score alone must never produce `coordinated_paraphrase_campaign`. Keep the guard in `features.py` and its test.
- UI and agent text must never say: fake, bot, fraud, sockpuppet, astroturf, "AI detected". Use the vocabulary in DESIGN_SYSTEM §6.
- Nothing is deleted, hidden, or down-ranked automatically. Reviews are human decisions.
- Agent citations are validated server-side; never render an uncited or unvalidated claim.

## Definition of done (every task)
- Backend: `pytest -q` passes; `uvicorn app.main:app` starts cleanly.
- Frontend: `npm run build` passes with no type errors.
- The task's **Done when** is demonstrably true.
- Docs updated if behaviour or specs changed.
