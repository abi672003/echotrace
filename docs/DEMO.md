# EchoTrace — Demo Script

A walkthrough for showing EchoTrace end to end, using a bundled real sample docket (no API key needed except for the AI calls). Expected timings are estimates — see the note at the bottom.

## 1. Load a sample (~5 seconds)

1. Open the app at `/` (Dockets).
2. Under "Bundled samples," click **Load sample** next to a docket.
3. You're taken to the docket page; ingestion is instant since the sample is pre-cached locally — no network wait.

## 2. Analyse the docket (~1-3 minutes, depends on size and provider latency)

1. On the docket page, click **Analyse docket**.
2. Watch the seven-step pipeline run live: Normalize → Embed → Cluster → Measure → AI-style score → Aggregate → Agent review. Each step shows its status and a one-line detail once done.
3. When status reaches "done," the ranked family list appears on the left, and a docket-level summary appears above the stepper.

## 3. Open the top family (~5 seconds)

1. In the ranked family list, click the top row (highest campaign score).
2. The evidence board loads: the representative comment (medoid) sits at the centre, members arranged around it. Thread thickness shows similarity to the medoid; dashed threads mean similar meaning but different wording, solid threads mean copied text.

## 4. Compare two dashed-thread members (~10 seconds)

1. Click one member sheet connected to the medoid by a **dashed** thread — this opens the compare tray against the medoid.
2. Shift-click a second dashed-thread member to compare the two members directly against each other instead.
3. In the compare tray, shared phrasing is highlighted; the semantic and lexical similarity numbers appear above the two sheets. Shared phrases are present despite the differing wording — this is what "reworded" looks like.

## 5. Read the cited rationale (~15 seconds)

1. In the verdict drawer (right column), read the verdict sentence and the agent's rationale.
2. Click a citation chip (the numbered circles) to jump to that cited comment on the board.
3. Expand "Show agent trace" to see the tool calls (`family_summary`, `list_members`, `compare`, etc.) the agent made before deciding.

## 6. Confirm the review (~5 seconds)

1. Optionally add a note in the review bar.
2. Click **Confirm campaign** (or **Reject** / **Mark unsure** if you disagree with the verdict).
3. The family's review status updates immediately; this becomes one row in the exported evaluation CSV (`GET /reviews/export.csv`).

## 7. Check a single comment (~10-30 seconds)

1. Go to **Check a comment** in the header.
2. Pick the same docket, paste in a comment of at least 25 words (you can reuse wording similar to one of the families you just reviewed to see a match, or write something unrelated to see "No family found").
3. Submit and wait for the result: either a family link with an aggregate AI-style signal, or "No family found" if fewer than two similar comments exist in the docket.

## Known limitations to state during a demo (PRD §8)

- EchoTrace cannot tell a real organisation whose members each reworded a shared template apart from one actor using many fake names — text alone can't prove identities. The verdict is always "one campaign," never "fake people."
- The AI-style signal is an unverified LLM judgement and carries low weight in the scoring by design — it can raise a campaign score but can never, on its own, produce a `coordinated_paraphrase_campaign` verdict.
- Quality depends on the embeddings: very loose paraphrases may be missed, and comments under 25 words are excluded from clustering entirely.
- Regulations.gov only exposes text that was typed directly into the comment form; attachment-only comments are skipped and counted separately in the docket's ingest progress.

## A note on timings

The step-by-step timings above are estimates based on the pipeline's design (§4.11's quota budget: ~500 Regulations.gov requests for a full ingest, 5-6 embedding batch calls, ~71 LLM calls for a 500-comment docket) — they have not yet been measured against a real run with live API keys, since that's still blocked on `REGULATIONS_API_KEY`/`GEMINI_API_KEY`/`GROQ_API_KEY` not being configured (see `docs/NOTES.md`, Tasks 2.9/3.4/3.14). Once a real run completes, replace this note with the actual measured wall-clock time, `llm_calls`, and `embed_calls` from `Analysis.usage`.
