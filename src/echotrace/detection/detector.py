"""Single-instance AI-text detector: RoBERTa fine-tuned on M-DAIGT.

Per constraint 0.3, loaded from a local folder path only — never a Hugging
Face hub string — so this never attempts a network call. The folder is
populated by running notebooks/finetune_roberta_mdaigt.ipynb in Colab and
copying its output here (see that notebook's final cell).

This step alone is intentionally not novel — it's the established
single-instance baseline that src/echotrace/aggregation builds on.
"""

from pathlib import Path

import torch
from transformers import RobertaForSequenceClassification, RobertaTokenizerFast

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "echotrace-detector"

_model = None
_tokenizer = None

# Matches label2id in notebooks/finetune_roberta_mdaigt.ipynb
MACHINE_LABEL_INDEX = 1


def _ensure_loaded():
    global _model, _tokenizer
    if _model is not None:
        return
    if not (MODEL_PATH / "config.json").exists():
        raise FileNotFoundError(
            f"No fine-tuned model found at {MODEL_PATH}. Run "
            "notebooks/finetune_roberta_mdaigt.ipynb in Colab and copy its "
            "output folder here — see constraint 0.3 in the project brief."
        )
    _tokenizer = RobertaTokenizerFast.from_pretrained(str(MODEL_PATH))
    _model = RobertaForSequenceClassification.from_pretrained(str(MODEL_PATH))
    _model.eval()


def score_text(text: str) -> float:
    """Return P(machine-generated) for a single article, in [0, 1]."""
    _ensure_loaded()
    inputs = _tokenizer(text, truncation=True, max_length=512, padding=True, return_tensors="pt")
    with torch.no_grad():
        logits = _model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)
    return probs[0, MACHINE_LABEL_INDEX].item()


def score_texts(texts: list[str]) -> list[float]:
    return [score_text(t) for t in texts]
