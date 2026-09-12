import docx
from docx.shared import Pt
from docx.enum.shape import WD_INLINE_SHAPE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
import logging
import re

logger = logging.getLogger(__name__)

def get_docx_images_count(doc_path: str) -> int:
    try:
        doc = docx.Document(doc_path)
        count = 0
        for shape in doc.inline_shapes:
            if shape.type == WD_INLINE_SHAPE_TYPE.PICTURE:
                count += 1
        return count
    except Exception as e:
        logger.error("Error counting images in DOCX: %s", e)
        return 0

def apply_docx_styling(
    doc_path: str,
    output_path: str,
    font_name: str = None,
    font_size: float = None,
    header_text: str = None,
    footer_text: str = None,
    target_header_text: str = None,
    target_footer_text: str = None,
    image_replacements: list = None,  # List of dicts: [{"target_index": int, "image_bytes": bytes}]
    alignment: str = None
) -> bool:
    try:
        doc = docx.Document(doc_path)

        align_map = {
            'left': WD_ALIGN_PARAGRAPH.LEFT,
            'center': WD_ALIGN_PARAGRAPH.CENTER,
            'right': WD_ALIGN_PARAGRAPH.RIGHT,
            'justify': WD_ALIGN_PARAGRAPH.JUSTIFY
        }

        # 1. Update font and sizes for paragraphs
        if font_name or font_size:
            # Change font of regular paragraphs
            for paragraph in doc.paragraphs:
                for run in paragraph.runs:
                    if font_name:
                        run.font.name = font_name
                    if font_size:
                        run.font.size = Pt(font_size)

            # Change font inside tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                if font_name:
                                    run.font.name = font_name
                                if font_size:
                                    run.font.size = Pt(font_size)

        # 2. Update Header/Footer
        for section in doc.sections:
            if header_text is not None:
                header = section.header
                current_header_text = "\n".join(p.text for p in header.paragraphs).strip()
                if target_header_text is None or current_header_text == target_header_text:
                    # Clear existing header paragraphs
                    for p in header.paragraphs:
                        p.text = ""
                    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
                    p.text = header_text
                    if alignment and alignment.lower() in align_map:
                        p.alignment = align_map[alignment.lower()]
                    for run in p.runs:
                        if font_name:
                            run.font.name = font_name
                        if font_size:
                            run.font.size = Pt(font_size)

            if footer_text is not None:
                footer = section.footer
                current_footer_text = "\n".join(p.text for p in footer.paragraphs).strip()
                if target_footer_text is None or current_footer_text == target_footer_text:
                    # Clear existing footer paragraphs
                    for p in footer.paragraphs:
                        p.text = ""
                    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
                    p.text = footer_text
                    if alignment and alignment.lower() in align_map:
                        p.alignment = align_map[alignment.lower()]
                    for run in p.runs:
                        if font_name:
                            run.font.name = font_name
                        if font_size:
                            run.font.size = Pt(font_size)

        # 3. Image replacement
        if image_replacements:
            # Collect all shapes that are pictures
            pics = []
            for shape in doc.inline_shapes:
                if shape.type == WD_INLINE_SHAPE_TYPE.PICTURE:
                    pics.append(shape)

            for rep in image_replacements:
                idx = rep.get("target_index")
                img_bytes = rep.get("image_bytes")
                if idx is not None and img_bytes and 0 <= idx < len(pics):
                    target_shape = pics[idx]
                    try:
                        # Access internal XML element for embedding
                        rId = target_shape._inline.graphic.graphicData.pic.blipFill.blip.embed
                        # Update binary blob in Zip archive package
                        image_part = doc.part.related_parts[rId]
                        image_part._blob = img_bytes
                        logger.info("Successfully replaced DOCX image at index %d", idx)
                    except Exception as img_err:
                        logger.error("Failed to replace image at index %d: %s", idx, img_err)

        doc.save(output_path)
        return True
    except Exception as e:
        logger.error("Error applying DOCX styling: %s", e)
        return False

def get_docx_content(doc_path: str) -> list:
    try:
        doc = docx.Document(doc_path)
        content = []
        for i, p in enumerate(doc.paragraphs):
            # Only send paragraphs with text, but allow empty ones in list for tracking
            content.append({
                "index": i,
                "text": p.text
            })
        return content
    except Exception as e:
        logger.error("Error getting DOCX content: %s", e)
        return []

def get_docx_headers_footers(doc_path: str) -> dict:
    try:
        doc = docx.Document(doc_path)
        headers = set()
        footers = set()
        for section in doc.sections:
            header_text = "\n".join(p.text for p in section.header.paragraphs).strip()
            if header_text:
                headers.add(header_text)
            footer_text = "\n".join(p.text for p in section.footer.paragraphs).strip()
            if footer_text:
                footers.add(footer_text)
        return {
            "headers": list(headers),
            "footers": list(footers)
        }
    except Exception as e:
        logger.error("Error getting DOCX headers/footers: %s", e)
        return {"headers": [], "footers": []}

def update_docx_content(doc_path: str, output_path: str, edits: list) -> bool:
    try:
        doc = docx.Document(doc_path)
        # edits is list of {"index": int, "text": str}
        edit_map = {edit["index"]: edit["text"] for edit in edits}
        
        for idx, p in enumerate(doc.paragraphs):
            if idx in edit_map:
                new_text = edit_map[idx]
                if p.text != new_text:
                    if p.runs:
                        # Update first run text to preserve styling and clear subsequent runs
                        p.runs[0].text = new_text
                        for run in p.runs[1:]:
                            run.text = ""
                    else:
                        p.text = new_text
        
        doc.save(output_path)
        return True
    except Exception as e:
        logger.error("Error updating DOCX content: %s", e)
        return False

def find_replace_docx(doc_path: str, output_path: str, find_text: str, replace_text: str, case_sensitive: bool = True) -> int:
    try:
        doc = docx.Document(doc_path)
        count = 0
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(find_text), flags)

        # 1. Replace in body paragraphs
        for p in doc.paragraphs:
            if pattern.search(p.text):
                new_text, n = pattern.subn(replace_text, p.text)
                if n > 0:
                    count += n
                    if p.runs:
                        p.runs[0].text = new_text
                        for run in p.runs[1:]:
                            run.text = ""
                    else:
                        p.text = new_text

        # 2. Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if pattern.search(p.text):
                            new_text, n = pattern.subn(replace_text, p.text)
                            if n > 0:
                                count += n
                                if p.runs:
                                    p.runs[0].text = new_text
                                    for run in p.runs[1:]:
                                        run.text = ""
                                else:
                                    p.text = new_text

        doc.save(output_path)
        return count
    except Exception as e:
        logger.error("Error in find-replace DOCX: %s", e)
        return 0

def _collect_docx_paragraphs(doc):
    """Yield (location_label, paragraph) pairs for body paragraphs, table cells,
    and header/footer paragraphs."""
    for i, p in enumerate(doc.paragraphs):
        yield {"kind": "body", "index": i, "label": f"Paragraph {i + 1}"}, p
    for t_idx, table in enumerate(doc.tables):
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                for p_idx, p in enumerate(cell.paragraphs):
                    yield {
                        "kind": "table",
                        "table": t_idx,
                        "row": r_idx,
                        "cell": c_idx,
                        "label": f"Table {t_idx + 1}, row {r_idx + 1}, cell {c_idx + 1}",
                    }, p
    for s_idx, section in enumerate(doc.sections):
        for p_idx, p in enumerate(section.header.paragraphs):
            if p.text and p.text.strip():
                yield {
                    "kind": "header",
                    "section": s_idx,
                    "label": f"Header {p_idx + 1}",
                }, p
        for p_idx, p in enumerate(section.footer.paragraphs):
            if p.text and p.text.strip():
                yield {
                    "kind": "footer",
                    "section": s_idx,
                    "label": f"Footer {p_idx + 1}",
                }, p

def find_text_variants(doc_path: str, find_text: str, case_sensitive: bool = True) -> dict:
    """Find all word variants of a search term across the document, grouped.

    Variants are whole words that share the search term as a case-insensitive
    prefix (e.g. searching "print" yields "print", "printf", "printy").
    Returns {"total_matches", "groups": [{"variant", "count", "locations":
    [{"paragraph": label, "context": "..."}]}]}
    """
    try:
        doc = docx.Document(doc_path)
        flags = 0 if case_sensitive else re.IGNORECASE
        prefix_pattern = re.compile(r"\b" + re.escape(find_text) + r"\w*", flags)

        groups = {}
        for loc, p in _collect_docx_paragraphs(doc):
            text = p.text or ""
            for m in prefix_pattern.finditer(text):
                variant = m.group(0)
                g = groups.setdefault(variant, {"variant": variant, "count": 0, "locations": []})
                g["count"] += 1
                ctx_start = max(0, m.start() - 24)
                ctx_end = min(len(text), m.end() + 24)
                context = ("..." if ctx_start > 0 else "") + text[ctx_start:ctx_end] + ("..." if ctx_end < len(text) else "")
                g["locations"].append({"paragraph": loc["label"], "context": context})

        groups_list = sorted(groups.values(), key=lambda g: (-g["count"], g["variant"].lower()))
        return {"total_matches": sum(g["count"] for g in groups_list), "groups": groups_list}
    except Exception as e:
        logger.error("Error finding text variants in DOCX: %s", e)
        return {"total_matches": 0, "groups": []}

def selective_replace_docx(
    doc_path: str,
    output_path: str,
    find_text: str,
    replace_text: str,
    selected_variants: list,
    case_sensitive: bool = True,
) -> dict:
    """Replace ONLY the user-selected variants, returning change info for highlighting.

    Returns {"matches_replaced": int, "changes": [
        {"paragraph": label, "index": int|None, "old_text": str, "new_text": str}
    ]}
    """
    try:
        doc = docx.Document(doc_path)
        flags = 0 if case_sensitive else re.IGNORECASE
        variants = [v for v in selected_variants if v]
        changes = []
        count = 0

        for loc, p in _collect_docx_paragraphs(doc):
            text = p.text or ""
            original = text
            for variant in variants:
                pattern = re.compile(r"\b" + re.escape(variant) + r"\b", flags)
                text, n = pattern.subn(replace_text, text)
                count += n
            if text != original:
                changes.append({
                    "paragraph": loc["label"],
                    "index": loc.get("index"),
                    "old_text": original,
                    "new_text": text,
                })
                if p.runs:
                    p.runs[0].text = text
                    for run in p.runs[1:]:
                        run.text = ""
                else:
                    p.text = text

        doc.save(output_path)
        return {"matches_replaced": count, "changes": changes}
    except Exception as e:
        logger.error("Error in selective find-replace DOCX: %s", e)
        return {"matches_replaced": 0, "changes": []}
