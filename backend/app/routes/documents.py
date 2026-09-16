"""Ops knowledge-base document endpoints.

POST   /documents        - upload a document (admin only): chunks the text,
                            embeds each chunk, stores it for semantic search.
GET    /documents         - list document metadata (any authenticated role).
GET    /documents/{id}    - get one document's metadata.
DELETE /documents/{id}    - delete a document and its chunks (admin only).

Content is never stored raw beyond its chunks — Document rows are metadata
and a citation anchor only; DocumentChunk rows are the only copy of the
actual text, and they're what backend.app.agent.tools.search_documents
searches over.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.agent.chunking import chunk_text
from backend.app.agent.embeddings_client import EmbeddingsClient
from backend.app.agent.exceptions import EmbeddingProviderError
from backend.app.auth import ROLE_ADMIN, get_current_user, require_role
from backend.app.database import get_db
from backend.app.models.document import Document
from backend.app.models.document_chunk import DocumentChunk
from backend.app.models.user import User
from backend.app.schemas.document import DocumentResponse, DocumentUploadRequest

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("backend.app.documents")


def get_embeddings_client() -> EmbeddingsClient:
    """FastAPI dependency, overridden in tests with a fake client."""
    try:
        return EmbeddingsClient()
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _to_response(document: Document, chunk_count: int) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        title=document.title,
        source=document.source,
        uploaded_by=document.uploaded_by,
        created_at=document.created_at,
        chunk_count=chunk_count,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    request: DocumentUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
    embeddings_client: EmbeddingsClient = Depends(get_embeddings_client),
):
    chunks = chunk_text(request.content)

    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document content is empty.")

    try:
        vectors = embeddings_client.embed(chunks, input_type="document")
    except EmbeddingProviderError as exc:
        logger.error("documents.upload.embedding_failed", extra={"user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    document = Document(title=request.title, source=request.source, uploaded_by=current_user.id)
    db.add(document)
    db.flush()

    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                chunk_text=chunk,
                embedding=vector,
            )
        )

    db.commit()
    db.refresh(document)

    logger.info(
        "documents.upload.created",
        extra={"user_id": current_user.id, "document_id": document.id, "chunk_count": len(chunks)},
    )

    return _to_response(document, len(chunks))


@router.get("", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    documents = db.query(Document).order_by(Document.created_at.desc()).all()

    return [
        _to_response(
            document,
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count(),
        )
        for document in documents
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
    return _to_response(document, chunk_count)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(ROLE_ADMIN)),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    db.delete(document)
    db.commit()
