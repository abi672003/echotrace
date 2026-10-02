import json
from pathlib import Path

from app.services.sources.base import RawItem
from app.services.sources.regulations_gov import parse_raw_item

SAMPLES_DIR = Path(__file__).resolve().parents[4] / "data" / "samples"


class SampleLoaderAdapter:
    """SourceAdapter that reads a previously-fetched `data/samples/<name>.json` file,
    mapping raw payloads through the exact same `parse_raw_item` used by the live
    Regulations.gov adapter (§2.8/§2.9) — no network access."""

    def __init__(self, sample_name: str, samples_dir: Path = SAMPLES_DIR) -> None:
        self._path = samples_dir / f"{sample_name}.json"
        self._payload: dict | None = None

    def _load(self) -> dict:
        if self._payload is None:
            self._payload = json.loads(self._path.read_text(encoding="utf-8"))
        return self._payload

    async def list_ids(self, scope: str) -> list[str]:
        # De-duplicate defensively: a sample fetched from a busy, currently-open docket
        # can itself contain repeats from pagination drift (see regulations_gov.py).
        seen: dict[str, None] = {}
        for comment in self._load()["comments"]:
            seen[comment["id"]] = None
        return list(seen.keys())

    async def fetch(self, item_id: str) -> RawItem:
        for comment in self._load()["comments"]:
            if comment["id"] == item_id:
                return parse_raw_item(comment)
        raise KeyError(f"No comment {item_id!r} in sample {self._path.name}")
