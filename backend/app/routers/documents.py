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
    apply_docx_styling, get_docx_images_count, get_docx_content, update_docx_content, find_replace_docx
)
from app.services.pdf_editor import (
    apply_pdf_styling, get_pdf_images_count, get_pdf_content, update_pdf_content, find_replace_pdf
)
from app.models import DocumentMetadata, ContentUpdateRequest, FindReplaceRequest

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
            "edit_history": [
                {
                    "date": upload_date_str,
                    "action": "Uploaded document"
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
        
        db.documents.update_one(
            {"_id": ObjectId(doc_id)},
            {
                "$push": {"edit_history": edit_entry}
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
