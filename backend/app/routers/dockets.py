import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import engine, get_session
from app.models import Docket, Document
from app.routers.documents import document_to_out
from app.schemas import DocketCreate, DocketOut, DocumentListOut, SampleOut
from app.security import require_admin
from app.services.sources.regulations_gov import ingest_docket
from app.services.sources.sample_loader import SAMPLES_DIR, SampleLoaderAdapter

router = APIRouter()


def docket_to_out(docket: Docket) -> DocketOut:
    return DocketOut(
        id=docket.id,
        agency_id=docket.agency_id,
        title=docket.title,
        source=docket.source,
        remote_comment_count=docket.remote_comment_count,
        ingested_count=docket.ingested_count,
        skipped_count=docket.skipped_count,
        ingest_status=docket.ingest_status,
        ingest_error=docket.ingest_error,
        last_ingested_at=docket.last_ingested_at,
        created_at=docket.created_at,
    )


async def _run_ingest(docket_id: str, max_comments: int) -> None:
    with Session(engine) as session:
        docket = session.get(Docket, docket_id)
        if docket is None:
            return
        await ingest_docket(session, docket, max_comments)


async def _run_sample_ingest(docket_id: str, sample_name: str) -> None:
    with Session(engine) as session:
        docket = session.get(Docket, docket_id)
        if docket is None:
            return
        adapter = SampleLoaderAdapter(sample_name, samples_dir=SAMPLES_DIR)
        await ingest_docket(session, docket, max_comments=10_000, adapter=adapter)


@router.get("/dockets", response_model=list[DocketOut])
def list_dockets(session: Session = Depends(get_session)) -> list[DocketOut]:
    dockets = session.exec(select(Docket).order_by(Docket.created_at.desc())).all()
    return [docket_to_out(d) for d in dockets]


@router.post(
    "/dockets",
    response_model=DocketOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
def create_docket(
    body: DocketCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> DocketOut:
    docket = session.get(Docket, body.docket_id)
    if docket is None:
        docket = Docket(id=body.docket_id, source="regulations_gov")
        session.add(docket)
        session.commit()
        session.refresh(docket)

    background_tasks.add_task(_run_ingest, docket.id, body.max_comments)
    return docket_to_out(docket)


@router.get("/samples", response_model=list[SampleOut])
def list_samples() -> list[SampleOut]:
    samples: list[SampleOut] = []
    if SAMPLES_DIR.exists():
        for path in sorted(SAMPLES_DIR.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            samples.append(
                SampleOut(
                    name=path.stem,
                    docket_id=payload.get("docket_id", path.stem),
                    count=len(payload.get("comments", [])),
                )
            )
    return samples


@router.post(
    "/dockets/samples/{sample_name}",
    response_model=DocketOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_docket_from_sample(
    sample_name: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> DocketOut:
    sample_path = SAMPLES_DIR / f"{sample_name}.json"
    if not sample_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "sample_not_found", "message": f"No sample named {sample_name!r}."},
        )
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    docket_id = payload.get("docket_id", sample_name)

    docket = session.get(Docket, docket_id)
    if docket is None:
        docket = Docket(id=docket_id, source="sample")
        session.add(docket)
        session.commit()
        session.refresh(docket)

    background_tasks.add_task(_run_sample_ingest, docket.id, sample_name)
    return docket_to_out(docket)


@router.get("/dockets/{docket_id}", response_model=DocketOut)
def get_docket(docket_id: str, session: Session = Depends(get_session)) -> DocketOut:
    docket = session.get(Docket, docket_id)
    if docket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "docket_not_found", "message": f"No docket {docket_id!r}."},
        )
    return docket_to_out(docket)


@router.get("/dockets/{docket_id}/documents", response_model=DocumentListOut)
def list_docket_documents(
    docket_id: str,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> DocumentListOut:
    statement = select(Document).where(Document.docket_id == docket_id)
    if q:
        statement = statement.where(Document.text.contains(q))
    total = len(session.exec(statement).all())
    items = session.exec(statement.order_by(Document.posted_at).offset(offset).limit(limit)).all()
    return DocumentListOut(items=[document_to_out(d) for d in items], total=total)
