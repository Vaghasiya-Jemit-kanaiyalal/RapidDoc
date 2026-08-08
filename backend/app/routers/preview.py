import io
import logging

import docx
from bson import ObjectId
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from fastapi.responses import Response

from app.database import db_conn
from app.routers.auth import get_current_user
from app.services.pdf_converter import convert_docx_bytes_to_pdf
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/docs", tags=["preview"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _read_stored_file(doc_id: str, owner_id: str) -> tuple[str, bytes]:
    """Load the current saved file bytes for a document owned by the user."""
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": owner_id})
    except ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error looking up document %s: %s", doc_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Error locating the document.")

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Document not found.")

    try:
        with open(storage_service.get_file_path(doc["storage_path"]), "rb") as fh:
            return doc["file_type"], fh.read()
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Document file is missing on the server.")
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied to the document file.")


def _validate_docx_bytes(content: bytes, filename: str) -> None:
    """Basic validation: extension, size, and that python-docx can open it."""
    if not filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .docx files can be previewed as PDF.",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum limit of 10MB.",
        )

    try:
        docx.Document(io.BytesIO(content))
    except Exception as exc:
        logger.error("Invalid DOCX content received for preview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded document is not a valid DOCX file.",
        )


@router.post("/preview")
async def preview_document(
    doc_id: str = Form(None, description="Document ID to preview the current saved state"),
    file: UploadFile = File(None, description="Edited DOCX file uploaded directly for preview"),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a PDF preview of an edited document.

    Accepts either an in-memory DOCX upload (`file`) or an existing document
    (`doc_id`). DOCX documents are converted to PDF in memory via LibreOffice;
    PDF documents are streamed back directly. Nothing is saved permanently to disk.
    """
    if file is not None:
        content = await file.read()
        _validate_docx_bytes(content, file.filename or "document.docx")
        file_type = "docx"
    elif doc_id:
        file_type, content = _read_stored_file(doc_id, current_user["id"])
        if file_type == "docx":
            _validate_docx_bytes(content, "document.docx")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either an uploaded DOCX file or a doc_id to preview.",
        )

    if file_type == "docx":
        try:
            pdf_bytes = convert_docx_bytes_to_pdf(content)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Unexpected error while generating preview: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while generating the preview.",
            )
    else:
        pdf_bytes = content

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="preview.pdf"',
            "Cache-Control": "no-store",
        },
    )
