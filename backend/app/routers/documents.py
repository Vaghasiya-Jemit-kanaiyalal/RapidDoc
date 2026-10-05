from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, status
from RapidDoc.backend.app.services.pdf_converter import prewarm_docx_preview
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from typing import Optional
from bson import ObjectId
from datetime import datetime
from urllib.parse import quote
import os
import logging
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from RapidDoc.backend.app.database import db_conn
from RapidDoc.backend.app.routers.auth import get_current_user
from RapidDoc.backend.app.services.storage import storage_service
from RapidDoc.backend.app.services.docx_editor import (
    apply_docx_styling, get_docx_images_count, get_docx_content, update_docx_content, find_replace_docx,
    find_text_variants, selective_replace_docx, iter_docx_body_items, get_docx_image_parts,
    get_docx_document_view, replace_docx_images, resize_docx_images
)
from RapidDoc.backend.app.services.pdf_editor import (
    apply_pdf_styling, get_pdf_images_count, get_pdf_content, update_pdf_content, find_replace_pdf,
    find_text_variants_pdf, selective_replace_pdf, replace_pdf_images, resize_pdf_images
)
from RapidDoc.backend.app.services.image_resolver import (
    build_image_inventory,
    read_and_validate_image,
    resolve_image_targets,
    _public_inventory,
)
from RapidDoc.backend.app.services.gemini_service import (
    generate_mcqs, summarize_document, understand_command, rewrite_text
)
from RapidDoc.backend.app.services.export_service import (
    build_docx_bytes_with_status, build_pdf_bytes,
    build_txt_bytes_with_status, build_pptx_bytes_with_status,
    get_document_image_bytes, get_document_images
)
from RapidDoc.backend.app.services.version_history import (
    find_version, list_versions, restore_version, snapshot_version,
)
from RapidDoc.backend.app.services.summary_export import (
    SUPPORTED_FORMATS as SUPPORTED_SUMMARY_FORMATS,
    build_summary_bytes,
)
from RapidDoc.backend.app.models import DocumentMetadata, ContentUpdateRequest, FindReplaceRequest, AICommandRequest, FindVariantsRequest, SelectiveReplaceRequest, HeaderFooterRequest, PipelineUpdateRequest, RewriteRequest, SummarizeRequest, GenerateMCQRequest, ImageResizeRequest, SummaryExportRequest

logger = logging.getLogger(__name__)

_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


class DocumentIdRoute(APIRoute):
    """Reject a malformed `doc_id` before the handler runs.

    Every handler starts with `ObjectId(doc_id)`, which raises `InvalidId` for
    anything that is not 24 hex characters. That surfaced as an HTTP 500 from
    all sixteen document endpoints (`xyz`, `../../etc/passwd`, ...) because the
    raise was caught by the generic `except Exception` arm. A syntactically
    impossible id is a client mistake, so it gets the same 404 as an id that is
    well formed but not this user's - which also avoids telling an attacker
    which ids exist.
    """

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            doc_id = request.path_params.get("doc_id")
            if doc_id is not None and not _OBJECT_ID_RE.match(doc_id):
                return JSONResponse(status_code=404, content={"detail": "Document not found"})
            return await original(request)

        return handler


router = APIRouter(prefix="/api/documents", tags=["documents"], route_class=DocumentIdRoute)

# Secure list of allowed extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

# The upload UI advertises 15 MB; the API used to reject anything over 10 MB,
# so a 10-15 MB file uploaded fine and then failed its very first preview with
# a limit error that a retry could never fix. Both limits must agree.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _content_disposition(filename: str) -> str:
    """Attachment header that survives non-ASCII names.

    A raw f-string header raises UnicodeEncodeError for anything outside
    latin-1 (em dashes, arrows, CJK, emoji), which the export endpoint's blanket
    exception handler turned into a 500. RFC 5987's filename* carries the real
    name and an ASCII fallback keeps old clients happy.
    """
    safe = "".join(ch for ch in filename if ch not in '"\\\r\n')
    try:
        safe.encode("ascii")
        return f'attachment; filename="{safe}"'
    except UnicodeEncodeError:
        ascii_fallback = "".join(
            ch if ord(ch) < 128 else "_" for ch in safe
        ) or "document"
        return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe)}"


def validate_file(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Only {', '.join(ALLOWED_EXTENSIONS)} are allowed."
        )
    return ext


def verify_upload_bytes(content: bytes, ext: str) -> None:
    """Reject an upload whose bytes are not really the format it claims.

    The extension check alone let an empty file and a plain-text file renamed to
    `.docx` through with HTTP 200. Both were stored and registered, then failed
    with HTTP 500 on every later read (content, txt/pptx export), and a corrupt
    DOCX was even handed to LibreOffice, which cheerfully produced a 13 KB PDF
    of nothing. Rejecting here keeps bad bytes out of storage and the database.
    """
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty."
        )

    if not _probe_file(content, ext.lstrip(".")):
        expected = "PDF" if ext.lower() == ".pdf" else "Word (.docx)"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This file is not a valid {expected} document. "
                "The extension does not match the file's contents."
            )
        )

    if ext.lower() == ".pdf":
        # The magic bytes alone are not enough: a truncated or hand-written file
        # starts with "%PDF-" and then fails on every later read, which is the
        # same dead end this check exists to prevent. Opening it is lazy, so this
        # costs almost nothing on a real upload.
        try:
            import fitz

            with fitz.open(stream=content, filetype="pdf") as probe:
                if probe.page_count < 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="This PDF contains no pages.",
                    )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This .pdf file is corrupt and cannot be opened. "
                       "The file may be incomplete or damaged.",
            )

    if ext.lower() == ".docx":
        # A DOCX is a ZIP that must contain the main document part. The magic
        # bytes alone also match any old ZIP, and a ZIP that is not a Word file
        # fails just as hard later on.
        import zipfile
        from io import BytesIO
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This .docx file is corrupt and cannot be opened as a Word document."
            )
        if "word/document.xml" not in names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file is a ZIP archive but not a Word (.docx) document."
            )


# ---------------------------------------------------------------------------
# Text extraction helpers (shared by summarize / generate-mcq / ai-command)
# ---------------------------------------------------------------------------

def _readable_units(file_path: str, file_type: str) -> list:
    """Ordered (label, text) units of readable content in a document.

    PDF  -> one unit per page, label "page N".
    DOCX -> one unit per non-empty paragraph, plus one unit per table row.

    The DOCX branch used to read only ``get_docx_content()``, i.e. just
    ``doc.paragraphs``. Every table was thrown away - and the AWDF practicals
    keep essentially all of their prose inside a table, so a document with 3,100
    characters of usable text was reported as 61 characters. Downstream that is
    fatal: the MCQ builder needs 120 characters, so it refused with "this
    document does not have enough readable text" on a document that was almost
    entirely text. Summarize, rewrite and the AI-command intents all read
    through this same helper, so they were starved of content for the same
    reason.

    Reading the ordered body stream instead keeps the units in true document
    order (a heading is summarised *before* the section it introduces) and
    picks up table text in the right place. Tables contribute one unit per row
    rather than one giant blob, so each row's label ("table 0 row 2") is
    reported back to the AI and citations point at the right place.
    """
    if file_type == "docx":
        units = []
        for kind, payload in iter_docx_body_items(file_path):
            if kind == "paragraph":
                text = (payload.get("text") or "").strip()
                if text:
                    units.append((f"paragraph {payload.get('index')}", text))
            elif kind == "table":
                for row_no, row in enumerate(payload.get("rows") or []):
                    # A merged or heavily padded row can be mostly empty
                    # whitespace; keep only rows with something to say.
                    cells = [str(c or "").strip() for c in row]
                    # Newline, not space: a label cell and its value cell are
                    # separate units of content. Joining with a space produced
                    # "Objective To set up a React development environment",
                    # which then became a question stem with a heading glued on.
                    line = "\n".join(c for c in cells if c).strip()
                    if line:
                        units.append((f"table {payload.get('table_index')} row {row_no}", line))
        return units

    units = []
    for page in get_pdf_content(file_path):
        blocks = page.get("blocks") or []
        text = "\n".join(
            (b.get("text") or "").strip() for b in blocks if (b.get("text") or "").strip()
        ).strip()
        if text:
            units.append((f"page {page.get('page_num')}", text))
    return units


def _document_text(file_path: str, file_type: str) -> str:
    """Whole-document plain text, or "" when nothing readable was found."""
    return "\n\n".join(text for _, text in _readable_units(file_path, file_type)).strip()


def _explicit_text(request) -> str:
    """Caller-supplied text, or "" to signal "use the document".

    A text field that is present but blank is almost always a client bug, so it
    is rejected instead of silently summarising the entire document instead.
    """
    if request.text is None:
        return ""
    text = request.text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="'text' was provided but is empty. Omit it to use the document.",
        )
    return text


def _unit_text(file_path: str, file_type: str, which) -> str:
    """Text of a single unit.

    `which` is a 1-based page number for PDFs and a 0-based paragraph index
    for DOCX. Returns (text, label) or (None, None) when out of range or blank.
    """
    try:
        target = int(which)
    except (TypeError, ValueError):
        return None, None

    # Match on the unit's own label rather than its position in the list: for
    # DOCX, `which` is the original paragraph index, so blank paragraphs earlier
    # in the document must not shift which paragraph the caller asked for.
    label = f"page {target}" if file_type == "pdf" else f"paragraph {target}"
    if file_type == "docx" and target < 0:
        return None, None

    for unit_label, text in _readable_units(file_path, file_type):
        if unit_label == label:
            return text, unit_label
    return None, None


def ensure_edited_version(doc: dict, db, action: Optional[str] = None) -> dict:
    """Copy-on-write preserving the uploaded original file.

    The first edit that rewrites a file creates a new 'edited' copy and records
    the uploaded file in `original_storage_path`. All later edits keep applying
    to the edited copy, so the user's original document is never destroyed.

    `action` names the change about to run. Once a document is already in edited
    mode this copy is the only remaining record of the state that change is about
    to overwrite, so it is snapshotted into the version timeline - that is what
    makes an individual edit reversible from the UI. On the first edit there is
    nothing to snapshot: the copy being made *is* the original.

    Returns the (path, fields) tuple: the active writable path and the metadata
    fields to persist in MongoDB.
    """
    if doc.get("original_storage_path"):
        if action:
            snapshot_version(db, doc, action)
        return storage_service.get_file_path(doc["storage_path"]), {}

    orig_path = storage_service.get_file_path(doc["storage_path"])
    with open(orig_path, "rb") as fh:
        data = fh.read()
    ext = "." + doc["file_type"]
    new_path = storage_service.save_file(f"edited{ext}", data)

    fields = {
        "storage_path": new_path,
        "original_storage_path": doc["storage_path"],
        "has_edited_version": True,
    }
    return new_path, fields

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user)
):
    ext = validate_file(file.filename)

    # Read in chunks rather than one `await file.read()`. A 15MB upload became a
    # single 15MB bytes object plus a second copy inside save_file; streaming
    # keeps peak memory flat. UploadFile.read() is a coroutine returning bytes
    # (not an async iterator), so drain it until it comes back empty.
    buffer = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buffer.extend(chunk)
        # Bail out as soon as the cap is passed rather than buffering an
        # unbounded upload into memory.
        if len(buffer) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds the maximum limit of 15MB."
            )

    content = bytes(buffer)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum limit of 15MB."
        )

    # Confirm the bytes match the extension before anything is written to disk.
    verify_upload_bytes(content, ext)

    try:
        # Save to local storage
        storage_path = storage_service.save_file(file.filename, content)

        # Build DB document metadata (no upload timestamp, upload_date YYYY-MM-DD only)
        upload_date_str = datetime.now().strftime("%Y-%m-%d")

        doc_metadata = {
            "name": file.filename,
            "file_type": ext.lstrip("."),
            "storage_path": storage_path,
            "owner_id": current_user["id"],
            "upload_date": upload_date_str,
            "images_count": 0,
            "pipeline_stage": 1,
            "pipeline_status": "In Progress",
            "completion_percent": 25,
            "last_edited_date": upload_date_str,
            "draft_edits": {},
            "edit_history": [
                {
                    "date": upload_date_str,
                    "action": "Uploaded document & started editing pipeline"
                }
            ]
        }

        db = db_conn.get_db()
        result = db.documents.insert_one(doc_metadata)

        doc_id = str(result.inserted_id)

        # Counting images means opening and walking the whole file. It used to run
        # inline, so the browser sat on a spinner for the length of a full parse
        # before it got an id it could start using. Do it after the response.
        if background_tasks is not None:
            background_tasks.add_task(
                _backfill_image_count, doc_id, storage_path, ext
            )
            # Render the first PDF preview now, in the background. Opening the
            # document then reads the cache instead of waiting 10-25s on a cold
            # LibreOffice run.
            if ext.lower().lstrip(".") == "docx":
                background_tasks.add_task(prewarm_docx_preview, content)

        doc_metadata["id"] = doc_id
        doc_metadata.pop("_id", None)

        return doc_metadata
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error uploading file: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save file metadata."
        )

@router.get("")
async def get_documents(current_user: dict = Depends(get_current_user)):
    try:
        db = db_conn.get_db()
        cursor = db.documents.find({"owner_id": current_user["id"]})
        documents = []
        for doc in cursor:
            doc["id"] = str(doc["_id"])
            doc.pop("_id", None)
            documents.append(doc)
        return documents
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error listing documents: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving documents."
        )

@router.delete("/history")
async def clear_document_history(current_user: dict = Depends(get_current_user)):
    """Permanently remove every document owned by the current user: delete the
    stored files (active + edited copies) from disk and drop the MongoDB records."""
    try:
        db = db_conn.get_db()
        docs = list(db.documents.find({"owner_id": current_user["id"]}))
        deleted_files = 0
        for doc in docs:
            for field in ("storage_path", "original_storage_path"):
                path = doc.get(field)
                if path:
                    try:
                        storage_service.delete_file(path)
                        deleted_files += 1
                    except Exception as fe:
                        logger.warning("Could not delete file %s: %s", path, fe)
        result = await run_in_threadpool(
            db.documents.delete_many, {"owner_id": current_user["id"]}
        )
        logger.info(
            "Cleared history for user %s: %d docs, %d files",
            current_user["id"], result.deleted_count, deleted_files,
        )
        return {"deleted_documents": result.deleted_count, "deleted_files": deleted_files}
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error clearing document history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error clearing document history."
        )

@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        return FileResponse(
            path=file_path,
            filename=doc["name"],
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error downloading file: %s", e)
        raise HTTPException(status_code=404, detail="Document file not found or inaccessible.")

def _export_headers(filename: str, cached: bool) -> dict:
    """Response headers for a converted export.

    ``X-Export-Cache`` lets the client tell the user why a repeat export was
    instant instead of leaving them wondering whether anything happened.
    """
    headers = {"Content-Disposition": _content_disposition(filename)}
    headers["X-Export-Cache"] = "hit" if cached else "miss"
    return headers


def _probe_file(data: bytes, fmt: str) -> bool:
    """Verify the bytes actually match the format being served, so browsers
    never receive a mismatched/corrupt file that cannot be opened."""
    if fmt == "pdf":
        return data[:5] == b"%PDF-"
    if fmt in ("docx", "pptx"):
        return data[:4] == b"PK\x03\x04"
    return True


@router.get("/export/themes")
async def list_export_themes(current_user: dict = Depends(get_current_user)):
    """Slide themes available for PPTX export, so the client can offer a picker."""
    from RapidDoc.backend.app.services.ppt_templates import (
        DEFAULT_THEME,
        available_themes,
    )

    return {"default": DEFAULT_THEME, "themes": available_themes()}


@router.get("/{doc_id}/export")
async def export_document(
    doc_id: str,
    format: str = Query("original", description="original | pdf | docx | txt | pptx"),
    theme: Optional[str] = Query(None, description="PPTX slide theme: modern | corporate | minimal"),
    force: bool = Query(False, description="Skip the PPTX suitability pre-check"),
    current_user: dict = Depends(get_current_user)
):
    """Download the document in one of the supported export formats:
    'original' (native file), 'pdf', 'docx', 'txt' or 'pptx'.

    `theme` selects the slide template set for PPTX exports; an unknown name
    falls back to the default rather than failing the download.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        fmt = (format or "original").lower()
        file_path = storage_service.get_file_path(doc["storage_path"])

        base, _ = os.path.splitext(doc["name"])

        if fmt == "original":
            media = "application/pdf" if doc["file_type"] == "pdf" \
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if not os.path.isfile(file_path):
                raise HTTPException(status_code=404, detail="Document file is missing on disk.")
            with open(file_path, "rb") as fh:
                raw = fh.read(8)
            if not _probe_file(raw, doc["file_type"]):
                raise HTTPException(status_code=409, detail="The stored file is corrupt and cannot be downloaded.")
            return FileResponse(path=file_path, filename=doc["name"], media_type=media)

        if fmt == "pdf":
            data = await run_in_threadpool(build_pdf_bytes, file_path, doc["file_type"])
            if not _probe_file(data, "pdf"):
                raise HTTPException(status_code=422, detail="PDF conversion failed; the output is not a valid PDF file.")
            return Response(content=data, media_type="application/pdf",
                            headers={"Content-Disposition": _content_disposition(f"{base}.pdf")})

        if fmt == "docx":
            data, cached = await run_in_threadpool(
                build_docx_bytes_with_status, file_path, doc["file_type"], "")
            if not _probe_file(data, "docx"):
                raise HTTPException(status_code=422, detail="DOCX conversion failed; the output is not a valid DOCX file.")
            return Response(content=data,
                            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            headers=_export_headers(f"{base}.docx", cached))

        if fmt == "txt":
            data, cached = await run_in_threadpool(
                build_txt_bytes_with_status, file_path, doc["file_type"], "")
            if not data:
                raise HTTPException(status_code=422, detail="TXT conversion produced no text.")
            return Response(content=data, media_type="text/plain; charset=utf-8",
                            headers=_export_headers(f"{base}.txt", cached))

        if fmt == "pptx":
            chosen = theme or "modern"
            if not force:
                from RapidDoc.backend.app.services.export_service import (
                    document_items,
                )
                from RapidDoc.backend.app.services.ppt_templates import (
                    assess_suitability,
                )

                verdict = assess_suitability(await run_in_threadpool(
                    document_items, file_path, doc["file_type"]))
                if not verdict["suitable"]:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "message": "This document is not suitable for a "
                                       "presentation.",
                            "reasons": verdict["reasons"],
                            "score": verdict["score"],
                            "stats": verdict["stats"],
                            "format": "pptx",
                        },
                    )
            data, cached = await run_in_threadpool(
                build_pptx_bytes_with_status, file_path, doc["file_type"], chosen)
            if not _probe_file(data, "pptx"):
                raise HTTPException(status_code=422, detail="PPTX conversion failed; the output is not a valid PPTX file.")
            return Response(content=data,
                            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            headers=_export_headers(f"{base}.pptx", cached))

        raise HTTPException(status_code=400, detail="Unsupported format. Use original, pdf, docx, txt or pptx.")
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error exporting document: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while exporting the document.")

@router.post("/{doc_id}/style")
async def update_document_style(
    doc_id: str,
    font_name: Optional[str] = Form(None),
    font_size: Optional[float] = Form(None),
    header_text: Optional[str] = Form(None),
    footer_text: Optional[str] = Form(None),
    target_header_text: Optional[str] = Form(None),
    target_footer_text: Optional[str] = Form(None),
    replace_image_index: Optional[int] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        active_path, version_fields = ensure_edited_version(doc, db, action="Styling update")
        
        # Read the replacement image if provided
        image_replacements = []
        if replace_image_index is not None and image_file is not None:
            img_bytes = await image_file.read()
            image_replacements.append({
                "target_index": replace_image_index,
                "image_bytes": img_bytes
            })

        # Set up a new temporary/edit path or overwrite (we'll overwrite or version, overwrite is standard here)
        success = False
        styling_kwargs = dict(
            font_name=font_name, font_size=font_size,
            header_text=header_text, footer_text=footer_text,
            target_header_text=target_header_text, target_footer_text=target_footer_text,
            image_replacements=image_replacements,
            # Resolved against the *original* upload name: the working copy sits
            # in a version folder, so its path would render a meaningless
            # {FILENAME}.
            doc_filename=doc.get("name") or "",
            doc_title=(doc.get("title") or "").strip(),
        )
        if doc["file_type"] == "docx":
            success = await run_in_threadpool(
                apply_docx_styling, active_path, active_path, **styling_kwargs,
            )
        elif doc["file_type"] == "pdf":
            success = await run_in_threadpool(
                apply_pdf_styling, active_path, active_path, **styling_kwargs,
            )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply styling changes to the document.")
        
        # Update edit history and count if files replaced
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Update images count if replacement changed it. This one has to stay
        # inline - the refreshed document (count included) is what we return.
        # Non-image formats keep whatever count they already had.
        images_count = doc.get("images_count", 0)
        if doc["file_type"] in ("docx", "pdf"):
            images_count = await run_in_threadpool(
                _count_images, active_path, f".{doc['file_type']}"
            )

        edit_entry = {
            "date": current_date,
            "action": f"Updated styling: font={font_name}, size={font_size}, header={header_text is not None}, footer={footer_text is not None}, img={replace_image_index is not None}"
        }
        
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": edit_entry},
                "$set": {"images_count": images_count, **version_fields}
            }
        )

        doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        return doc

    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating document styling: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while applying document styles.")

@router.get("/{doc_id}/headers-footers")
async def get_document_headers_footers_endpoint(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        
        if doc["file_type"] == "docx":
            from RapidDoc.backend.app.services.docx_editor import get_docx_headers_footers
            data = await run_in_threadpool(get_docx_headers_footers, file_path)
        elif doc["file_type"] == "pdf":
            from RapidDoc.backend.app.services.pdf_editor import get_pdf_headers_footers
            data = await run_in_threadpool(get_pdf_headers_footers, file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
            
        return data
        
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting headers and footers: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{doc_id}/header-footer")
async def update_document_header_footer_endpoint(
    doc_id: str,
    request: HeaderFooterRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        active_path, version_fields = ensure_edited_version(doc, db, action="Header & footer update")
        success = False

        hf_kwargs = dict(
            font_name=request.font_name, font_size=request.font_size,
            header_text=request.header_text, footer_text=request.footer_text,
            target_header_text=request.target_header_text,
            target_footer_text=request.target_footer_text,
            alignment=request.alignment,
            header_text_odd=request.header_text_odd,
            header_text_even=request.header_text_even,
            header_text_first=request.header_text_first,
            footer_text_odd=request.footer_text_odd,
            footer_text_even=request.footer_text_even,
            footer_text_first=request.footer_text_first,
            header_alignment=request.header_alignment,
            footer_alignment=request.footer_alignment,
            # Resolved against the *original* upload name: the working copy sits
            # in a version folder, so its path would render a meaningless
            # {FILENAME}.
            doc_filename=doc.get("name") or "",
            doc_title=(doc.get("title") or "").strip(),
        )
        if doc["file_type"] == "docx":
            success = await run_in_threadpool(
                apply_docx_styling, active_path, active_path, **hf_kwargs,
            )
        elif doc["file_type"] == "pdf":
            success = await run_in_threadpool(
                apply_pdf_styling, active_path, active_path, **hf_kwargs,
            )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update header/footer.")

        current_date = datetime.now().strftime("%Y-%m-%d")
        changes_desc = []
        for label, value in (
            ("Header", request.header_text),
            ("Footer", request.footer_text),
            ("Header (odd pages)", request.header_text_odd),
            ("Header (even pages)", request.header_text_even),
            ("Header (first page)", request.header_text_first),
            ("Footer (odd pages)", request.footer_text_odd),
            ("Footer (even pages)", request.footer_text_even),
            ("Footer (first page)", request.footer_text_first),
        ):
            if value:
                changes_desc.append(f"{label}: '{value}'")
        if not changes_desc:
            changes_desc.append("cleared")

        edit_entry = {
            "date": current_date,
            "action": f"Updated header & footer ({', '.join(changes_desc)})"
        }

        new_stage = max(2, doc.get("pipeline_stage", 1))
        new_percent = max(50, doc.get("completion_percent", 25))
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": edit_entry},
                "$set": {
                    "pipeline_stage": new_stage,
                    "completion_percent": new_percent,
                    "last_edited_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    **version_fields
                }
            }
        )

        doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        return doc

    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating header/footer: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while updating header/footer.")

@router.post("/{doc_id}/pipeline")
async def update_document_pipeline_endpoint(
    doc_id: str,
    request: PipelineUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        update_data = {}
        if request.pipeline_stage is not None:
            update_data["pipeline_stage"] = request.pipeline_stage
            stage_percent_map = {1: 25, 2: 50, 3: 75, 4: 100}
            if request.completion_percent is None and request.pipeline_stage in stage_percent_map:
                update_data["completion_percent"] = stage_percent_map[request.pipeline_stage]
        if request.pipeline_status is not None:
            update_data["pipeline_status"] = request.pipeline_status
        if request.completion_percent is not None:
            update_data["completion_percent"] = request.completion_percent
        if request.draft_edits is not None:
            update_data["draft_edits"] = request.draft_edits

        update_data["last_edited_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": update_data}
        )

        updated_doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        updated_doc["id"] = str(updated_doc["_id"])
        updated_doc.pop("_id", None)
        return updated_doc

    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating document pipeline: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error updating pipeline.")


def _count_images(file_path: str, ext: str) -> int:
    """Number of embedded images in a stored document.

    Kept as a helper so the upload path can run it off the request thread (see
    :func:`upload_document`); it walks the whole file and is not free.
    """
    if ext == ".docx":
        return get_docx_images_count(file_path)
    if ext == ".pdf":
        return get_pdf_images_count(file_path)
    return 0


def _backfill_image_count(doc_id: str, storage_path: str, ext: str) -> None:
    """Fill in ``images_count`` after the upload response has been sent.

    Runs on a background task, so a failure here can only leave the counter at
    its default - it must never surface as an upload error, because the document
    itself is already stored and usable.
    """
    try:
        count = _count_images(storage_path, ext)
        db_conn.get_db().documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"images_count": count}},
        )
    except Exception as exc:
        logger.warning("Could not record image count for document %s: %s", doc_id, exc)


@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        
        if doc["file_type"] == "docx":
            # One parse for paragraphs, tables and images. This used to be three
            # separate full reads of the .docx zip per request, which is what
            # made opening a large document feel slow.
            view = await run_in_threadpool(get_docx_document_view, file_path)
            return {
                "file_type": "docx",
                # `content` keeps its original shape and index order (save and
                # rewrite key off those indices); `blocks` and `images` are
                # additive so the editor can show tables and pictures.
                "content": view["content"],
                "blocks": view["blocks"],
                "images": view["images"],
            }
        elif doc["file_type"] == "pdf":
            content = await run_in_threadpool(get_pdf_content, file_path)
            return {
                "file_type": "pdf",
                "content": content,
                # PDF content is page-based; the per-page "images" arrays produced
                # by get_pdf_content already carry global image indices.
                "images": await run_in_threadpool(
                    get_document_images, file_path, "pdf"),
            }
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
            
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting document content: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while retrieving document content.")


@router.get("/{doc_id}/images")
async def list_document_images(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Every image in the document, on the canonical index space.

    The editor already receives these alongside the content, so this exists for
    the two cases that need them without a full content fetch: showing the user
    which image a natural-language request resolved to, and letting the client
    confirm a target before committing an upload.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = storage_service.get_file_path(doc["storage_path"])
        inventory = await run_in_threadpool(
            build_image_inventory, file_path, doc["file_type"]
        )
        return {
            "status": "success",
            "count": len(inventory),
            "images": _public_inventory(inventory),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing document images: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while listing images.")


@router.get("/{doc_id}/images/{index}")
async def get_document_image(
    doc_id: str,
    index: int,
    current_user: dict = Depends(get_current_user)
):
    """Serve one embedded image by its stable index, for the interactive view."""
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if index < 0:
            raise HTTPException(status_code=400, detail="Image index must be zero or greater")

        file_path = storage_service.get_file_path(doc["storage_path"])
        data, mime = await run_in_threadpool(
            get_document_image_bytes, file_path, doc["file_type"], index
        )
        if not data:
            raise HTTPException(status_code=404, detail="Image not found")

        return Response(content=data, media_type=mime or "application/octet-stream")
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error("Error getting document image: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while retrieving the image.")


@router.post("/{doc_id}/replace-image")
async def replace_document_image(
    doc_id: str,
    image_file: UploadFile = File(...),
    image_index: Optional[int] = Form(None),
    page: Optional[int] = Form(None),
    command: Optional[str] = Form(None),
    size_mode: str = Form("fit"),
    current_user: dict = Depends(get_current_user)
):
    """Swap the picture at a chosen position for an uploaded image.

    Accepts three ways to name the target, in precedence order:

      * ``image_index`` - the integer the editor already shows. Used by the
        double-click flow, where the user has literally clicked the picture.
      * ``page``        - 1-based, PDFs only.
      * ``command``     - free text, resolved by
        :func:`image_resolver.resolve_image_targets` ("the image on page 2",
        "image 3", "the logo"). No model is involved.

    Returns the refreshed image inventory so the client can re-render without a
    second round trip, plus a human-readable ``message`` explaining what actually
    happened - including when one stored picture is drawn in several places and
    therefore all of them changed.

    The upload is validated before any writer opens, and a failed replacement
    never leaves a partially written document: the writer writes to the same
    path it was given, and it is only called once the bytes are known good.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc["file_type"] not in ("docx", "pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image replacement is not supported for .{doc['file_type']} files.",
            )

        # ---- validate the upload first; never open a writer on bad bytes ----
        raw = await image_file.read()
        try:
            await run_in_threadpool(read_and_validate_image, raw)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        file_path = storage_service.get_file_path(doc["storage_path"])
        file_type = doc["file_type"]

        # ---- work out the target -------------------------------------------
        if image_index is not None:
            if image_index < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image index must be zero or greater.",
                )
            indexes = [image_index]
            reason = "selected directly"
        else:
            if page is not None:
                synthetic = f"the image on page {page}"
            else:
                synthetic = command or ""

            resolution = await run_in_threadpool(
                resolve_image_targets, synthetic, file_path, file_type
            )

            if resolution["status"] == "empty":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=resolution["message"],
                )
            if resolution["status"] == "unresolved":
                # The wording does not identify an image. This is a bad request
                # the user must reword, so it is a 400 with an explanation -
                # distinct from "ambiguous", where the request is valid but the
                # client has to choose from the candidates returned.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=resolution["message"],
                )
            if resolution["status"] == "ambiguous":
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "status": resolution["status"],
                        "message": resolution["message"],
                        "candidates": resolution.get("candidates") or [],
                        "images": resolution.get("inventory") or [],
                    },
                )

            indexes = resolution["indexes"]
            reason = resolution.get("reason", "")

        if not indexes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="I could not work out which image to replace.",
            )

        # ---- write -----------------------------------------------------------
        active_path, version_fields = ensure_edited_version(
            doc, db, action=f"Image replacement ({', '.join(str(i + 1) for i in indexes)})"
        )
        replacements = [{"target_index": i, "image_bytes": raw} for i in indexes]

        if file_type == "docx":
            outcome = await run_in_threadpool(
                replace_docx_images, active_path, active_path, replacements, size_mode
            )
        else:
            outcome = await run_in_threadpool(
                replace_pdf_images, active_path, active_path, replacements, size_mode
            )

        if not outcome.get("ok"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=outcome.get("error") or "The image could not be replaced.",
            )

        # ---- report ------------------------------------------------------------
        reports = [r for r in outcome["reports"] if r.get("replaced")]
        notes = []
        for r in reports:
            if r.get("occurrences", 1) > 1:
                notes.append(
                    f"Image {r['index'] + 1} is the same stored picture used in "
                    f"{r['occurrences']} places, so all of them now show the new image."
                )
            if r.get("scaled"):
                notes.append(
                    f"Image {r['index'] + 1} was scaled to fit its original box so it "
                    "would not be stretched."
                )
            if r.get("no_extent"):
                notes.append(
                    f"Image {r['index'] + 1} declares no size, so it kept whatever size "
                    "the document gives it."
                )
            if r.get("resource_warning"):
                notes.append(
                    f"Image {r['index'] + 1} is stored in a format that had to be "
                    "rewritten, so re-check the surrounding images."
                )

        message = (
            f"Replaced image {indexes[0] + 1}"
            if len(indexes) == 1
            else f"Replaced {len(indexes)} images"
        )
        if reason:
            message += f" ({reason})"
        if notes:
            message += ". " + " ".join(notes)

        images_count = await run_in_threadpool(
            _count_images, active_path, f".{file_type}"
        )
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "action": f"Replaced image(s) {', '.join(str(i + 1) for i in indexes)}",
                }},
                "$set": {"images_count": images_count, **version_fields},
            },
        )

        refreshed = await run_in_threadpool(
            build_image_inventory, active_path, file_type
        )

        return {
            "status": "success",
            "action": "replace_image",
            "replaced": outcome["replaced"],
            "indexes": indexes,
            "reports": outcome["reports"],
            "message": message,
            # The client keys image URLs by index, so it must be told to refetch
            # or it will keep showing the bytes it cached before the swap.
            "images_version": datetime.now().isoformat(),
            "images_count": images_count,
            "images": _public_inventory(refreshed),
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error("Error replacing document image: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while replacing the image.")


@router.post("/{doc_id}/resolve-image")
async def resolve_document_image_target(
    doc_id: str,
    command: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Resolve a phrase to image target(s) without uploading anything.

    Lets the prompt bar tell the user "I found 2 images on page 3 - which one?"
    *before* they hand over a file, instead of after.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = storage_service.get_file_path(doc["storage_path"])
        resolution = await run_in_threadpool(
            resolve_image_targets, command, file_path, doc["file_type"]
        )
        return {
            "status": "success",
            **resolution,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resolving image target: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while resolving the image target.")


@router.post("/{doc_id}/resize-image")
async def resize_document_images(
    doc_id: str,
    payload: ImageResizeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Change how large a picture prints, without touching its pixels.

    Accepts a batch so the dialog can resize several pictures in one save, and
    names targets the same way everything else does - the canonical image index,
    which is the integer already shown on the tile.

    Distinguishes the two failure kinds the same way ``/replace-image`` does:
    a request that cannot be honoured (no size, zero, unknown unit, a rotated
    picture) is a 400 with an explanation, because re-sending it unchanged would
    fail the same way.

    Returns the refreshed inventory so the client can re-render in one round
    trip, plus the before/after size of each picture so the UI can confirm what
    it actually did rather than what was asked.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc["file_type"] not in ("docx", "pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image resizing is not supported for .{doc['file_type']} files.",
            )

        if not payload.items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No image was identified to resize.",
            )

        file_type = doc["file_type"]
        resizes = [
            {
                "target_index": item.index,
                "width": item.width,
                "height": item.height,
                "unit": item.unit,
                "keep_aspect": item.keep_aspect,
                "anchor": item.anchor,
            }
            for item in payload.items
        ]

        active_path, version_fields = ensure_edited_version(
            doc, db, action=f"Image resize ({len(payload.items)} image(s))"
        )
        if file_type == "docx":
            outcome = await run_in_threadpool(
                resize_docx_images, active_path, active_path, resizes
            )
        else:
            outcome = await run_in_threadpool(
                resize_pdf_images, active_path, active_path, resizes
            )

        if not outcome.get("ok"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=outcome.get("error") or "The image could not be resized.",
            )

        reports = [r for r in outcome["reports"] if r.get("resized")]
        indexes = [r["index"] for r in reports]
        message = (
            f"Resized image {indexes[0] + 1}"
            if len(indexes) == 1
            else f"Resized {len(indexes)} images"
        )
        changes = [r.get("change") for r in reports if r.get("change")]
        if changes:
            message += f" ({'; '.join(changes)})"
        multi = [r for r in reports if r.get("placements", 1) > 1]
        if multi:
            message += (
                f". {multi[0]['index'] + 1} is drawn in {multi[0]['placements']} "
                "places, and all of them were resized."
            )

        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "action": f"Resized image(s) {', '.join(str(i + 1) for i in indexes)}",
                }},
                "$set": version_fields,
            },
        )

        refreshed = await run_in_threadpool(
            build_image_inventory, active_path, file_type
        )

        return {
            "status": "success",
            "action": "resize_image",
            "resized": outcome["resized"],
            "indexes": indexes,
            "reports": outcome["reports"],
            "message": message,
            "images_version": datetime.now().isoformat(),
            "images_count": len(refreshed),
            "images": _public_inventory(refreshed),
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error("Error resizing document images: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while resizing the image.")


@router.get("/{doc_id}/versions")
async def list_document_versions(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """The rollback timeline: the live document, every checkpoint, the original.

    `edit_history` is prose and cannot be restored from; this is the list the
    history panel renders so a mis-click has a way back.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        timeline = await run_in_threadpool(list_versions, doc)
        return {
            "status": "success",
            "count": len(timeline),
            "versions": timeline,
            "has_original": bool(
                doc.get("original_storage_path") or not doc.get("has_edited_version")
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing document versions: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while listing versions.")


@router.post("/{doc_id}/versions/{version_id}/restore")
async def restore_document_version(
    doc_id: str,
    version_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Make an earlier version the live document.

    Non-destructive in both directions: the state being replaced is snapshotted
    first, so a restore taken by mistake is itself on the timeline. The uploaded
    original is never overwritten - a restore writes a fresh file and repoints
    `storage_path`, exactly like any other edit.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            new_path = await run_in_threadpool(restore_version, db, doc, version_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except FileNotFoundError:
            raise HTTPException(status_code=410, detail="That version's file is no longer available.")

        images_count = doc.get("images_count", 0)
        if doc["file_type"] in ("docx", "pdf"):
            images_count = await run_in_threadpool(
                _count_images, new_path, f".{doc['file_type']}"
            )

        entry = find_version(doc, version_id)
        restored_label = entry.get("label") or "an earlier version"

        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "action": f"Restored {restored_label}",
                }},
                "$set": {
                    "storage_path": new_path,
                    "has_edited_version": True,
                    "images_count": images_count,
                },
            },
        )

        refreshed = await run_in_threadpool(list_versions, db.documents.find_one({"_id": ObjectId(doc_id)}))
        return {
            "status": "success",
            "action": "restore_version",
            "message": f"Restored {restored_label}.",
            "images_version": datetime.now().isoformat(),
            "images_count": images_count,
            "versions": refreshed,
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error("Error restoring document version: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while restoring the version.")


@router.post("/{doc_id}/content")
async def update_document_content(
    doc_id: str,
    request: ContentUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        active_path, version_fields = ensure_edited_version(doc, db, action="Text edits")
        success = False
        
        if doc["file_type"] == "docx":
            # Accept both addressings: body paragraphs (`index`) and table cells
            # (`table_index`/`row`/`col`). Anything missing its coordinates is
            # skipped rather than silently misapplied to paragraph 0.
            edits_list = []
            for item in request.edits:
                text = item.text
                if item.kind == "table_cell" or item.table_index is not None:
                    if item.table_index is None or item.row is None or item.col is None:
                        continue
                    edits_list.append({
                        "table_index": item.table_index,
                        "row": item.row,
                        "col": item.col,
                        "text": text,
                    })
                elif item.index is not None:
                    edits_list.append({"index": item.index, "text": text})
            success = await run_in_threadpool(update_docx_content, active_path, active_path, edits_list)
        elif doc["file_type"] == "pdf":
            # Group edits by page
            from collections import defaultdict
            grouped_edits = defaultdict(list)
            for item in request.edits:
                if item.page_num is not None and item.block_no is not None:
                    grouped_edits[item.page_num].append({
                        "block_no": item.block_no,
                        "bbox": item.bbox,
                        "text": item.text
                    })
            pdf_edits = [{"page_num": page_num, "blocks": blocks} for page_num, blocks in grouped_edits.items()]
            success = await run_in_threadpool(update_pdf_content, active_path, active_path, pdf_edits)
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
            
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save content edits to file.")
            
        # Add to history log
        current_date = datetime.now().strftime("%Y-%m-%d")
        edit_entry = {
            "date": current_date,
            "action": f"Edited text content ({len(request.edits)} block(s))"
        }
        
        new_stage = max(3, doc.get("pipeline_stage", 1))
        new_percent = max(75, doc.get("completion_percent", 25))
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": edit_entry},
                "$set": {
                    "pipeline_stage": new_stage,
                    "completion_percent": new_percent,
                    "draft_edits": {},
                    "last_edited_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    **version_fields
                }
            }
        )
        
        # Reload and return document info
        updated_doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        updated_doc["id"] = str(updated_doc["_id"])
        updated_doc.pop("_id", None)
        return updated_doc
        
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error saving document content edits: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while saving content edits.")

@router.post("/{doc_id}/find-replace")
async def find_replace_document_text(
    doc_id: str,
    request: FindReplaceRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        active_path, version_fields = ensure_edited_version(doc, db, action="Find & replace")
        matches_replaced = 0
        
        if doc["file_type"] == "docx":
            matches_replaced = await run_in_threadpool(
                find_replace_docx, active_path, active_path,
                request.find_text, request.replace_text, request.case_sensitive
            )
        elif doc["file_type"] == "pdf":
            matches_replaced = await run_in_threadpool(
                find_replace_pdf, active_path, active_path,
                request.find_text, request.replace_text, request.case_sensitive
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
            
        if matches_replaced > 0:
            current_date = datetime.now().strftime("%Y-%m-%d")
            edit_entry = {
                "date": current_date,
                "action": f"Find & Replace: '{request.find_text}' -> '{request.replace_text}' ({matches_replaced} matches)"
            }
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {
                    "$push": {"edit_history": edit_entry},
                    "$set": version_fields
                }
            )
            
        return {"status": "success", "matches_replaced": matches_replaced}
        
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error executing find-replace on document: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while executing find-replace.")

@router.post("/{doc_id}/ai-command")
async def ai_command_endpoint(
    doc_id: str,
    request: AICommandRequest,
    current_user: dict = Depends(get_current_user)
):
    """Understand a natural-language command via Gemini, then act on the document.

    For 'replace': returns variant groups for the user to select which to change.
    For 'header'/'footer': applies the change directly (only header/footer) and
    returns change info for highlighting.
    For 'replace_image': resolves which image the phrase names and returns it,
    so the client can upload the new file against a confirmed target. Nothing is
    written here - this endpoint never mutates the document for an image swap.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        intent = await run_in_threadpool(
            understand_command, request.command, bool(request.has_image_upload)
        )
        action = intent.get("action")

        if action == "replace":
            find_text = (intent.get("find_text") or "").strip()
            replace_text = (intent.get("replace_text") or "").strip()
            if not find_text:
                return {"status": "success", "action": "unknown", "engine": intent.get("engine"), "message": "I couldn't tell what text to find."}
            if doc["file_type"] == "docx":
                result = await run_in_threadpool(
                    find_text_variants, file_path, find_text, False
                )
            else:
                result = await run_in_threadpool(
                    find_text_variants_pdf, file_path, find_text, False
                )
            return {
                "status": "success",
                "action": "replace",
                "intent": intent.get("intent"),
                "engine": intent.get("engine"),
                "find_text": find_text,
                "replace_text": replace_text,
                "total_matches": result["total_matches"],
                "groups": result["groups"],
            }

        if action in ("header", "footer"):
            new_text = (intent.get("new_text") or "").strip()
            if not new_text:
                return {"status": "success", "action": "unknown", "engine": intent.get("engine"), "message": f"I couldn't tell what new {action} text you want."}
            active_path, version_fields = ensure_edited_version(doc, db, action=f"AI {action} command")
            success = False
            # NOTE: these must stay keyword arguments. Passing the header/footer
            # text positionally landed it in `font_name`/`font_size`: the header
            # branch reported success while writing no header at all, and the
            # footer branch passed a string to Pt() and returned HTTP 500.
            if doc["file_type"] == "docx":
                success = await run_in_threadpool(
                    apply_docx_styling, active_path, active_path,
                    header_text=new_text if action == "header" else None,
                    footer_text=new_text if action == "footer" else None,
                )
            else:
                success = await run_in_threadpool(
                    apply_pdf_styling, active_path, active_path,
                    header_text=new_text if action == "header" else None,
                    footer_text=new_text if action == "footer" else None,
                )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update the document.")
            current_date = datetime.now().strftime("%Y-%m-%d")
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": {"date": current_date, "action": f"Changed {action} to '{new_text}'"}},
                 "$set": version_fields}
            )
            return {
                "status": "success",
                "action": action,
                "intent": intent.get("intent"),
                "engine": intent.get("engine"),
                "new_text": new_text,
                "message": f"Changed the {action} to '{new_text}'.",
                "changes": [{"paragraph": action.capitalize(), "old_text": "", "new_text": new_text}],
            }

        if action == "image_module":
            if doc["file_type"] not in ("docx", "pdf"):
                return {
                    "status": "success",
                    "action": "image_module",
                    "engine": intent.get("engine", "rule"),
                    "count": 0,
                    "images": [],
                    "message": f"Image detection is not supported for .{doc['file_type']} files.",
                }
            inventory = await run_in_threadpool(
                build_image_inventory, file_path, doc["file_type"]
            )
            count = len(inventory)
            return {
                "status": "success",
                "action": "image_module",
                "engine": intent.get("engine", "rule"),
                "count": count,
                "images": _public_inventory(inventory),
                "message": (
                    f"Detected {count} image{'s' if count != 1 else ''} in this document."
                    if count > 0
                    else "No images detected in this document."
                ),
            }

        if action == "replace_image":
            # The intent layer deliberately returns no index. Resolve the target
            # here, against this document's real image list, so the client can
            # show the user which picture is about to be replaced (or pick one)
            # before it uploads anything.
            if doc["file_type"] not in ("docx", "pdf"):
                return {
                    "status": "success", "action": "unknown",
                    "engine": intent.get("engine"),
                    "message": f"Image replacement isn't supported for .{doc['file_type']} files.",
                }
            resolution = await run_in_threadpool(
                resolve_image_targets, request.command, file_path, doc["file_type"]
            )
            return {
                "status": "success",
                "action": "replace_image",
                "engine": intent.get("engine"),
                "intent": intent.get("intent"),
                **resolution,
            }

        if action == "summarize":
            scope = (intent.get("scope") or "document").lower()
            page = intent.get("page")
            length = intent.get("length")
            if scope == "page":
                if page is None:
                    return {
                        "status": "success",
                        "action": "unknown",
                        "engine": intent.get("engine"),
                        "message": "Tell me which page to summarize, e.g. 'Summarize page 2'.",
                    }
                source_text, source_label = await run_in_threadpool(
                    _unit_text, file_path, doc["file_type"], page
                )
                if not source_text:
                    what = "page" if doc["file_type"] == "pdf" else "paragraph"
                    return {
                        "status": "success",
                        "action": "unknown",
                        "engine": intent.get("engine"),
                        "message": f"{what.capitalize()} {page} has no readable text in this document.",
                    }
            else:
                source_text = await run_in_threadpool(
                    _document_text, file_path, doc["file_type"]
                )
                source_label = "whole document"

            if not source_text:
                return {
                    "status": "success",
                    "action": "unknown",
                    "engine": intent.get("engine"),
                    "message": "I could not find any readable text to summarize in this document.",
                }

            doc_title = doc.get("name") or doc.get("title") or "Document"
            result = await run_in_threadpool(summarize_document, source_text, length, doc_title)
            current_date = datetime.now().strftime("%Y-%m-%d")
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": {
                    "date": current_date,
                    "action": f"AI Summarize ({result['engine']}): {source_label}"
                }}}
            )
            if not result.get("summary"):
                return {
                    "status": "error",
                    "action": "summarize",
                    "intent": intent.get("intent"),
                    "engine": result.get("engine"),
                    "message": result.get("message") or "Summarization is unavailable right now.",
                }
            return {
                "status": "success",
                "action": "summarize",
                "intent": intent.get("intent"),
                "engine": result["engine"],
                "source": source_label,
                "summary_source": result.get("source", "document"),
                "length": length,
                "summary": result["summary"],
                "key_points": result.get("key_points") or [],
                "message": f"Summary of the {source_label}:\n\n{result['summary']}",
            }

        if action == "generate_mcq":
            requested = intent.get("num_questions") or 5
            source_label = "whole document"
            source_text = _explicit_text(request)
            if source_text:
                source_label = "provided text"
            else:
                source_text = await run_in_threadpool(
                    _document_text, file_path, doc["file_type"]
                )
            if not source_text:
                return {
                    "status": "success",
                    "action": "unknown",
                    "engine": intent.get("engine"),
                    "message": "I could not find any readable text to build questions from.",
                }
            result = await run_in_threadpool(generate_mcqs, source_text, requested)
            current_date = datetime.now().strftime("%Y-%m-%d")
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": {
                    "date": current_date,
                    "action": f"AI Generate MCQ ({result['engine']}): {result.get('requested')} requested from {source_label}"
                }}}
            )
            if not result.get("questions"):
                return {
                    "status": "error",
                    "action": "generate_mcq",
                    "intent": intent.get("intent"),
                    "engine": result.get("engine"),
                    "source": source_label,
                    "message": result.get("message") or "Question generation is unavailable right now.",
                }
            return {
                "status": "success",
                "action": "generate_mcq",
                "intent": intent.get("intent"),
                "engine": result["engine"],
                # Without this the client renders "from undefined" in its
                # "Generated N of M requested question(s) from X." notice.
                "source": source_label,
                "requested": result["requested"],
                "questions": result["questions"],
                "message": result["message"],
            }

        if action == "rewrite":
            source_text = _explicit_text(request)
            source_label = "provided text" if source_text else "whole document"
            if not source_text:
                source_text = await run_in_threadpool(
                    _document_text, file_path, doc["file_type"]
                )
            if not source_text:
                return {
                    "status": "success",
                    "action": "unknown",
                    "engine": intent.get("engine"),
                    "message": "I could not find any readable text to rewrite in this document.",
                }
            instruction = intent.get("instruction") or request.command
            result = await run_in_threadpool(rewrite_text, instruction, source_text[:2500])
            rewritten = result.get("rewritten_text") or ""
            current_date = datetime.now().strftime("%Y-%m-%d")
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": {
                    "date": current_date,
                    "action": f"AI Rewrite ({result.get('engine')}): {instruction[:40]}"
                }}}
            )
            return {
                "status": "success",
                "action": "rewrite",
                "intent": intent.get("intent"),
                "engine": result.get("engine"),
                "instruction": instruction,
                "rewritten_text": rewritten,
                "source": source_label,
                "message": result.get("message") or f"Rewritten following instruction '{instruction}'.",
            }

        return {"status": "success", "action": "unknown", "intent": intent.get("intent"), "engine": intent.get("engine"), "message": "I scanned your document. Try e.g. 'Change print to not print' or 'Change the header to RapidDoc Report'."}

    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in AI command endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while processing the AI command.")

@router.post("/{doc_id}/find-variants")
async def find_document_variants(
    doc_id: str,
    request: FindVariantsRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        if doc["file_type"] == "docx":
            result = await run_in_threadpool(
                find_text_variants, file_path, request.find_text, request.case_sensitive
            )
        elif doc["file_type"] == "pdf":
            result = await run_in_threadpool(
                find_text_variants_pdf, file_path, request.find_text, request.case_sensitive
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        return result
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error finding variants: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while finding variants.")

@router.post("/{doc_id}/selective-replace")
async def selective_replace_document_text(
    doc_id: str,
    request: SelectiveReplaceRequest,
    current_user: dict = Depends(get_current_user)
):
    """Replace only the user-selected variants; returns changes for highlighting."""
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if not request.selected_variants:
            return {"status": "success", "matches_replaced": 0, "changes": []}
        
        active_path, version_fields = ensure_edited_version(doc, db, action="Selective replace")
        if doc["file_type"] == "docx":
            result = await run_in_threadpool(
                selective_replace_docx, active_path, active_path, request.find_text,
                request.replace_text, request.selected_variants, request.case_sensitive
            )
        elif doc["file_type"] == "pdf":
            result = await run_in_threadpool(
                selective_replace_pdf, active_path, active_path, request.find_text,
                request.replace_text, request.selected_variants, request.case_sensitive
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        
        if result["matches_replaced"] > 0:
            current_date = datetime.now().strftime("%Y-%m-%d")
            edit_entry = {
                "date": current_date,
                "action": f"AI Replace: '{request.find_text}' -> '{request.replace_text}' "
                          f"({', '.join(request.selected_variants)}; {result['matches_replaced']} matches)"
            }
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": edit_entry}, "$set": version_fields}
            )
        
        return {"status": "success", **result}
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error executing selective replace: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while executing selective replace.")


@router.post("/{doc_id}/rewrite")
async def rewrite_document_text_endpoint(
    doc_id: str,
    request: RewriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Rewrite a paragraph/block of the document using the local T5 brain
    (Gemini fallback), returning the rewritten text so the frontend can apply
    it through the existing /content endpoint."""
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        source_text = _explicit_text(request)
        source_label = "provided text"
        if not source_text:
            file_path = storage_service.get_file_path(doc["storage_path"])
            if doc["file_type"] == "docx":
                paragraphs = await run_in_threadpool(get_docx_content, file_path)
                if request.index is None or not (0 <= request.index < len(paragraphs)):
                    raise HTTPException(status_code=400, detail=f"Valid 'index' (0..{len(paragraphs) - 1}) is required for this DOCX.")
                source_text = (paragraphs[request.index].get("text") or "").strip()
                source_label = f"paragraph index {request.index}"
            elif doc["file_type"] == "pdf":
                if request.page_num is None or request.block_no is None:
                    raise HTTPException(status_code=400, detail="'page_num' and 'block_no' are required for this PDF.")
                pages = await run_in_threadpool(get_pdf_content, file_path)
                page = next((p for p in pages if p["page_num"] == request.page_num), None)
                if not page:
                    raise HTTPException(status_code=400, detail=f"Page {request.page_num} not found in document.")
                block = next((b for b in page["blocks"] if b.get("block_no") == request.block_no), None)
                if not block:
                    raise HTTPException(status_code=400, detail=f"Block {request.block_no} not found on page {request.page_num}.")
                source_text = (block.get("text") or "").strip()
                source_label = f"page {request.page_num} block {request.block_no}"
            else:
                raise HTTPException(status_code=400, detail="Unsupported document type")

        if not source_text:
            raise HTTPException(status_code=400, detail="The target paragraph/block is empty; nothing to rewrite.")

        result = await run_in_threadpool(rewrite_text, request.instruction, source_text)

        current_date = datetime.now().strftime("%Y-%m-%d")
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$push": {"edit_history": {
                "date": current_date,
                "action": f"AI Rewrite ({result['engine']}): {source_label} - {request.instruction or 'improve'}"
            }}}
        )

        return {
            "status": "success",
            "original_text": source_text,
            "source": source_label,
            "instruction": request.instruction,
            **result,
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in document rewrite endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while rewriting document text.")


@router.post("/{doc_id}/summarize")
async def summarize_document_endpoint(
    doc_id: str,
    request: SummarizeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Summarize a document (or one page/paragraph) with the local BART brain.

    The summary is returned to the client; nothing is written to the file.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        source_text = _explicit_text(request)
        source_label = "provided text"

        if not source_text:
            file_path = storage_service.get_file_path(doc["storage_path"])
            file_type = doc["file_type"]
            if (request.scope or "document").lower() == "page":
                if request.page is None:
                    raise HTTPException(
                        status_code=400,
                        detail="'page' is required when scope is 'page' (1-based page number for PDF, 0-based paragraph index for DOCX).",
                    )
                source_text, source_label = await run_in_threadpool(
                    _unit_text, file_path, file_type, request.page
                )
                if not source_text:
                    what = "page" if file_type == "pdf" else "paragraph"
                    raise HTTPException(
                        status_code=400,
                        detail=f"{what.capitalize()} {request.page} has no readable text in this document.",
                    )
            else:
                source_text = await run_in_threadpool(_document_text, file_path, file_type)
                source_label = "whole document"

        if not source_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No readable text could be extracted from this document.",
            )

        doc_title = doc.get("name") or doc.get("title") or "Document"
        result = await run_in_threadpool(
            summarize_document, source_text, request.length, doc_title
        )

        current_date = datetime.now().strftime("%Y-%m-%d")
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$push": {"edit_history": {
                "date": current_date,
                "action": f"AI Summarize ({result['engine']}): {source_label}"
            }}}
        )

        if not result.get("summary"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message") or "No summarization engine is available.",
            )

        return {
            "status": "success",
            "source": source_label,
            "length": request.length,
            "characters": len(source_text),
            **result,
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in document summarize endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while summarizing the document.")


@router.post("/{doc_id}/generate-mcq")
async def generate_document_mcq_endpoint(
    doc_id: str,
    request: GenerateMCQRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate multiple-choice questions from the document with the local
    BART MCQ brain. Questions are returned to the client, never written to
    the file.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        source_text = _explicit_text(request)
        source_label = "provided text"
        if not source_text:
            file_path = storage_service.get_file_path(doc["storage_path"])
            source_text = await run_in_threadpool(
                _document_text, file_path, doc["file_type"]
            )
            source_label = "whole document"

        if not source_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No readable text could be extracted from this document.",
            )

        result = await run_in_threadpool(
            generate_mcqs, source_text, request.num_questions
        )

        current_date = datetime.now().strftime("%Y-%m-%d")
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$push": {"edit_history": {
                "date": current_date,
                "action": f"AI Generate MCQ ({result['engine']}): {result.get('requested')} requested from {source_label}"
            }}}
        )

        if not result.get("questions"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message") or "No question-generation engine is available.",
            )

        return {
            **result,
            # After the spread, so the label this route computed always wins.
            "status": "success",
            "source": source_label,
            "characters": len(source_text),
        }
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in document generate-mcq endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while generating questions.")


@router.post("/{doc_id}/summary/export")
async def export_document_summary(
    doc_id: str,
    request: SummaryExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Download a generated summary as txt, docx or pdf.

    Takes the summary the client is already showing rather than regenerating it:
    a second summarisation pass would hand back different wording, and the user
    asked to keep the one they read.
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if not (request.summary or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="There is no summary text to export. Generate a summary first.",
            )

        fmt = (request.format or "txt").lower().strip()
        if fmt not in SUPPORTED_SUMMARY_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported summary format '{request.format}'. Use one of: "
                       f"{', '.join(SUPPORTED_SUMMARY_FORMATS)}.",
            )

        title = (request.title or doc.get("filename") or "Summary").strip()
        payload = {
            "summary": request.summary,
            "key_points": request.key_points or [],
            "source": request.source,
            "engine": request.engine,
            "characters": request.characters,
        }

        try:
            data, filename, media_type = await run_in_threadpool(
                build_summary_bytes, fmt, payload, title
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$push": {"edit_history": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "action": f"Exported summary as {fmt.upper()}"
            }}}
        )

        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in document summary export endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while exporting the summary.")
