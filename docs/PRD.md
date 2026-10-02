# EchoTrace — Product Requirements Document (MVP)

**One line:** EchoTrace shows when many apparent voices are really one. It finds families of reworded public comments on U.S. government rulemaking dockets, measures how coordinated each family looks, and has an AI agent explain the evidence to a human reviewer.

**Status:** Prototype, free-tier only, no Docker, no model training.
**Companion docs:** `ARCHITECTURE.md` (stack, schema, API, runtime agent), `DESIGN_SYSTEM.md` (UI), `TASKS.md` (build checklist), `AGENTS.md` (rules for the coding agent).

---

## 1. Problem

Government agencies read public comments before finalising rules, and the *number* of people raising a point matters. Organised campaigns have always sent identical form letters, which agencies group with exact-match tools. LLMs now let one actor send thousands of *reworded* versions of the same argument, which exact matching misses, so one voice can look like a crowd.

Single-text AI detectors don't solve this: they are unreliable, especially on paraphrased text, and AI-assisted writing is legitimate anyway. The useful signal is the **family**: many texts with the same meaning, different wording, arriving in a burst, under different names.

## 2. Principles (non-negotiable)

1. **Coordination is the finding, not AI use.** An AI-style score alone never produces a flag.
2. **Evidence, not accusations.** Output says "these 212 comments form one reworded campaign," never "these are fake" or "bots."
3. **Human decides.** The system triages and explains; a reviewer confirms or rejects. Nothing is deleted or hidden.
4. **Inspectable scoring.** Every number in a verdict can be traced to a formula and specific comments.
5. **Real data only.** Demo and evaluation data come from the real Regulations.gov API. Tiny handwritten strings are allowed only inside unit tests.

## 3. Target audience

| User | Need | How they use EchoTrace |
|---|---|---|
| **Comment analyst** (agency staff, primary persona) | Know which comments are one campaign so the argument is read once and counted honestly | Runs a docket analysis, reviews ranked campaign families, confirms/rejects |
| **Civic-tech researcher / journalist** | Evidence of coordinated influence on a specific rule | Checks a docket or a single suspicious comment, exports the evidence |
| **Academic reviewer / portfolio viewer** (demo audience) | See the idea work end to end | Loads a bundled real sample docket, watches the pipeline, inspects a verdict |

## 4. MVP user stories

Each story has acceptance criteria (AC) that tests and demos must satisfy.

**US-1 Add a docket.** As an analyst, I enter a Regulations.gov docket ID and EchoTrace pulls its public comments.
- AC: ingestion runs in the background with visible progress (fetched / total); respects a configurable cap (default 500); skips attachment-only comments and records how many were skipped; can resume after interruption.

**US-2 Load a sample.** As a demo viewer, I load a bundled real docket without an API key or waiting on rate limits.
- AC: one click loads `data/samples/*.json` (real API responses cached by a script); works offline except for AI calls.

**US-3 Analyse a docket.** As an analyst, I start an analysis and watch each pipeline step complete.
- AC: steps shown live (normalise → embed → cluster → measure → AI-style score → aggregate → agent review); failure of one step shows a clear error and which step failed.

**US-4 See ranked campaign families.** As an analyst, I see families ranked by campaign score with their type (reworded campaign / form letter / organic agreement / insufficient evidence).
- AC: each row shows size, reword index, 24-hour burst share, name diversity, AI-style signal, verdict, confidence.

**US-5 Inspect the evidence board.** As an analyst, I open a family and see its representative comment in the centre, members around it, threads encoding similarity.
- AC: thread thickness = meaning similarity; dashed thread = low word overlap (reworded), solid = copied; clicking a member opens a side-by-side comparison with shared phrasing highlighted.

**US-6 Read the agent's explanation.** As an analyst, I read a verdict with rationale that cites specific comments and metrics.
- AC: every cited comment ID exists in that family's retrieved evidence (validated server-side); invalid citations are removed and the verdict is marked "citations corrected"; the agent's step trace is viewable.

**US-7 Check one comment.** As a researcher, I paste a comment, pick an ingested docket, and see whether it belongs to a family.
- AC: returns its nearest family (or "no family found"), the similarity-weighted aggregate, and an agent verdict; a lone comment with a high AI-style score returns "no campaign detected."

**US-8 Record a review.** As an analyst, I mark a family confirmed / rejected / unsure with a note.
- AC: stored with timestamp; review status visible on the list; reviews exportable as CSV (these become the evaluation labels).

## 5. Out of scope for MVP

Account system and multi-user auth (single shared admin token instead) · attachment/PDF text extraction · non-English text · identifying which comment is the "original" · live social-media sources (the source adapter interface allows adding them later) · model training or fine-tuning · any automatic removal or down-ranking.

## 6. Success criteria

- A bundled sample docket analyses end to end in under 5 minutes on free tiers.
- On a docket with known exact form letters, those letters land in one family classed as `form_letter` (sanity check).
- On 30+ human-reviewed families, report precision of the `coordinated_paraphrase_campaign` label (reviews from US-8 are the labels).
- A single-comment check completes in under 30 seconds.
- Zero verdicts in the UI contain uncited or invalid comment IDs.

## 7. Constraints

- **Free tiers only:** Regulations.gov (free api.data.gov key, about 1,000 requests/hour), Gemini API free tier (embeddings + fallback LLM), Groq free tier (primary LLM). Limits change: verify in each provider's console before relying on numbers.
- **Development machine:** Windows 11 company laptop, VS Code, no Docker, Hugging Face blocked. Nothing may download from Hugging Face at runtime or build time.
- **No training:** all intelligence comes from API embeddings, formulas, and LLM calls.

## 8. Known limitations (state these in demos)

- Cannot tell a real organisation's members who each reworded a template apart from one actor using fake names; text alone can't prove identities. The verdict is "one campaign," not "fake people."
- The AI-style signal is an unverified LLM judgement and carries low weight.
- Quality depends on embeddings; very loose paraphrases may be missed, and short comments (<25 words) are excluded from clustering.
- Regulations.gov only exposes text for comments typed into the form; attachment-only comments are skipped.

## 9. Stretch goals (only after MVP is done)

Local offline embedding fallback (TF-IDF + LSA) · CSV/JSON evidence export per family · docket comparison over time · second source adapter (e.g., Bluesky public posts) · "possible template seed" hint (most specific, earliest member).
