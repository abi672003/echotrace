"""Fetch real Regulations.gov API responses for a docket and cache them for demos/tests.

Usage (from backend/): python scripts\\fetch_sample.py <DOCKET_ID> --max 500
Writes data/samples/<DOCKET_ID>.json with the raw list + per-comment detail payloads
(real API responses only — see AGENTS.md's data rules).
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.sources.regulations_gov import RegulationsGovAdapter  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


async def fetch_sample(docket_id: str, max_comments: int) -> dict:
    adapter = RegulationsGovAdapter()
    try:
        all_ids = await adapter.list_ids(docket_id)
        ids_to_fetch = all_ids[:max_comments]
        comments = [await adapter.fetch_raw(item_id) for item_id in ids_to_fetch]
        return {
            "docket_id": docket_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "remote_comment_count": len(all_ids),
            "comments": comments,
        }
    finally:
        await adapter.aclose()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a real Regulations.gov sample docket.")
    parser.add_argument("docket_id")
    parser.add_argument("--max", type=int, default=500, dest="max_comments")
    args = parser.parse_args()

    sample = await fetch_sample(args.docket_id, args.max_comments)

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SAMPLES_DIR / f"{args.docket_id}.json"
    out_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")

    print(
        f"Saved {len(sample['comments'])} comments "
        f"({sample['remote_comment_count']} available) to {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
