from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models import Document
from app.schemas import CompareOut, DocumentOut, SharedSpan
from app.services.compare import lexical_similarity, semantic_similarity, shared_spans

router = APIRouter()


def document_to_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        docket_id=document.docket_id,
        external_id=document.external_id,
        title=document.title,
        submitter_label=document.submitter_label,
        submitter_hash=document.submitter_hash,
        organization=document.organization,
        text=document.text,
        word_count=document.word_count,
        posted_at=document.posted_at,
        url=document.url,
        created_at=document.created_at,
    )


@router.get("/documents/compare", response_model=CompareOut)
def compare_documents(a: int, b: int, session: Session = Depends(get_session)) -> CompareOut:
    doc_a = session.get(Document, a)
    doc_b = session.get(Document, b)
    if doc_a is None or doc_b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": "One or both documents not found."},
        )

    settings = get_settings()
    sem = semantic_similarity(session, settings.GEMINI_EMBED_MODEL, doc_a.text_hash, doc_b.text_hash)
    lex = lexical_similarity(doc_a.text, doc_b.text)
    spans = [SharedSpan(**span) for span in shared_spans(doc_a.text, doc_b.text)]

    return CompareOut(a=a, b=b, sem=sem, lex=lex, shared=spans)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, session: Session = Depends(get_session)) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"No document {document_id}."},
        )
    return document_to_out(document)
