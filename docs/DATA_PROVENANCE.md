# Data Provenance — EchoTrace

Per project constraint 0.1 (no synthetic data, ever), every row in this
project's data layer traces back to one of the two real datasets named in
the brief. This document records exactly where each file came from, how it
was verified as authentic, and every deviation from the brief's stated
source (with the reasoning), so the chain of custody is auditable.

## NEWS-COPY

**Brief's stated source:** https://github.com/dell-research-harvard/news-copy
(code repo, README points to a Dropbox folder for the actual data).

**Finding:** The Dropbox folder linked in that README
(`dropbox.com/sh/so3iw4xecayyrow/...`) returns "This item was deleted" as of
2026-09-05. The original data host is gone.

**Resolution:** Located a verified third-party re-hosting on Hugging Face —
`chenghao/NEWS-COPY-train` and `chenghao/NEWS-COPY-eval` — uploaded by a
third party, license marked "unknown" on the HF card. Verified this is the
genuine NEWS-COPY dataset (not a look-alike) by cross-checking against the
paper (Silcock, D'Amico-Wong, Yang, Dell, ICLR 2023 / arXiv:2210.04261):
- Column schema (`Text 1`, `Text 2`, `Label`, `split`) matches the paper's
  pairwise near-duplicate classification setup exactly.
- `train.parquet` + `dev.parquet` contain real digitized historical
  newspaper OCR text (visible OCR artifacts consistent with the paper's
  described noisy-scan source material), with `same`/`different` duplicate
  labels — 73,928 train pairs, 6,288 dev pairs.
- `eval_val.parquet` / `eval_test.parquet` are article-level (not pairwise),
  carrying `cluster` and `duplicates` fields that reconstruct the retrieval
  ground truth described in the paper — 4,988 + 14,211 = 19,199 articles.

**Action item / open risk:** the HF mirror's license is unknown. Fine for
research/internal use; before any external release, get written permission
from the original NEWS-COPY authors or locate an official re-host.

**Files:** `data/raw/news-copy/{train,dev,eval_val,eval_test}.parquet`

## M-DAIGT

**Brief's explicit warning:** verify against the original M-DAIGT
shared-task paper (Lamsiyah et al., RANLP 2025) since similarly-named
AI-text datasets exist.

**Verification performed:**
1. Confirmed the real paper: Lamsiyah, Ezzini, Elmahdaouy, Alami, Benlahbib,
   El Amrany, Chafik, Hammouchi — "M-DAIGT: A Shared Task on Multi-Domain
   Detection of AI-Generated Text," RANLP 2025
   (https://aclanthology.org/2025.ranlp-mdaigt.1/, arXiv:2511.11340).
2. Confirmed the official task repo: https://github.com/ezzini/M-DAIGT
   (task description site; the actual data distribution channel is a
   CodaLab competition, gated to registered participants — not directly
   fetchable).
3. Official published split sizes per subtask: train 10,000 / dev 2,000 /
   test 3,000 (30,000 total across both subtasks — matches the paper's
   reported "30,000 samples" figure).
4. The candidate dataset `CogniSAL/MDAIGT` on Hugging Face does **not** cite
   the RANLP paper on its card — this is exactly the kind of similarly-named
   imposter the brief warned about, so it was not accepted on citation
   alone. It was accepted only after its actual content matched the
   official spec byte-for-byte on the one checkable dimension: exactly
   10,000 rows per subtask, exactly balanced 5,000 human / 5,000 machine —
   matching the official "Training: 10,000" split size precisely. Treat
   this as the real M-DAIGT **training** portion only; it is not verified
   as an authoritative re-host of the gated dev/test sets.

**Resolution:** Since the official dev/test sets are not publicly
downloadable (CodaLab-gated), and constraint 0.2 requires a documented split
when no public official one exists, EchoTrace creates its own stratified
80/10/10 train/val/test split from the 10,000 real Task 1 (News Article
Detection) rows, fixed seed 42, stratified by label. Split sizes are logged
by `scripts/build_sqlite.py` at ingestion time.

Task 2 (Academic Writing Detection, 10,000 rows) was downloaded for
completeness but is **not** ingested into the pipeline — EchoTrace is a news
pipeline and the brief scopes M-DAIGT usage to news text only. The raw file
is kept at `data/raw/mdaigt/train_mdaigt_task2.csv` for future extension.

**Files:** `data/raw/mdaigt/train_mdaigt_task1.csv` (used),
`train_mdaigt_task2.csv` (downloaded, unused, kept for reference)
