from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.config import get_settings
from app.models import Docket, Document
from app.services.normalize import (
    clean_text,
    is_attachment_only,
    normalize_for_hash,
    submitter_hash,
    text_hash,
    word_count,
)
from app.services.ratelimit import get_bucket, with_retries
from app.services.sources.base import RawItem, SourceAdapter

REGULATIONS_BASE_URL = "https://api.regulations.gov/v4"
# httpx defaults to a 5s timeout; a busy day on Regulations.gov's side can exceed that.
REGULATIONS_HTTP_TIMEOUT = 30.0


class RegulationsGovAdapter:
    """SourceAdapter for the Regulations.gov API v4 (§4.1)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.REGULATIONS_API_KEY.get_secret_value()
        self._client = client or httpx.AsyncClient(
            base_url=REGULATIONS_BASE_URL, timeout=REGULATIONS_HTTP_TIMEOUT
        )
        self._bucket = get_bucket("regulations")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_ids(self, scope: str) -> list[str]:
        # A dict-as-ordered-set: on a busy, currently-open docket, new comments can post
        # between page requests and shift the postedDate sort order, so the same id can
        # legitimately appear on more than one page ("pagination drift"). De-duplicating
        # here, once, means every caller can trust list_ids() never repeats an id.
        seen: dict[str, None] = {}
        page = 1
        while True:
            await self._bucket.acquire()

            async def _request() -> httpx.Response:
                return await self._client.get(
                    "/comments",
                    params={
                        "filter[docketId]": scope,
                        "page[size]": 250,
                        "page[number]": page,
                        "sort": "postedDate",
                    },
                    headers={"X-Api-Key": self._api_key},
                )

            response = await with_retries(_request)
            response.raise_for_status()
            payload = response.json()
            for item in payload["data"]:
                seen[item["id"]] = None
            if not payload.get("meta", {}).get("hasNextPage"):
                break
            page += 1
        return list(seen.keys())

    async def fetch_raw(self, item_id: str) -> dict:
        """Return the raw `data` object from `GET /comments/{id}`, unparsed."""
        await self._bucket.acquire()

        async def _request() -> httpx.Response:
            return await self._client.get(
                f"/comments/{item_id}", headers={"X-Api-Key": self._api_key}
            )

        response = await with_retries(_request)
        response.raise_for_status()
        return response.json()["data"]

    async def fetch(self, item_id: str) -> RawItem:
        return parse_raw_item(await self.fetch_raw(item_id))


def parse_raw_item(data: dict) -> RawItem:
    """Map one raw `GET /comments/{id}` `data` object to a `RawItem` (shared with `sample_loader.py`)."""
    item_id = data["id"]
    attributes = data["attributes"]

    first_name = (attributes.get("firstName") or "").strip()
    last_name = (attributes.get("lastName") or "").strip()
    display_name = " ".join(part for part in (first_name, last_name) if part) or "Anonymous"

    posted_at: datetime | None = None
    posted_raw = attributes.get("postedDate")
    if posted_raw:
        posted_at = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))

    return RawItem(
        external_id=item_id,
        title=attributes.get("title"),
        submitter_label=display_name,
        organization=attributes.get("organization") or None,
        text=attributes.get("comment") or "",
        posted_at=posted_at,
        url=f"https://www.regulations.gov/comment/{item_id}",
    )


def map_raw_item_to_document(docket_id: str, item: RawItem) -> Document:
    normalized = normalize_for_hash(item.text)
    label = item.submitter_label or "Anonymous"
    return Document(
        docket_id=docket_id,
        external_id=item.external_id,
        title=item.title,
        submitter_label=label,
        submitter_hash=submitter_hash(label),
        organization=item.organization,
        text=clean_text(item.text),
        text_hash=text_hash(normalized),
        word_count=word_count(normalized),
        posted_at=item.posted_at,
        url=item.url,
    )


async def ingest_docket(
    session: Session,
    docket: Docket,
    max_comments: int,
    adapter: SourceAdapter | None = None,
) -> None:
    """Ingest up to `max_comments` total comments for `docket`, resuming past prior runs
    (external ids already stored as `Document` rows are skipped)."""
    owns_adapter = adapter is None
    adapter = adapter or RegulationsGovAdapter()

    docket.ingest_status = "running"
    docket.ingest_error = None
    session.add(docket)
    session.commit()

    try:
        all_ids = await adapter.list_ids(docket.id)
        docket.remote_comment_count = len(all_ids)

        already_stored = set(
            session.exec(select(Document.external_id).where(Document.docket_id == docket.id))
        )
        remaining_budget = max(0, max_comments - len(already_stored))
        to_fetch = [item_id for item_id in all_ids if item_id not in already_stored][:remaining_budget]

        for external_id in to_fetch:
            item = await adapter.fetch(external_id)
            if is_attachment_only(item.text):
                docket.skipped_count += 1
                continue
            session.add(map_raw_item_to_document(docket.id, item))
            docket.ingested_count += 1

        covered = len(already_stored) + len(to_fetch)
        docket.ingest_status = "done" if covered >= len(all_ids) else "partial"
    except Exception as exc:  # noqa: BLE001 - reported visibly on the Docket, per AGENTS.md
        docket.ingest_status = "failed"
        docket.ingest_error = str(exc)
    finally:
        docket.last_ingested_at = datetime.now(timezone.utc)
        session.add(docket)
        session.commit()
        if owns_adapter:
            await adapter.aclose()  # type: ignore[union-attr]
