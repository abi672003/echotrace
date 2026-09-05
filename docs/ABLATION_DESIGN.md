# Ablation Design: Aggregated vs. Single-Instance Detection

The brief requires an explicit ablation comparing the cross-duplicate
aggregation mechanism against the single-instance baseline, broken down by
rewrite-distance/paraphrase-severity bucket. This document records a real
gap in the available public data and the honest, real-data resolution
chosen — per constraint 0.1, nothing here is synthesized to paper over it.

## The gap

The ideal ablation needs a corpus where the **same underlying story**
appears in multiple near-duplicate copies, **and** each copy carries a real
AI-vs-human generation label, so we can measure whether aggregating across
copies improves true-positive detection of AI-reworded content over
trusting any single copy. No such public dataset exists:

- **NEWS-COPY** has real near-duplicate clusters (wire stories reprinted
  across dozens of newspapers) but every article is genuinely
  human-written historical text — there is no AI-generated variant of any
  of these stories.
- **M-DAIGT** has real AI-vs-human labels but each sample is an
  independent article with no near-duplicate cluster structure.

This is expected: EchoTrace's exact scenario (a story with both
independently-reported and AI-reworded-copy versions in circulation) isn't
a benchmarked task yet, which is part of why the brief frames the
aggregation mechanism as the novel contribution.

## What this ablation actually measures instead

`scripts/run_ablation.py` runs the real M-DAIGT-trained RoBERTa detector
(out-of-domain: it was trained on modern news text, not 1920s–1980s wire
copy) over real NEWS-COPY duplicate clusters, where the true label is known
with certainty to be **human** for every article. This lets us honestly
measure one real, useful thing: **does reliability-weighted aggregation
across genuine duplicate copies reduce the false-positive rate** relative
to trusting a single noisy copy, when the detector is operating under
distribution shift (OCR noise, period-appropriate style, out-of-domain
text)?

This is a specificity/robustness result, not a true-positive-lift result.
Both are reported honestly as what they are — see the script's docstring
and output — rather than presenting one as the other.

**Bucketing:** NEWS-COPY has no explicit "rewrite distance" label. As a
real proxy, each target article is bucketed by its **embedding similarity
to its most similar same-cluster duplicate** (from retrieval): near-1.0
similarity approximates a near-verbatim reprint (low rewrite distance);
lower similarity approximates heavier OCR noise or genuine copy-editing
divergence (higher rewrite distance) — the same continuous signal the
brief's "paraphrase-severity bucket" language is getting at, grounded in
real embedding distances rather than a fabricated label.

## Requires

The fine-tuned RoBERTa detector (`models/echotrace-detector/`, produced by
`notebooks/finetune_roberta_mdaigt.ipynb`) must be present before this
script can run.
