import fitz  # PyMuPDF
import logging
import re

logger = logging.getLogger(__name__)

def _open_pdf(pdf_path: str):
    """Open a PDF from bytes to avoid PyMuPDF failures with non-ASCII/emoji paths."""
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    return fitz.open(stream=data, filetype="pdf")

def _save_pdf(doc, output_path: str):
    """Write a PDF to disk via Python file I/O to avoid PyMuPDF failures with non-ASCII/emoji paths."""
    pdf_bytes = doc.tobytes(deflate=True, garbage=4)
    with open(output_path, "wb") as fh:
        fh.write(pdf_bytes)

def get_pdf_images_count(pdf_path: str) -> int:
    try:
        doc = _open_pdf(pdf_path)
        xrefs = set()
        for page in doc:
            for img_info in page.get_images(full=True):
                xrefs.add(img_info[0])
        doc.close()
        return len(xrefs)
    except Exception as e:
        logger.error("Error counting images in PDF: %s", e)
        return 0

def apply_pdf_styling(
    pdf_path: str,
    output_path: str,
    font_name: str = None,  # For new additions like headers/footers
    font_size: float = None,  # For new additions like headers/footers
    header_text: str = None,
    footer_text: str = None,
    image_replacements: list = None  # List of dicts: [{"target_index": int, "image_bytes": bytes}]
) -> bool:
    try:
        doc = _open_pdf(pdf_path)

        # 1. Image replacement
        if image_replacements:
            # Map unique image xrefs in order of appearance
            xrefs = []
            for page in doc:
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    if xref not in xrefs:
                        xrefs.append(xref)

            for rep in image_replacements:
                idx = rep.get("target_index")
                img_bytes = rep.get("image_bytes")
                if idx is not None and img_bytes and 0 <= idx < len(xrefs):
                    target_xref = xrefs[idx]
                    try:
                        doc.replace_image(target_xref, stream=img_bytes)
                        logger.info("Successfully replaced PDF image at xref %d (index %d)", target_xref, idx)
                    except Exception as img_err:
                        logger.error("Failed to replace PDF image at index %d: %s", idx, img_err)

        # 2. Add Header & Footer overlays
        # Map frontend font choices to TextWriter base-14 PDF font codes
        pdf_font = "helv"  # Default Helvetica
        if font_name:
            fn_lower = font_name.lower()
            if "times" in fn_lower:
                pdf_font = "tiro"
            elif "courier" in fn_lower:
                pdf_font = "cour"
            elif "helvetica" in fn_lower or "arial" in fn_lower or "calibri" in fn_lower:
                pdf_font = "helv"

        f_size = font_size if font_size else 10.0

        for page in doc:
            # Page dimensions
            width = page.rect.width
            height = page.rect.height

            # Apply Header
            if header_text is not None:
                # White-out original header area (top 45 points)
                header_rect = fitz.Rect(0, 0, width, 45)
                page.draw_rect(header_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

                # Write new header centered and auto-wrapped within the top band
                text_rect = fitz.Rect(10, 5, width - 10, 45)
                page.insert_textbox(
                    text_rect,
                    header_text,
                    fontsize=f_size,
                    fontname=pdf_font,
                    color=(0.2, 0.2, 0.2),
                    align=fitz.TEXT_ALIGN_CENTER,
                    overlay=True
                )

            # Apply Footer
            if footer_text is not None:
                # White-out original footer area (bottom 45 points)
                footer_rect = fitz.Rect(0, height - 45, width, height)
                page.draw_rect(footer_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

                text_rect = fitz.Rect(10, height - 45, width - 10, height - 5)
                page.insert_textbox(
                    text_rect,
                    footer_text,
                    fontsize=f_size,
                    fontname=pdf_font,
                    color=(0.2, 0.2, 0.2),
                    align=fitz.TEXT_ALIGN_CENTER,
                    overlay=True
                )

        _save_pdf(doc, output_path)
        doc.close()
        return True
    except Exception as e:
        logger.error("Error applying PDF styling: %s", e)
        return False

def get_pdf_content(pdf_path: str) -> list:
    try:
        doc = _open_pdf(pdf_path)
        pages = []
        for i, page in enumerate(doc):
            blocks = []
            for b in page.get_text("blocks"):
                # b is (x0, y0, x1, y1, text, block_no, block_type)
                # block_type is 0 for text, 1 for image
                if b[6] == 0:
                    text_content = b[4].strip()
                    if text_content: # Ignore empty text blocks
                        blocks.append({
                            "bbox": [b[0], b[1], b[2], b[3]],
                            "text": text_content,
                            "block_no": b[5]
                        })
            pages.append({
                "page_num": i,
                "blocks": blocks
            })
        doc.close()
        return pages
    except Exception as e:
        logger.error("Error getting PDF content: %s", e)
        return []

def update_pdf_content(pdf_path: str, output_path: str, page_edits: list) -> bool:
    try:
        doc = _open_pdf(pdf_path)
        # page_edits is list of {"page_num": int, "blocks": [{"block_no": int, "bbox": list[float], "text": str}]}
        for p_edit in page_edits:
            page_num = p_edit.get("page_num")
            if page_num is None or page_num < 0 or page_num >= len(doc):
                continue

            page = doc[page_num]
            blocks = p_edit.get("blocks", [])
            for b_edit in blocks:
                bbox = b_edit.get("bbox")
                text = b_edit.get("text")
                if bbox and text is not None:
                    rect = fitz.Rect(bbox)
                    # White-out the block region
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                    # Insert the new text in the textbox (align left = 0, default 9pt helvetica font)
                    page.insert_textbox(rect, text, fontsize=9.0, fontname="helv", color=(0.1, 0.1, 0.1), align=0)

        _save_pdf(doc, output_path)
        doc.close()
        return True
    except Exception as e:
        logger.error("Error updating PDF content: %s", e)
        return False

def find_replace_pdf(pdf_path: str, output_path: str, find_text: str, replace_text: str, case_sensitive: bool = True) -> int:
    try:
        doc = _open_pdf(pdf_path)
        count = 0

        for page in doc:
            rects = page.search_for(find_text)
            targets = []
            for rect in rects:
                if case_sensitive:
                    found = page.get_textbox(rect)
                    if found is None or found.strip() != find_text:
                        continue
                targets.append(rect)

            if not targets:
                continue

            # Use redaction to properly remove original text from the content stream
            for rect in targets:
                page.add_redact_annot(rect)
            page.apply_redactions()

            # Insert replacement text at each original position
            for rect in targets:
                fontsize = max(6.0, rect.height - 2)
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    replace_text,
                    fontsize=fontsize,
                    fontname="helv",
                    color=(0.1, 0.1, 0.1),
                )
                count += 1

        _save_pdf(doc, output_path)
        doc.close()
        return count
    except Exception as e:
        logger.error("Error in find-replace PDF: %s", e)
        return 0

def find_text_variants_pdf(pdf_path: str, find_text: str, case_sensitive: bool = True) -> dict:
    try:
        doc = _open_pdf(pdf_path)
        flags = 0 if case_sensitive else re.IGNORECASE
        prefix_pattern = re.compile(r"\b" + re.escape(find_text) + r"\w*", flags)

        groups = {}
        for i, page in enumerate(doc):
            text = page.get_text() or ""
            for m in prefix_pattern.finditer(text):
                variant = m.group(0)
                g = groups.setdefault(variant, {"variant": variant, "count": 0, "locations": []})
                g["count"] += 1
                ctx_start = max(0, m.start() - 24)
                ctx_end = min(len(text), m.end() + 24)
                context = ("..." if ctx_start > 0 else "") + text[ctx_start:ctx_end] + ("..." if ctx_end < len(text) else "")
                g["locations"].append({"paragraph": f"Page {i + 1}", "context": context})

        doc.close()
        groups_list = sorted(groups.values(), key=lambda g: (-g["count"], g["variant"].lower()))
        return {"total_matches": sum(g["count"] for g in groups_list), "groups": groups_list}
    except Exception as e:
        logger.error("Error finding text variants in PDF: %s", e)
        return {"total_matches": 0, "groups": []}

def selective_replace_pdf(
    pdf_path: str,
    output_path: str,
    find_text: str,
    replace_text: str,
    selected_variants: list,
    case_sensitive: bool = True,
) -> dict:
    try:
        doc = _open_pdf(pdf_path)
        variants = [v for v in selected_variants if v]
        changes = []
        count = 0

        for i, page in enumerate(doc):
            for variant in variants:
                rects = page.search_for(variant)
                if not rects:
                    continue
                targets = []
                for rect in rects:
                    if case_sensitive:
                        found = page.get_textbox(rect)
                        if found is None or found.strip() != variant:
                            continue
                    targets.append(rect)

                for rect in targets:
                    page.add_redact_annot(rect)
                page.apply_redactions()

                for rect in targets:
                    fontsize = max(6.0, rect.height - 2)
                    page.insert_text(
                        (rect.x0, rect.y1 - 2),
                        replace_text,
                        fontsize=fontsize,
                        fontname="helv",
                        color=(0.1, 0.1, 0.1),
                    )
                    count += 1
                    changes.append({
                        "paragraph": f"Page {i + 1}",
                        "old_text": variant,
                        "new_text": replace_text
                    })

        _save_pdf(doc, output_path)
        doc.close()
        return {"matches_replaced": count, "changes": changes}
    except Exception as e:
        logger.error("Error in selective find-replace PDF: %s", e)
        return {"matches_replaced": 0, "changes": []}

def get_pdf_headers_footers(pdf_path: str) -> dict:
    try:
        doc = _open_pdf(pdf_path)
        headers = []
        footers = []
        for i, page in enumerate(doc):
            height = page.rect.height
            width = page.rect.width
            # Extract header text (top 45 points)
            header_rect = fitz.Rect(0, 0, width, 45)
            h_text = page.get_text("text", clip=header_rect).strip()
            if h_text:
                headers.append({"section": i, "text": h_text})

            # Extract footer text (bottom 45 points)
            footer_rect = fitz.Rect(0, height - 45, width, height)
            f_text = page.get_text("text", clip=footer_rect).strip()
            if f_text:
                footers.append({"section": i, "text": f_text})

        doc.close()
        return {"headers": headers, "footers": footers}
    except Exception as e:
        logger.error("Error getting PDF headers/footers: %s", e)
        return {"headers": [], "footers": []}

def update_pdf_header_footer(
    pdf_path: str,
    output_path: str,
    header_text: str = None,
    footer_text: str = None,
) -> bool:
    return apply_pdf_styling(pdf_path, output_path, header_text=header_text, footer_text=footer_text)

