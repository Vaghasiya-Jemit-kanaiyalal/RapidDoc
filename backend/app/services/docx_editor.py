import docx
from docx.shared import Pt
from docx.enum.shape import WD_INLINE_SHAPE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
import copy
import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting-preserving, yellow-highlighting text engine (run-level)
# ---------------------------------------------------------------------------

def _el_text(el) -> str:
    return "".join(t.text or "" for t in el.findall(qn("w:t")))


def _el_set_text(el, text: str) -> None:
    """Set the text of a <w:r> element, keeping a single <w:t> node."""
    ts = el.findall(qn("w:t"))
    if not ts:
        t = OxmlElement("w:t")
        el.append(t)
        ts = [t]
    for t in ts[1:]:
        el.remove(t)
    ts[0].text = text or ""
    ts[0].set(qn("xml:space"), "preserve")


def _el_highlight_yellow(el) -> None:
    """Add <w:highlight w:val="yellow"/> to a run element's rPr."""
    rPr = el.find(qn("w:rPr"))
    if rPr is None:
        rPr = el.makeelement(qn("w:rPr"), {})
        el.insert(0, rPr)
    hl = rPr.find(qn("w:highlight"))
    if hl is None:
        hl = rPr.makeelement(qn("w:highlight"), {})
        rPr.append(hl)
    hl.set(qn("w:val"), "yellow")


def _strip_paragraph_highlights(p) -> None:
    """Remove any <w:highlight> from every run of a paragraph."""
    for run in p.runs:
        rpr = run._r.find(qn("w:rPr"))
        if rpr is None:
            continue
        for hl in rpr.findall(qn("w:highlight")):
            rpr.remove(hl)


def _save_docx_clean(doc, output_path: str) -> None:
    """Save the document WITHOUT any run highlight.

    The working highlight (yellow) is a preview-only affordance — it must
    never leak into the persisted file or any download. The editable text is
    preserved exactly; only the <w:highlight> annotation is dropped.
    """
    try:
        for p in doc.paragraphs:
            _strip_paragraph_highlights(p)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        _strip_paragraph_highlights(p)
        for section in doc.sections:
            for p in section.header.paragraphs:
                _strip_paragraph_highlights(p)
            for p in section.footer.paragraphs:
                _strip_paragraph_highlights(p)
    except Exception as exc:
        logger.warning("Highlight cleanup skipped: %s", exc)
    doc.save(output_path)


def _split_el(el, offset: int):
    """Split a <w:r> element's text at `offset` chars, preserving formatting.
    Returns the NEW right-hand element (or None if no split was needed)."""
    text = _el_text(el)
    if offset <= 0 or offset >= len(text):
        return None
    _el_set_text(el, text[:offset])
    new_el = copy.deepcopy(el)
    _el_set_text(new_el, text[offset:])
    el.addnext(new_el)
    return new_el


def _insert_highlighted_run(p, after_el, new_text: str, template_el):
    """Create a highlighted yellow run from `template_el` formatting."""
    if after_el is None:
        run = p.add_run(new_text)
        _el_highlight_yellow(run._r)
        return run
    new_el = copy.deepcopy(template_el)
    _el_set_text(new_el, new_text)
    _el_highlight_yellow(new_el)
    after_el.addnext(new_el)
    return new_el


def _replace_span(p, start: int, end: int, new_text: str) -> None:
    """Replace the character span [start, end) of paragraph `p` with new_text,
    preserving the surrounding run formatting and highlighting the inserted
    text yellow. Handles pure insertions and pure deletions too."""
    if end < start:
        start, end = end, start
    if end == start and not new_text:
        return

    elements = [r._r for r in p.runs]
    if not elements:
        run = p.add_run(new_text or "")
        if new_text:
            _el_highlight_yellow(run._r)
        return

    def locate(pos):
        cum = 0
        for idx, el in enumerate(elements):
            t = _el_text(el)
            if cum + len(t) > pos:
                return idx, pos - cum
            cum += len(t)
        return len(elements) - 1, len(_el_text(elements[-1]))

    # Pure insertion
    if end == start:
        idx, off = locate(start)
        anchor = elements[idx]
        new_el = copy.deepcopy(anchor)
        _el_set_text(new_el, new_text)
        _el_highlight_yellow(new_el)
        anchor.addnext(new_el)
        return

    # Pure deletion of the entire paragraph
    if not new_text and start == 0 and end == len(p.text):
        for el in elements:
            p._p.remove(el)
        return

    # Split the start element so the replaced region begins on a run boundary
    s_idx, s_off = locate(start)
    if s_off > 0:
        right = _split_el(elements[s_idx], s_off)
        if right is not None:
            elements = [r._r for r in p.runs]
            s_idx += 1

    # Split the end element so the replaced region ends on a run boundary
    elements = [r._r for r in p.runs]
    e_idx, e_off = locate(end - 1)
    e_el = elements[e_idx]
    if e_off < len(_el_text(e_el)) - 1:
        _split_el(e_el, e_off + 1)

    elements = [r._r for r in p.runs]
    s_idx, s_off = locate(start)
    e_idx, e_off = locate(end - 1)

    after_el = elements[e_idx + 1] if e_idx + 1 < len(elements) else None
    template_el = elements[s_idx]

    mid_els = elements[s_idx: e_idx + 1]
    new_el = copy.deepcopy(template_el)
    for el in mid_els:
        p._p.remove(el)
    _el_set_text(new_el, new_text)
    _el_highlight_yellow(new_el)
    if after_el is not None:
        after_el.addprevious(new_el)
    else:
        p._p.append(new_el)


def replace_paragraph_text_preserving_format(p, new_text: str, old_text: str = None) -> bool:
    """Replace paragraph text from old_text to new_text, preserving run
    formatting and highlighting the diff region yellow. Falls back to a
    full-paragraph diff when old_text doesn't match the current text."""
    current = p.text
    if old_text is None:
        old_text = current
    elif old_text != current:
        if old_text not in current:
            old_text = current
        else:
            # Substring-style edit within a larger paragraph
            start = current.find(old_text)
            _replace_span(p, start, start + len(old_text), new_text)
            return p.text != current

    if old_text == new_text:
        return False

    if not old_text:
        if not p.runs:
            run = p.add_run(new_text)
            _el_highlight_yellow(run._r)
        else:
            # Insert at the very start of the paragraph
            _replace_span(p, 0, 0, new_text)
        return True

    if not new_text:
        _replace_span(p, 0, len(old_text), "")
        return True

    # Common prefix / suffix diff -> highlight only the changed middle
    n = min(len(old_text), len(new_text))
    plen = 0
    while plen < n and old_text[plen] == new_text[plen]:
        plen += 1
    slen = 0
    while (slen < n - plen
           and old_text[len(old_text) - 1 - slen] == new_text[len(new_text) - 1 - slen]):
        slen += 1
    start = plen
    end = len(old_text) - slen
    mid_new = new_text[plen: len(new_text) - slen] if slen else new_text[plen:]

    _replace_span(p, start, end, mid_new)
    return True


def _replace_occurrences(p, find_text: str, replace_text: str, case_sensitive: bool = True) -> int:
    """Replace every occurrence of find_text in paragraph p preserving run
    formatting, highlighting changed spans yellow. Returns match count."""
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(find_text), flags)
    matches = list(pattern.finditer(p.text))
    for m in reversed(matches):
        _replace_span(p, m.start(), m.end(), replace_text)
    return len(matches)

def get_docx_images_count(doc_path: str) -> int:
    """Number of distinct images in a DOCX.

    This used to count ``doc.inline_shapes`` of type PICTURE, which silently
    under-reports: anchored (floating) pictures are not inline shapes, so a
    document with one floating logo reported 6 while the editor - which walks
    the body XML - correctly showed 7. Two different numbers for "how many
    images does this document have" is exactly the kind of thing that makes a
    UI look broken, so the count now comes from the same traversal the content
    endpoint uses and is guaranteed to agree with it.
    """
    try:
        doc = docx.Document(doc_path)
        # Apply the same part-level filter as get_docx_image_parts so the two
        # can never disagree: a relationship with no part, or one whose blob
        # cannot be read / is empty, is skipped there and must be skipped here.
        count = 0
        for r_id, _w, _h, _anchor in _iter_document_images(doc, set()):
            part = doc.part.related_parts.get(r_id)
            if part is None:
                continue
            try:
                if not part.blob:
                    continue
            except Exception:
                continue
            count += 1
        return count
    except Exception as e:
        logger.error("Error counting images in DOCX: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Full-fidelity content extraction (paragraphs + tables + images, in order)
#
# get_docx_content() above only walks doc.paragraphs, which silently drops every
# table and every image in the document. The interactive view needs the real
# body order, so these helpers walk the body XML directly.
# ---------------------------------------------------------------------------

_EMU_PER_PX = 9525


def _paragraph_style_name(paragraph) -> str:
    """Best-effort style name, '' when the style cannot be resolved."""
    try:
        style = paragraph.style
        if style is None:
            return ""
        return (style.name or "").strip()
    except Exception:
        return ""


def _heading_level(paragraph, style_name: str = "") -> int:
    """Outline level 1-9 for headings, 0 for body text.

    Heading information used to be thrown away during extraction, which is why
    PPTX export had to guess that the first paragraph of every 5-paragraph
    chunk was a title. Both the style name and the explicit <w:outlineLvl>
    property are consulted so hand-formatted headings are detected too.
    """
    if not style_name:
        style_name = _paragraph_style_name(paragraph)

    lowered = style_name.lower()
    if lowered.startswith("heading "):
        suffix = lowered[len("heading "):].strip()
        if suffix.isdigit():
            level = int(suffix)
            return level if 1 <= level <= 9 else 0

    # Localised style names (Word stores the UI language, not "Heading").
    for level in range(1, 10):
        for prefix in ("heading", "berschrift", "titre", "encabezado", "titolo"):
            if lowered == f"{prefix}{level}":
                return level

    # Explicit outline level in the paragraph properties beats the style name.
    try:
        pPr = paragraph._p.pPr
        if pPr is not None:
            outline = pPr.find(qn("w:outlineLvl"))
            if outline is not None:
                raw = outline.get(qn("w:val"))
                if raw is not None and raw.isdigit() and int(raw) <= 8:
                    return int(raw) + 1
    except Exception:
        pass

    return 0


def _is_list_item(paragraph, style_name: str = "") -> bool:
    """True when the paragraph is a bullet/numbered list entry."""
    try:
        pPr = paragraph._p.pPr
        if pPr is not None and pPr.find(qn("w:numPr")) is not None:
            return True
    except Exception:
        pass
    if not style_name:
        style_name = _paragraph_style_name(paragraph)
    return "list" in style_name.lower()


def _paragraph_descriptor(paragraph, index: int) -> dict:
    """Style snapshot for one paragraph, matching get_docx_content()'s shape."""
    run_font = next((r for r in paragraph.runs if r.text.strip()), None)
    color = None
    try:
        if run_font is not None and run_font.font.color is not None \
                and run_font.font.color.rgb is not None:
            color = f"#{run_font.font.color.rgb}"
    except Exception:
        color = None
    style_name = _paragraph_style_name(paragraph)
    return {
        "index": index,
        "text": paragraph.text,
        "font_name": (run_font.font.name if run_font is not None else None),
        "font_size": (run_font.font.size.pt if run_font is not None and run_font.font.size is not None else None),
        "bold": (run_font.font.bold if run_font is not None else None),
        "italic": (run_font.font.italic if run_font is not None else None),
        "underline": (run_font.font.underline if run_font is not None else None),
        "color": color,
        # Structural signals the PPTX builder needs. Additive only, so every
        # existing consumer of this dict keeps working.
        "style": style_name,
        "heading_level": _heading_level(paragraph, style_name),
        "is_list_item": _is_list_item(paragraph, style_name),
    }


def _iter_blips_in(element, doc):
    """Yield ``(rId, width_emu, height_emu)`` for every picture inside an element.

    ``a:blip`` is the low-level element behind both inline and anchored images,
    so this catches floating images that ``doc.inline_shapes`` never reports.
    """
    for drawing in element.iter():
        if drawing.tag not in (qn("w:drawing"), qn("w:pict")):
            continue
        for blip in drawing.iter(qn("a:blip")):
            r_id = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
            if not r_id:
                continue
            width = height = None
            for extent in drawing.iter(qn("wp:extent")):
                try:
                    width = int(extent.get("cx"))
                    height = int(extent.get("cy"))
                except (TypeError, ValueError):
                    width = height = None
                break
            yield r_id, width, height


def _iter_document_images(doc, seen: set):
    """Yield ``(rId, width, height, anchor_index)`` for each *distinct* image, in order.

    Shared with :func:`get_docx_image_parts` so the two agree exactly on
    ordering and on skipping logos that the same relationship part repeats.

    ``anchor_index`` is the number of body paragraphs that precede the picture,
    which is what lets a consumer (notably PPTX export) put an image on the
    slide built from the text it illustrates. It is ``None`` for pictures that
    live inside a table, where there is no single owning paragraph.
    """
    paragraph_count = 0
    for child in doc.element.body.iterchildren():
        is_paragraph = child.tag == qn("w:p")
        for r_id, width, height in _iter_blips_in(child, doc):
            if r_id in seen:
                continue
            seen.add(r_id)
            yield r_id, width, height, (paragraph_count if is_paragraph else None)
        if is_paragraph:
            paragraph_count += 1


def iter_docx_body_items(doc_path: str):
    """Yield ``(kind, payload)`` for every body item in true document order.

    ``kind`` is ``"paragraph"``, ``"table"`` or ``"image"``. Paragraph payloads
    keep the same ``index`` that :func:`get_docx_content` assigns (their
    position in ``doc.paragraphs``) so the existing edit/save/rewrite flows -
    which key off that index - keep working unchanged.

    Note: lxml hands out a fresh Python proxy object each time an element is
    reached, so the body children cannot be matched to ``doc.paragraphs`` by
    object identity. ``doc.paragraphs``/``doc.tables`` are simply the direct
    ``w:p``/``w:tbl`` children of the body in order, so counting is both exact
    and free of that trap.
    """
    doc = docx.Document(doc_path)
    body = doc._body
    paragraph_no = 0
    table_no = 0
    image_counter = 0
    seen_rids = set()

    def _images_for(child, anchor_index):
        nonlocal image_counter
        for r_id, width, height in _iter_blips_in(child, doc):
            if r_id in seen_rids:
                continue
            seen_rids.add(r_id)
            part = doc.part.related_parts.get(r_id)
            if part is None:
                continue
            try:
                blob = part.blob
            except Exception:
                continue
            if not blob:
                continue
            payload = {
                "image_index": image_counter,
                "anchor_index": anchor_index,
                "mime": getattr(part, "content_type", None) or "image/png",
                "width_px": round(width / _EMU_PER_PX) if width else None,
                "height_px": round(height / _EMU_PER_PX) if height else None,
            }
            image_counter += 1
            yield payload

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "paragraph", _paragraph_descriptor(
                Paragraph(child, body), paragraph_no
            )
            paragraph_no += 1
            # Pictures anchored in a paragraph are reported after it so the
            # image keeps its position relative to the surrounding text.
            for payload in _images_for(child, paragraph_no - 1):
                yield "image", payload

        elif child.tag == qn("w:tbl"):
            table = Table(child, body)
            rows = [
                ["\n".join(p.text for p in cell.paragraphs) for cell in row.cells]
                for row in table.rows
            ]
            yield "table", {
                "table_index": table_no,
                "rows": rows,
                "n_rows": len(rows),
                "n_cols": max((len(r) for r in rows), default=0),
            }
            table_no += 1
            # Logos and diagrams inside cells used to vanish entirely.
            for payload in _images_for(child, None):
                yield "image", payload


def get_docx_document_view(doc_path: str) -> dict:
    """Everything the interactive editor needs, from a *single* parse.

    ``GET /{id}/content`` used to call :func:`get_docx_content`,
    :func:`iter_docx_body_items` and :func:`get_docx_image_parts` in sequence.
    Each one re-opens the .docx zip and re-parses the document XML, so every
    single request paid for three full parses of the whole file - the dominant
    cost when opening a large report.

    All three read the same body walk with the same de-duplication and the same
    image index space, so one pass produces identical output:

    * ``content`` - the paragraph descriptor list, in the exact shape (and index
      order) the save / rewrite / find-replace flows are keyed to.
    * ``blocks``  - the ordered paragraph/table/image stream for rendering.
    * ``images``  - image descriptors for the image endpoint.

    Image bytes are deliberately *not* included: sending them here would bloat
    every content request, and the frontend already fetches them individually.
    """
    content = []
    blocks = []
    images = []

    for kind, payload in iter_docx_body_items(doc_path):
        if kind == "paragraph":
            content.append(payload)
        elif kind == "image":
            images.append({
                "index": payload["image_index"],
                "mime": payload["mime"],
                "width": payload.get("width_px"),
                "height": payload.get("height_px"),
            })
        blocks.append({"kind": kind, **payload})

    return {"content": content, "blocks": blocks, "images": images}


def get_docx_image_parts(doc_path: str) -> list:
    """Every image in the document, in reading order, with its bytes.

    The ordering matches the ``image_index`` values produced by
    :func:`iter_docx_body_items` and the ``index`` used by the image-replacement
    feature, so one index space is shared by reads and writes.
    """
    doc = docx.Document(doc_path)
    parts = []
    counter = 0

    for r_id, width, height, anchor_index in _iter_document_images(doc, set()):
        part = doc.part.related_parts.get(r_id)
        if part is None:
            continue
        try:
            blob = part.blob
        except Exception:
            continue
        if not blob:
            continue
        parts.append({
            "index": counter,
            "mime": getattr(part, "content_type", None) or "image/png",
            "width": round(width / _EMU_PER_PX) if width else None,
            "height": round(height / _EMU_PER_PX) if height else None,
            "anchor_index": anchor_index,
            "blob": blob,
        })
        counter += 1
    return parts

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

        _save_docx_clean(doc, output_path)
        return True
    except Exception as e:
        logger.error("Error applying DOCX styling: %s", e)
        return False

def get_docx_content(doc_path: str) -> list:
    try:
        doc = docx.Document(doc_path)
        content = []
        for i, p in enumerate(doc.paragraphs):
            run_font = next((r for r in p.runs if r.text.strip()), None)

            def _rgb(run):
                try:
                    if run is not None and run.font.color is not None and run.font.color.rgb is not None:
                        return f"#{run.font.color.rgb}"
                except Exception:
                    pass
                return None

            content.append({
                "index": i,
                "text": p.text,
                "font_name": (run_font.font.name if run_font is not None else None),
                "font_size": (run_font.font.size.pt if run_font is not None and run_font.font.size is not None else None),
                "bold": (run_font.font.bold if run_font is not None else None),
                "italic": (run_font.font.italic if run_font is not None else None),
                "underline": (run_font.font.underline if run_font is not None else None),
                "color": _rgb(run_font)
            })
        return content
    except Exception as e:
        logger.error("Error getting DOCX content: %s", e)
        return []

def get_docx_headers_footers(doc_path: str) -> dict:
    try:
        doc = docx.Document(doc_path)
        headers = []
        footers = []
        seen_headers = set()
        seen_footers = set()
        for section in doc.sections:
            header_text = "\n".join(p.text for p in section.header.paragraphs).strip()
            # Keep document order and drop exact repeats, rather than collecting
            # into a set: a set has no defined iteration order, so the "first"
            # header the editor renders could differ between runs.
            if header_text and header_text not in seen_headers:
                seen_headers.add(header_text)
                headers.append(header_text)
            footer_text = "\n".join(p.text for p in section.footer.paragraphs).strip()
            if footer_text and footer_text not in seen_footers:
                seen_footers.add(footer_text)
                footers.append(footer_text)
        return {
            "headers": headers,
            "footers": footers
        }
    except Exception as e:
        logger.error("Error getting DOCX headers/footers: %s", e)
        return {"headers": [], "footers": []}

def _set_table_cell_text(table, row_idx: int, col_idx: int, new_text: str) -> bool:
    """Write `new_text` into one table cell, preserving its formatting.

    Returns True when the cell was found and its text actually changed.

    Addressing (``table.rows[row].cells[col]``) is deliberately identical to what
    :func:`iter_docx_body_items` uses when it *reads* cells, so the cell the
    editor displayed at (r, c) is the same cell this writes to - including for
    merged cells, where python-docx resolves both grid positions to the same
    underlying ``<w:tc>``.

    A cell routinely holds several paragraphs and the reader joins them with
    ``"\\n"``, so a single string edit is mapped back onto those paragraphs
    line-by-line instead of collapsing them (which would silently destroy text)
    or refusing the edit (which is what made table content read-only in practice
    - most real lab-report cells hold 2+ paragraphs).
    """
    try:
        rows = table.rows
        if row_idx < 0 or row_idx >= len(rows):
            return False
        row = rows[row_idx]
        if col_idx < 0 or col_idx >= len(row.cells):
            return False
        cell = row.cells[col_idx]
    except (IndexError, KeyError, TypeError, ValueError):
        return False

    if not cell.paragraphs:
        if not new_text:
            return False
        cell.add_paragraph("")

    before = "\n".join(p.text for p in cell.paragraphs)
    if before == new_text:
        return False

    lines = new_text.split("\n")
    paragraphs = list(cell.paragraphs)

    for offset, line in enumerate(lines):
        if offset < len(paragraphs):
            target = paragraphs[offset]
            if target.text != line:
                replace_paragraph_text_preserving_format(target, line, old_text=target.text)
        else:
            # More lines than the cell had paragraphs: append the extras.
            cell.add_paragraph(line)

    # Fewer lines than paragraphs: drop the now-empty trailing ones so the cell
    # reads back exactly as edited. A cell must always keep at least one
    # paragraph, so the loop stops at 1.
    if len(lines) < len(paragraphs):
        for target in paragraphs[len(lines):]:
            if len(cell.paragraphs) <= 1:
                break
            try:
                target._p.getparent().remove(target._p)
            except Exception:
                logger.warning("Could not remove an emptied paragraph from cell (%s, %s).",
                               row_idx, col_idx)
                break

    return True


def update_docx_content(doc_path: str, output_path: str, edits: list) -> bool:
    """Apply paragraph and table-cell edits to a DOCX file.

    Each edit is ``{"index": int, "text": str}`` for a body paragraph, or
    ``{"table_index": int, "row": int, "col": int, "text": str}`` for a table
    cell. Table edits used to be dropped on the floor because this function
    only walked ``doc.paragraphs``, which is why table content could be read in
    the editor but never written back.
    """
    try:
        doc = docx.Document(doc_path)

        paragraph_edits = {}
        cell_edits = {}
        for edit in edits or []:
            if not isinstance(edit, dict):
                continue
            if edit.get("table_index") is not None:
                cell_edits[edit["table_index"]] = cell_edits.get(edit["table_index"], {})
                cell_edits[edit["table_index"]][(edit.get("row"), edit.get("col"))] = edit.get("text") or ""
            elif edit.get("index") is not None:
                paragraph_edits[edit["index"]] = edit.get("text") or ""

        for idx, p in enumerate(doc.paragraphs):
            if idx in paragraph_edits:
                new_text = paragraph_edits[idx]
                if p.text != new_text:
                    replace_paragraph_text_preserving_format(p, new_text, old_text=p.text)

        if cell_edits:
            tables = doc.tables
            for table_index, cells in cell_edits.items():
                if table_index < 0 or table_index >= len(tables):
                    logger.warning(
                        "Table edit targets table %s but the document has %d table(s).",
                        table_index, len(tables),
                    )
                    continue
                table = tables[table_index]
                for (row_idx, col_idx), new_text in cells.items():
                    _set_table_cell_text(table, row_idx, col_idx, new_text)

        _save_docx_clean(doc, output_path)
        return True
    except Exception as e:
        logger.error("Error updating DOCX content: %s", e)
        return False

def find_replace_docx(doc_path: str, output_path: str, find_text: str, replace_text: str, case_sensitive: bool = True) -> int:
    try:
        doc = docx.Document(doc_path)
        count = 0

        # 1. Replace in body paragraphs
        for p in doc.paragraphs:
            count += _replace_occurrences(p, find_text, replace_text, case_sensitive)

        # 2. Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        count += _replace_occurrences(p, find_text, replace_text, case_sensitive)

        _save_docx_clean(doc, output_path)
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
            original = p.text or ""
            paragraph_count = 0
            for variant in variants:
                pattern = re.compile(r"\b" + re.escape(variant) + r"\b", flags)
                matches = list(pattern.finditer(p.text or ""))
                for m in reversed(matches):
                    _replace_span(p, m.start(), m.end(), replace_text)
                    paragraph_count += 1
            count += paragraph_count
            if paragraph_count > 0:
                changes.append({
                    "paragraph": loc["label"],
                    "index": loc.get("index"),
                    "old_text": original,
                    "new_text": p.text,
                })

        _save_docx_clean(doc, output_path)
        return {"matches_replaced": count, "changes": changes}
    except Exception as e:
        logger.error("Error in selective find-replace DOCX: %s", e)
        return {"matches_replaced": 0, "changes": []}
