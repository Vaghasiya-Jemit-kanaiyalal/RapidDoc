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

def _page_zone_text(page, rect) -> str:
    try:
        return page.get_text("text", clip=rect).strip()
    except Exception:
        return ""


def apply_pdf_styling(
    pdf_path: str,
    output_path: str,
    font_name: str = None,  # For new additions like headers/footers
    font_size: float = None,  # For new additions like headers/footers
    header_text: str = None,
    footer_text: str = None,
    target_header_text: str = None,
    target_footer_text: str = None,
    image_replacements: list = None,  # List of dicts: [{"target_index": int, "image_bytes": bytes}]
    alignment: str = None
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
        align_map = {
            "left": fitz.TEXT_ALIGN_LEFT,
            "center": fitz.TEXT_ALIGN_CENTER,
            "right": fitz.TEXT_ALIGN_RIGHT,
        }
        align = align_map.get((alignment or "center").lower(), fitz.TEXT_ALIGN_CENTER)

        for page in doc:
            # Page dimensions
            width = page.rect.width
            height = page.rect.height

            # Apply Header (only when targeted/current header matches)
            if header_text is not None:
                header_rect = fitz.Rect(0, 0, width, 45)
                current_header = _page_zone_text(page, header_rect)
                if target_header_text is None or current_header == target_header_text:
                    # White-out original header area (top 45 points)
                    page.draw_rect(header_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                    # Write new header centered and auto-wrapped within the top band
                    text_rect = fitz.Rect(10, 5, width - 10, 45)
                    page.insert_textbox(
                        text_rect,
                        header_text,
                        fontsize=f_size,
                        fontname=pdf_font,
                        color=(0.2, 0.2, 0.2),
                        align=align,
                        overlay=True
                    )

            # Apply Footer (only when targeted/current footer matches)
            if footer_text is not None:
                footer_rect = fitz.Rect(0, height - 45, width, height)
                current_footer = _page_zone_text(page, footer_rect)
                if target_footer_text is None or current_footer == target_footer_text:
                    # White-out original footer area (bottom 45 points)
                    page.draw_rect(footer_rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                    text_rect = fitz.Rect(10, height - 45, width - 10, height - 5)
                    page.insert_textbox(
                        text_rect,
                        footer_text,
                        fontsize=f_size,
                        fontname=pdf_font,
                        color=(0.2, 0.2, 0.2),
                        align=align,
                        overlay=True
                    )

        _save_pdf(doc, output_path)
        doc.close()
        return True
    except Exception as e:
        logger.error("Error applying PDF styling: %s", e)
        return False

def _pick_pdf_font(span_font: str) -> str:
    """Map a detected span font name to a PyMuPDF base-14 font code."""
    fn = (span_font or "").lower()
    if "times" in fn or "serif" in fn:
        return "tiro"
    if "courier" in fn or "cour" in fn or "mono" in fn:
        return "cour"
    return "helv"


def _norm_color(color) -> tuple:
    if isinstance(color, int):
        color = [(color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF]
    if not color:
        return (0.1, 0.1, 0.1)
    vals = list(color)
    if any(v > 1.0 for v in vals):
        vals = [v / 255.0 for v in vals]
    return tuple(min(1.0, max(0.0, float(v))) for v in vals)


def _color_int_to_list(color: int) -> list:
    return [(color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF]


def _pick_block_style(doc, page_num: int, bbox) -> dict:
    """Find the formatting (font code, size, color) of the text spans that
    intersect the given bbox — reused when re-writing edited block text."""
    try:
        rect = fitz.Rect(bbox)
        page = doc[page_num]
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for sp in line.get("spans", []):
                    if fitz.Rect(sp["bbox"]).intersects(rect):
                        return {
                            "font": _pick_pdf_font(sp.get("font", "")),
                            "size": max(6.0, float(sp.get("size", 9.0))),
                            "color": _norm_color(sp.get("color")),
                        }
    except Exception as e:
        logger.error("Error picking PDF block style: %s", e)
    return {"font": "helv", "size": 9.0, "color": (0.1, 0.1, 0.1)}


def _whiteout_and_write_text(page, rect, text: str, style: dict):
    """Replace the region's content: redact the original glyphs, white-out,
    then write the new text using the detected formatting. No highlight is
    drawn — edits look native in the file; highlighting is preview-only.
    Text is auto-shrunk until it fits."""
    # Physically remove the original glyphs inside the rect so re-extraction
    # returns the new text instead of a mix of old + new.
    try:
        page.add_redact_annot(rect)
        page.apply_redactions()
    except Exception:
        pass

    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
    if not text:
        return

    size = style["size"]
    font = style["font"]
    color = style["color"]
    while size >= 6.0:
        rc = page.insert_textbox(
            rect, text, fontsize=size, fontname=font, color=color, align=0, overlay=True
        )
        if rc >= 0:
            return
        size -= 0.5
    # Last resort: baseline insert at the top-left corner (may overflow slightly
    # but guarantees the text is written into the file).
    page.insert_text(
        (rect.x0, rect.y0 + 0.5),
        text,
        fontsize=size,
        fontname=font,
        color=color,
        overlay=True,
    )


def _join_spans(spans: list) -> str:
    """Join text spans without gluing adjacent words together.

    PyMuPDF returns each span with its own bounding box, so two spans that meet
    horizontally are separate words while spans on different lines need a
    newline. Joining everything with "" (as this function used to) produced
    text like "thequickbrownfox" in the editor and in every text export.
    """
    out = []
    previous = None
    for span in spans:
        text = span.get("text", "")
        if not text:
            continue
        if previous is not None:
            x0, y0 = previous["bbox"][0], previous["bbox"][1]
            cx0, cy0 = span["bbox"][0], span["bbox"][1]
            same_line = abs(cy0 - y0) < max(1.0, previous["bbox"][3] - y0) * 0.5
            if same_line:
                # Only insert a space for a real horizontal gap, otherwise
                # kerned pairs would gain phantom spaces.
                if cx0 - previous["bbox"][2] > 0.8 and not out[-1].endswith((" ", "\n")):
                    out.append(" ")
            else:
                out.append("\n")
        out.append(text)
        previous = span
    return "".join(out).strip()


def get_pdf_content(pdf_path: str) -> list:
    try:
        doc = _open_pdf(pdf_path)
        pages = []
        for i, page in enumerate(doc):
            blocks = []
            images = []
            block_no = 0
            for b in page.get_text("dict")["blocks"]:
                if b.get("type") != 0:
                    # Image blocks used to be dropped entirely, which is why the
                    # interactive view never showed pictures. They are reported
                    # separately so text block numbering (used for editing) is
                    # untouched.
                    continue
                spans = [sp for line in b.get("lines", []) for sp in line.get("spans", [])]
                spans = [sp for sp in spans if sp.get("text")]
                text_content = _join_spans(spans)
                if not text_content:
                    continue
                first = spans[0] if spans else {}
                blocks.append({
                    "bbox": list(b["bbox"]),
                    "text": text_content,
                    "block_no": block_no,
                    "font": first.get("font", ""),
                    "size": round(float(first.get("size", 9.0)), 2) if first.get("size") else 9.0,
                    "color": _color_int_to_list(first.get("color", 0)) if isinstance(first.get("color"), int) else [0, 0, 0],
                })
                block_no += 1

            for image_index, info in enumerate(page.get_image_info(xrefs=True)):
                bbox = info.get("bbox")
                images.append({
                    "image_index": _page_image_base(doc, i) + image_index,
                    "page_num": i,
                    "bbox": [round(v, 2) for v in bbox] if bbox else None,
                    "width": info.get("width"),
                    "height": info.get("height"),
                })

            pages.append({
                "page_num": i,
                "blocks": blocks,
                "images": images,
                "width": round(page.rect.width, 2) if page.rect else None,
                "height": round(page.rect.height, 2) if page.rect else None,
            })
        doc.close()
        return pages
    except Exception as e:
        logger.error("Error getting PDF content: %s", e)
        return []


def _page_image_base(doc, page_index: int) -> int:
    """Global image index of a page's first image (matches get_document_images)."""
    total = 0
    for i, p in enumerate(doc):
        if i == page_index:
            return total
        for info in p.get_images(full=True):
            try:
                if doc.extract_image(info[0]).get("image"):
                    total += 1
            except Exception:
                continue
    return total

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
                    style = _pick_block_style(doc, page_num, bbox)
                    _whiteout_and_write_text(page, rect, text, style)

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

            # Insert replacement text at each original position using the
            # original span's formatting (no highlight — preview shows that)
            for rect in targets:
                style = _pick_block_style(doc, page.number, [rect.x0, rect.y0, rect.x1, rect.y1])
                style["size"] = max(6.0, rect.height - 2)
                _whiteout_and_write_text(page, rect, replace_text, style)
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
                    style = _pick_block_style(doc, i, [rect.x0, rect.y0, rect.x1, rect.y1])
                    style["size"] = max(6.0, rect.height - 2)
                    _whiteout_and_write_text(page, rect, replace_text, style)
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
            if h_text and h_text not in headers:
                headers.append(h_text)

            # Extract footer text (bottom 45 points)
            footer_rect = fitz.Rect(0, height - 45, width, height)
            f_text = page.get_text("text", clip=footer_rect).strip()
            if f_text and f_text not in footers:
                footers.append(f_text)

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

