import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Docket, Document
from app.services.sources.regulations_gov import ingest_docket
from app.services.sources.sample_loader import SampleLoaderAdapter

SUBSTANTIVE_TEXT = (
    "I am writing to express my strong opposition to this proposed rule because it "
    "would harm small businesses across the region and fails to consider long-term "
    "economic impacts on our community."
)


def _write_sample(dir_path: Path) -> None:
    payload = {
        "docket_id": "SAMPLE-DOCKET-0001",
        "fetched_at": "2024-05-01T00:00:00+00:00",
        "remote_comment_count": 2,
        "comments": [
            {
                "id": "s1",
                "type": "comments",
                "attributes": {
                    "comment": SUBSTANTIVE_TEXT + " First.",
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "organization": None,
                    "postedDate": "2024-05-01T12:00:00Z",
                    "title": None,
                },
            },
            {
                "id": "s2",
                "type": "comments",
                "attributes": {
                    "comment": "See attached.",
                    "firstName": None,
                    "lastName": None,
                    "organization": None,
                    "postedDate": "2024-05-02T12:00:00Z",
                    "title": None,
                },
            },
        ],
    }
    (dir_path / "SAMPLE-DOCKET-0001.json").write_text(json.dumps(payload), encoding="utf-8")


def test_sample_loader_lists_and_fetches(tmp_path: Path) -> None:
    _write_sample(tmp_path)
    adapter = SampleLoaderAdapter("SAMPLE-DOCKET-0001", samples_dir=tmp_path)

    import asyncio

    ids = asyncio.run(adapter.list_ids("SAMPLE-DOCKET-0001"))
    assert ids == ["s1", "s2"]

    item = asyncio.run(adapter.fetch("s1"))
    assert item.external_id == "s1"
    assert item.submitter_label == "Jane Doe"
    assert "First." in item.text


def test_sample_loader_fetch_unknown_id_raises(tmp_path: Path) -> None:
    _write_sample(tmp_path)
    adapter = SampleLoaderAdapter("SAMPLE-DOCKET-0001", samples_dir=tmp_path)

    import asyncio

    with pytest.raises(KeyError):
        asyncio.run(adapter.fetch("does-not-exist"))


@pytest.mark.asyncio
async def test_ingest_docket_works_with_sample_loader_adapter(tmp_path: Path) -> None:
    _write_sample(tmp_path)
    adapter = SampleLoaderAdapter("SAMPLE-DOCKET-0001", samples_dir=tmp_path)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        docket = Docket(id="SAMPLE-DOCKET-0001", source="sample")
        session.add(docket)
        session.commit()
        session.refresh(docket)

        await ingest_docket(session, docket, max_comments=500, adapter=adapter)

        assert docket.ingest_status == "done"
        assert docket.ingested_count == 1
        assert docket.skipped_count == 1

        documents = session.exec(
            select(Document).where(Document.docket_id == "SAMPLE-DOCKET-0001")
        ).all()
        assert len(documents) == 1
        assert documents[0].external_id == "s1"


def test_sample_loader_list_ids_deduplicates_repeated_entries(tmp_path: Path) -> None:
    """A sample file fetched from a busy, currently-open docket can itself contain a
    repeated comment id (pagination drift during the original fetch — see Task 2.9's
    real-world case in docs/NOTES.md). list_ids() must still return each id once."""
    payload = {
        "docket_id": "DRIFT-DOCKET",
        "fetched_at": "2024-05-01T00:00:00+00:00",
        "remote_comment_count": 2,
        "comments": [
            {"id": "d1", "type": "comments", "attributes": {"comment": SUBSTANTIVE_TEXT}},
            {"id": "d2", "type": "comments", "attributes": {"comment": SUBSTANTIVE_TEXT}},
            {"id": "d1", "type": "comments", "attributes": {"comment": SUBSTANTIVE_TEXT}},
        ],
    }
    (tmp_path / "DRIFT-DOCKET.json").write_text(json.dumps(payload), encoding="utf-8")
    adapter = SampleLoaderAdapter("DRIFT-DOCKET", samples_dir=tmp_path)

    import asyncio

    ids = asyncio.run(adapter.list_ids("DRIFT-DOCKET"))
    assert ids == ["d1", "d2"]
