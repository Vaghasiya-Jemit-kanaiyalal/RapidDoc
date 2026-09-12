from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from typing import Optional
from bson import ObjectId
from datetime import datetime
import os
import logging

from app.database import db_conn
from app.routers.auth import get_current_user
from app.services.storage import storage_service
from app.services.docx_editor import (
    apply_docx_styling, get_docx_images_count, get_docx_content, update_docx_content, find_replace_docx,
    find_text_variants, selective_replace_docx
)
from app.services.pdf_editor import (
    apply_pdf_styling, get_pdf_images_count, get_pdf_content, update_pdf_content, find_replace_pdf,
    find_text_variants_pdf, selective_replace_pdf
)
from app.services.gemini_service import understand_command
from app.models import DocumentMetadata, ContentUpdateRequest, FindReplaceRequest, AICommandRequest, FindVariantsRequest, SelectiveReplaceRequest, HeaderFooterRequest, PipelineUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Secure list of allowed extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

def validate_file(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Only {', '.join(ALLOWED_EXTENSIONS)} are allowed."
        )
    return ext

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    ext = validate_file(file.filename)
    
    # Read file content (up to 10MB limit)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum limit of 10MB."
        )

    try:
        # Save to local storage
        storage_path = storage_service.save_file(file.filename, content)
        
        # Determine number of images
        images_count = 0
        if ext == ".docx":
            images_count = get_docx_images_count(storage_path)
        elif ext == ".pdf":
            images_count = get_pdf_images_count(storage_path)

        # Build DB document metadata (no upload timestamp, upload_date YYYY-MM-DD only)
        upload_date_str = datetime.now().strftime("%Y-%m-%d")
        
        doc_metadata = {
            "name": file.filename,
            "file_type": ext.lstrip("."),
            "storage_path": storage_path,
            "owner_id": current_user["id"],
            "upload_date": upload_date_str,
            "images_count": images_count,
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
        
        doc_metadata["id"] = str(result.inserted_id)
        doc_metadata.pop("_id", None)
        
        return doc_metadata
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
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error downloading file: %s", e)
        raise HTTPException(status_code=404, detail="Document file not found or inaccessible.")

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
        
        orig_path = storage_service.get_file_path(doc["storage_path"])
        
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
        if doc["file_type"] == "docx":
            success = apply_docx_styling(
                doc_path=orig_path,
                output_path=orig_path,  # Save in-place
                font_name=font_name,
                font_size=font_size,
                header_text=header_text,
                footer_text=footer_text,
                target_header_text=target_header_text,
                target_footer_text=target_footer_text,
                image_replacements=image_replacements
            )
        elif doc["file_type"] == "pdf":
            success = apply_pdf_styling(
                pdf_path=orig_path,
                output_path=orig_path,  # Save in-place
                font_name=font_name,
                font_size=font_size,
                header_text=header_text,
                footer_text=footer_text,
                target_header_text=target_header_text,
                target_footer_text=target_footer_text,
                image_replacements=image_replacements
            )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply styling changes to the document.")
        
        # Update edit history and count if files replaced
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Update images count if replacement changed it
        images_count = doc.get("images_count", 0)
        if doc["file_type"] == "docx":
            images_count = get_docx_images_count(orig_path)
        elif doc["file_type"] == "pdf":
            images_count = get_pdf_images_count(orig_path)

        edit_entry = {
            "date": current_date,
            "action": f"Updated styling: font={font_name}, size={font_size}, header={header_text is not None}, footer={footer_text is not None}, img={replace_image_index is not None}"
        }
        
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": edit_entry},
                "$set": {"images_count": images_count}
            }
        )

        doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        return doc

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
            from app.services.docx_editor import get_docx_headers_footers
            data = get_docx_headers_footers(file_path)
        elif doc["file_type"] == "pdf":
            from app.services.pdf_editor import get_pdf_headers_footers
            data = get_pdf_headers_footers(file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
            
        return data
        
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
        
        orig_path = storage_service.get_file_path(doc["storage_path"])
        success = False

        if doc["file_type"] == "docx":
            success = apply_docx_styling(
                doc_path=orig_path,
                output_path=orig_path,
                font_name=request.font_name,
                font_size=request.font_size,
                header_text=request.header_text,
                footer_text=request.footer_text,
                target_header_text=request.target_header_text,
                target_footer_text=request.target_footer_text,
                alignment=request.alignment
            )
        elif doc["file_type"] == "pdf":
            success = apply_pdf_styling(
                pdf_path=orig_path,
                output_path=orig_path,
                font_name=request.font_name,
                font_size=request.font_size,
                header_text=request.header_text,
                footer_text=request.footer_text,
                target_header_text=request.target_header_text,
                target_footer_text=request.target_footer_text,
                alignment=request.alignment
            )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update header/footer.")

        current_date = datetime.now().strftime("%Y-%m-%d")
        changes_desc = []
        if request.header_text is not None:
            changes_desc.append(f"Header: '{request.header_text}'")
        if request.footer_text is not None:
            changes_desc.append(f"Footer: '{request.footer_text}'")

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
                    "last_edited_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
            }
        )

        doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        return doc

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

    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating document pipeline: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error updating pipeline.")


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
            content = get_docx_content(file_path)
            return {"file_type": "docx", "content": content}
        elif doc["file_type"] == "pdf":
            content = get_pdf_content(file_path)
            return {"file_type": "pdf", "content": content}
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
            
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting document content: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while retrieving document content.")

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
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        success = False
        
        if doc["file_type"] == "docx":
            edits_list = [{"index": item.index, "text": item.text} for item in request.edits if item.index is not None]
            success = update_docx_content(file_path, file_path, edits_list)
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
            success = update_pdf_content(file_path, file_path, pdf_edits)
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
                    "last_edited_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
            }
        )
        
        # Reload and return document info
        updated_doc = db.documents.find_one({"_id": ObjectId(doc_id)})
        updated_doc["id"] = str(updated_doc["_id"])
        updated_doc.pop("_id", None)
        return updated_doc
        
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
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        matches_replaced = 0
        
        if doc["file_type"] == "docx":
            matches_replaced = find_replace_docx(
                file_path, file_path, request.find_text, request.replace_text, request.case_sensitive
            )
        elif doc["file_type"] == "pdf":
            matches_replaced = find_replace_pdf(
                file_path, file_path, request.find_text, request.replace_text, request.case_sensitive
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
                    "$push": {"edit_history": edit_entry}
                }
            )
            
        return {"status": "success", "matches_replaced": matches_replaced}
        
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
    """
    try:
        db = db_conn.get_db()
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "owner_id": current_user["id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        intent = understand_command(request.command)
        action = intent.get("action")

        if action == "replace":
            find_text = (intent.get("find_text") or "").strip()
            replace_text = (intent.get("replace_text") or "").strip()
            if not find_text:
                return {"status": "success", "action": "unknown", "message": "I couldn't tell what text to find."}
            if doc["file_type"] == "docx":
                result = find_text_variants(file_path, find_text, case_sensitive=False)
            else:
                result = find_text_variants_pdf(file_path, find_text, case_sensitive=False)
            return {
                "status": "success",
                "action": "replace",
                "find_text": find_text,
                "replace_text": replace_text,
                "total_matches": result["total_matches"],
                "groups": result["groups"],
            }

        if action in ("header", "footer"):
            new_text = (intent.get("new_text") or "").strip()
            if not new_text:
                return {"status": "success", "action": "unknown", "message": f"I couldn't tell what new {action} text you want."}
            success = False
            if doc["file_type"] == "docx":
                success = apply_docx_styling(
                    doc_path=file_path,
                    output_path=file_path,
                    header_text=new_text if action == "header" else None,
                    footer_text=new_text if action == "footer" else None,
                )
            else:
                success = apply_pdf_styling(
                    pdf_path=file_path,
                    output_path=file_path,
                    header_text=new_text if action == "header" else None,
                    footer_text=new_text if action == "footer" else None,
                )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update the document.")
            current_date = datetime.now().strftime("%Y-%m-%d")
            db.documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"edit_history": {"date": current_date, "action": f"Changed {action} to '{new_text}'"}}}
            )
            return {
                "status": "success",
                "action": action,
                "new_text": new_text,
                "message": f"Changed the {action} to '{new_text}'.",
                "changes": [{"paragraph": action.capitalize(), "old_text": "", "new_text": new_text}],
            }

        return {"status": "success", "action": "unknown", "message": "I scanned your document. Try e.g. 'Change print to not print' or 'Change the header to RapidDoc Report'."}

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
            result = find_text_variants(file_path, request.find_text, request.case_sensitive)
        elif doc["file_type"] == "pdf":
            result = find_text_variants_pdf(file_path, request.find_text, request.case_sensitive)
        else:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        return result
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
        
        file_path = storage_service.get_file_path(doc["storage_path"])
        if doc["file_type"] == "docx":
            result = selective_replace_docx(
                file_path, file_path, request.find_text, request.replace_text,
                request.selected_variants, request.case_sensitive
            )
        elif doc["file_type"] == "pdf":
            result = selective_replace_pdf(
                file_path, file_path, request.find_text, request.replace_text,
                request.selected_variants, request.case_sensitive
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
                {"$push": {"edit_history": edit_entry}}
            )
        
        return {"status": "success", **result}
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error executing selective replace: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while executing selective replace.")
