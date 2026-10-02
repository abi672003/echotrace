from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawItem:
    external_id: str
    title: str | None
    submitter_label: str
    organization: str | None
    text: str
    posted_at: datetime | None
    url: str | None


class SourceAdapter(Protocol):
    """A pluggable source of public comments for a docket (or other scope)."""

    async def list_ids(self, scope: str) -> list[str]:
        """Return every external id available for `scope` (e.g. a docket id)."""
        ...

    async def fetch(self, item_id: str) -> RawItem:
        """Fetch one item's full content by its external id."""
        ...
