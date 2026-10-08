"""Canonical Document AST Builder.

Parses both DOCX and PDF documents into an unambiguous, structured JSON
Abstract Syntax Tree (headings, paragraphs, tables, images) that powers the
RapidDoc editor and document integrations.
"""

import logging
import os
from typing import Any, Dict

from RapidDoc.backend.app.services.docx_editor import iter_docx_body_items
from RapidDoc.backend.app.services.pdf_editor import get_pdf_content

logger = logging.getLogger(__name__)


def build_document_ast(file_path: str, file_type: str) -> Dict[str, Any]:
    """Convert an uploaded document into a unified canonical JSON AST.

    Handles both DOCX (native flow hierarchy) and PDF (PyMuPDF blocks).
    """
    blocks = []
    images = []
    title = os.path.splitext(os.path.basename(file_path))[0].replace("_", " ")

    if file_type == "docx":
        block_idx = 0
        for kind, payload in iter_docx_body_items(file_path):
            if kind == "paragraph":
                text = (payload.get("text") or "").strip()
                if not text:
                    continue
                font_size = float(payload.get("font_size") or 11.0)
                is_bold = bool(payload.get("bold"))

                # Word's own outline level (style name / <w:outlineLvl>) is
                # authoritative; the size heuristic only applies when the
                # paragraph carries no outline information at all.
                style = (payload.get("style") or "").strip().lower()
                level = int(payload.get("heading_level") or 0)
                if level == 0 and style == "title":
                    level = 1
                elif level == 0 and style == "subtitle":
                    level = 2

                block_type = "paragraph"
                heading_level = 0
                if level:
                    block_type = "heading"
                    heading_level = min(level, 3)
                elif font_size >= 18 or (font_size >= 14 and is_bold and len(text) < 80):
                    block_type = "heading"
                    heading_level = 1 if font_size >= 18 else 2
                elif font_size >= 13 and is_bold and len(text) < 100:
                    block_type = "heading"
                    heading_level = 3

                blocks.append({
                    "id": f"docx-p-{payload.get('index', block_idx)}",
                    "kind": block_type,
                    "level": heading_level,
                    "index": payload.get("index", block_idx),
                    "text": text,
                    "font_name": payload.get("font_name"),
                    "font_size": font_size,
                    "bold": is_bold,
                    "italic": bool(payload.get("italic")),
                    "underline": bool(payload.get("underline")),
                    "color": payload.get("color"),
                    "is_list_item": bool(payload.get("is_list_item")),
                })
                block_idx += 1
            elif kind == "table":
                # iter_docx_body_items yields the table dict itself
                # ({"table_index", "rows", ...}); the old read looked for a
                # nested payload["table"] key that never existed, so every DOCX
                # table was silently dropped from the AST.
                rows = payload.get("rows") or []
                blocks.append({
                    "id": f"docx-tbl-{payload.get('table_index', block_idx)}",
                    "kind": "table",
                    "table_index": payload.get("table_index", block_idx),
                    "n_rows": payload.get("n_rows", len(rows)),
                    "n_cols": payload.get("n_cols", len(rows[0]) if rows else 0),
                    "rows": rows,
                })
                block_idx += 1
            elif kind == "image":
                img_desc = {
                    "id": f"docx-img-{payload.get('image_index', len(images))}",
                    "kind": "image",
                    "image_index": payload.get("image_index", len(images)),
                    "mime": payload.get("mime", "image/png"),
                    "width_px": payload.get("width_px"),
                    "height_px": payload.get("height_px"),
                }
                blocks.append(img_desc)
                images.append(img_desc)

    elif file_type == "pdf":
        pages = get_pdf_content(file_path)
        global_block_idx = 0
        for page in pages:
            page_num = page.get("page_num", 0)
            page_blocks = page.get("blocks", [])
            for b in page_blocks:
                text = (b.get("text") or "").strip()
                if not text:
                    continue
                size = float(b.get("size") or 10.0)
                font_name = b.get("font", "")
                is_bold = "bold" in font_name.lower() or "black" in font_name.lower() or "heavy" in font_name.lower()

                block_type = "paragraph"
                heading_level = 0
                if size >= 16 or (size >= 13 and is_bold and len(text) < 80):
                    block_type = "heading"
                    heading_level = 1 if size >= 16 else 2
                elif size >= 12 and is_bold and len(text) < 100:
                    block_type = "heading"
                    heading_level = 3

                blocks.append({
                    "id": f"pdf-b-{page_num}-{b.get('block_no', global_block_idx)}",
                    "kind": block_type,
                    "level": heading_level,
                    "page_num": page_num,
                    "block_no": b.get("block_no", global_block_idx),
                    "bbox": b.get("bbox", []),
                    "text": text,
                    "font_name": font_name,
                    "font_size": size,
                    "bold": is_bold,
                    "color": b.get("color"),
                })
                global_block_idx += 1

    return {
        "title": title,
        "file_type": file_type,
        "total_blocks": len(blocks),
        "total_images": len(images),
        "blocks": blocks,
    }