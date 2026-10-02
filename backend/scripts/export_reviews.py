"""Export reviews (with cluster metrics) to CSV for a docket, reusing the exact CSV
construction `GET /reviews/export.csv` uses.

Usage (from backend/): python scripts\\export_reviews.py <DOCKET_ID> [--out reviews.csv]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from app.db import engine  # noqa: E402
from app.routers.clusters import build_reviews_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reviews to CSV.")
    parser.add_argument("docket_id")
    parser.add_argument("--out", default="reviews.csv")
    args = parser.parse_args()

    with Session(engine) as session:
        csv_text = build_reviews_csv(session, args.docket_id)

    Path(args.out).write_text(csv_text, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
