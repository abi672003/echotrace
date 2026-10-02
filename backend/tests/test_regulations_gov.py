import pytest
import respx
from httpx import Response
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Docket, Document
from app.services.sources.regulations_gov import REGULATIONS_BASE_URL, ingest_docket

DOCKET_ID = "TEST-DOCKET-0001"

SUBSTANTIVE_TEXT = (
    "I am writing to express my strong opposition to this proposed rule because it "
    "would harm small businesses across the region and fails to consider long-term "
    "economic impacts on our community."
)


def _detail_payload(comment_id: str, text: str) -> dict:
    return {
        "data": {
            "id": comment_id,
            "type": "comments",
            "attributes": {
                "comment": text,
                "firstName": "Jane",
                "lastName": "Doe",
                "organization": None,
                "postedDate": "2024-05-01T12:00:00Z",
                "title": None,
            },
        }
    }


def _mock_routes() -> None:
    respx.get(f"{REGULATIONS_BASE_URL}/comments").mock(
        return_value=Response(
            200,
            json={
                "data": [{"id": cid, "type": "comments", "attributes": {}} for cid in ("c1", "c2", "c3", "c4")],
                "meta": {"hasNextPage": False, "totalElements": 4},
            },
        )
    )
    respx.get(f"{REGULATIONS_BASE_URL}/comments/c1").mock(
        return_value=Response(200, json=_detail_payload("c1", SUBSTANTIVE_TEXT + " First."))
    )
    respx.get(f"{REGULATIONS_BASE_URL}/comments/c2").mock(
        return_value=Response(200, json=_detail_payload("c2", SUBSTANTIVE_TEXT + " Second."))
    )
    respx.get(f"{REGULATIONS_BASE_URL}/comments/c3").mock(
        return_value=Response(200, json=_detail_payload("c3", SUBSTANTIVE_TEXT + " Third."))
    )
    respx.get(f"{REGULATIONS_BASE_URL}/comments/c4").mock(
        return_value=Response(200, json=_detail_payload("c4", "See attached."))
    )


@pytest.mark.asyncio
@respx.mock
async def test_ingest_docket_stores_valid_comments_and_skips_attachment_only() -> None:
    _mock_routes()

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        docket = Docket(id=DOCKET_ID, source="regulations_gov")
        session.add(docket)
        session.commit()
        session.refresh(docket)

        await ingest_docket(session, docket, max_comments=500)

        assert docket.ingest_status == "done"
        assert docket.ingested_count == 3
        assert docket.skipped_count == 1
        assert docket.remote_comment_count == 4
        assert docket.ingest_error is None

        documents = session.exec(select(Document).where(Document.docket_id == DOCKET_ID)).all()
        assert len(documents) == 3
        assert {d.external_id for d in documents} == {"c1", "c2", "c3"}


@pytest.mark.asyncio
@respx.mock
async def test_ingest_docket_second_run_inserts_nothing_new() -> None:
    _mock_routes()

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        docket = Docket(id=DOCKET_ID, source="regulations_gov")
        session.add(docket)
        session.commit()
        session.refresh(docket)

        await ingest_docket(session, docket, max_comments=500)
        await ingest_docket(session, docket, max_comments=500)

        documents = session.exec(select(Document).where(Document.docket_id == DOCKET_ID)).all()
        assert len(documents) == 3
        assert docket.ingested_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_list_ids_deduplicates_across_pages_from_pagination_drift() -> None:
    """On a busy, currently-open docket, a new comment posting mid-fetch can shift the
    postedDate sort order enough that the same id appears on two pages. Discovered for
    real fetching a live sample (Task 2.9) — 'c2' here stands in for that repeat."""

    def _list_response(request):
        page = request.url.params.get("page[number]")
        if page == "1":
            return Response(
                200,
                json={
                    "data": [
                        {"id": cid, "type": "comments", "attributes": {}}
                        for cid in ("c1", "c2", "c3")
                    ],
                    "meta": {"hasNextPage": True, "totalElements": 4},
                },
            )
        return Response(
            200,
            json={
                "data": [
                    {"id": cid, "type": "comments", "attributes": {}}
                    for cid in ("c3", "c4")  # c3 repeats: it drifted onto page 2
                ],
                "meta": {"hasNextPage": False, "totalElements": 4},
            },
        )

    respx.get(f"{REGULATIONS_BASE_URL}/comments").mock(side_effect=_list_response)
    for cid in ("c1", "c2", "c3", "c4"):
        respx.get(f"{REGULATIONS_BASE_URL}/comments/{cid}").mock(
            return_value=Response(200, json=_detail_payload(cid, SUBSTANTIVE_TEXT + f" {cid}."))
        )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        docket = Docket(id=DOCKET_ID, source="regulations_gov")
        session.add(docket)
        session.commit()
        session.refresh(docket)

        # must not raise a UNIQUE-constraint IntegrityError on the drifted duplicate
        await ingest_docket(session, docket, max_comments=500)

        assert docket.ingest_status == "done"
        assert docket.ingested_count == 4
        documents = session.exec(select(Document).where(Document.docket_id == DOCKET_ID)).all()
        assert {d.external_id for d in documents} == {"c1", "c2", "c3", "c4"}
