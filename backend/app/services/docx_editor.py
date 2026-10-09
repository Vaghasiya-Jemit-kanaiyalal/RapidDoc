import docx
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
from docx.table import Table
from docx.text.paragraph import Paragraph
import copy
import io
import logging
import re

from . import header_footer as hf
from .image_geometry import ResizeError, describe_change, resolve_target_box

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting-preserving, yellow-highlighting text engine (run-level)
# ---------------------------------------------------------------------------

def _el_text(el) -> str:
    """Rendered text of a <w:r> element, including soft line breaks.

    ``<w:br/>`` inside a run becomes ``"\\n"``; python-docx's ``Run.text``
    drops it entirely, which made a paragraph with a manual line break read as
    two words glued together in the editor and destroyed the break on edit.
    """
    parts = []
    for child in el:
        if child.tag == qn("w:t"):
            parts.append(child.text or "")
        elif child.tag == qn("w:br"):
            parts.append("\n")
    return "".join(parts)


def _el_set_text(el, text: str) -> None:
    """Set the text of a <w:r> element, keeping a single <w:t> node.

    Any existing ``<w:br/>`` nodes are dropped first: they would otherwise
    survive inside cloned runs and resurface as phantom newlines after the
    text of a line-broken paragraph is rewritten.
    """
    for br in el.findall(qn("w:br")):
        el.remove(br)
    ts = el.findall(qn("w:t"))
    if not ts:
        t = OxmlElement("w:t")
        el.append(t)
        ts = [t]
    for t in ts[1:]:
        el.remove(t)
    ts[0].text = text or ""
    ts[0].set(qn("xml:space"), "preserve")


def _p_text(p) -> str:
    """Full rendered text of a paragraph, newlines included.

    The whole edit engine measures against this instead of ``p.text`` so that
    offsets stay aligned with the run span math in :func:`_replace_span`, which
    counts characters through :func:`_el_text`.
    """
    return "".join(_el_text(r._r) for r in p.runs)


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
    if not new_text and start == 0 and end == len(_p_text(p)):
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
    current = _p_text(p)
    if old_text is None:
        old_text = current
    elif old_text != current:
        if old_text not in current:
            old_text = current
        else:
            # Substring-style edit within a larger paragraph
            start = current.find(old_text)
            _replace_span(p, start, start + len(old_text), new_text)
            return _p_text(p) != current

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
    matches = list(pattern.finditer(_p_text(p)))
    for m in reversed(matches):
        _replace_span(p, m.start(), m.end(), replace_text)
    return len(matches)

def get_docx_images_count(doc_path: str) -> int:
    """Number of distinct images in a DOCX.

    Sourced from the one canonical traversal (:func:`collect_docx_image_targets`)
    that the content endpoint, the image endpoint and the replacement writer all
    use, so "how many images" can never disagree with "which image is #3".

    This used to count ``doc.inline_shapes`` of type PICTURE, which silently
    under-reports: anchored (floating) pictures are not inline shapes, so a
    document with one floating logo reported 6 while the editor - which walks
    the body XML - correctly showed 7.
    """
    try:
        doc = docx.Document(doc_path)
        return len(collect_docx_image_targets(doc))
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

    runs_data = []
    for r in paragraph.runs:
        if not r.text:
            continue
        r_color = None
        try:
            if r.font.color and r.font.color.rgb:
                r_color = f"#{r.font.color.rgb}"
        except Exception:
            pass
        runs_data.append({
            "text": r.text,
            "bold": bool(r.font.bold) if r.font.bold is not None else False,
            "italic": bool(r.font.italic) if r.font.italic is not None else False,
            "underline": bool(r.font.underline) if r.font.underline is not None else False,
            "strike": bool(r.font.strike) if r.font.strike is not None else False,
            "color": r_color,
            "font_size": r.font.size.pt if r.font.size is not None else None,
            "font_name": r.font.name or None,
        })

    align_str = "left"
    if paragraph.alignment is not None:
        try:
            align_str = str(paragraph.alignment).split(".")[-1].lower()
        except Exception:
            align_str = "left"

    return {
        "index": index,
        "text": _p_text(paragraph),
        "runs": runs_data,
        "alignment": align_str,
        "font_name": (run_font.font.name if run_font is not None else None),
        "font_size": (run_font.font.size.pt if run_font is not None and run_font.font.size is not None else None),
        "bold": (run_font.font.bold if run_font is not None else None),
        "italic": (run_font.font.italic if run_font is not None else None),
        "underline": (run_font.font.underline if run_font is not None else None),
        "color": color,
        "style": style_name,
        "heading_level": _heading_level(paragraph, style_name),
        "is_list_item": _is_list_item(paragraph, style_name),
    }


def _iter_blips_in(element, doc):
    """Yield ``(rId, width_emu, height_emu, blip)`` for every picture in an element.

    ``a:blip`` is the low-level element behind both inline and anchored images,
    so this catches floating images that ``doc.inline_shapes`` never reports.

    The ``blip`` element itself is yielded because the replacement writer needs
    to repoint it at a new image part and rewrite the extents around it - neither
    is reachable from a high-level python-docx shape object.
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
            yield r_id, width, height, blip


def collect_docx_image_targets(doc) -> list:
    """THE canonical DOCX image index space. One traversal, one numbering.

    Every image-related feature in the app resolves an image by the integer this
    function assigns, so there is exactly one definition of what "image 3" means:

      * ``GET /{id}/content``          - renders the tiles
      * ``GET /{id}/images/{index}``   - serves the bytes
      * ``images_count`` on the doc   - shown in the sidebar
      * ``replace_docx_image``        - writes the new bytes

    Entries look like::

        {
          "index": 0,                  # the stable public id
          "r_id": "rId7",              # document.xml -> part relationship
          "part": <ImagePart>,
          "mime": "image/png",
          "width_emu": 1905000,
          "height_emu": 1905000,
          "anchor_index": 4,           # body paragraphs before it (None in a table)
          "blips": [<a:blip>, ...],    # EVERY blip sharing this r_id
          "occurrences": 3,            # how many pictures use it
        }

    Two rules define the numbering, and the writer depends on both:

    1. **Deduplicated by relationship.** One logo referenced from five places is
       one part, so it is one entry with ``occurrences == 5``. Replacing it
       replaces all five - which is what a user means by "replace the logo".

    2. **Unreadable parts are skipped entirely and consume no index.** A
       relationship with no part, or one whose blob cannot be read, is invisible
       in the editor, so it must also be invisible to the writer - otherwise
       every later index would be off by one between what the user clicked and
       what gets written.

    Note that ``doc.inline_shapes`` is deliberately NOT used anywhere: it lists
    only *inline* pictures (floating ones vanish), it counts non-picture inline
    shapes such as charts and OLE objects (shifting every index), and it does not
    deduplicate shared parts. Using it for writes while reading from this walk is
    exactly how a replacement ends up on the wrong picture.
    """
    targets = []
    by_r_id = {}
    paragraph_count = 0

    for child in doc.element.body.iterchildren():
        is_paragraph = child.tag == qn("w:p")
        for r_id, width, height, blip in _iter_blips_in(child, doc):
            existing = by_r_id.get(r_id)
            if existing is not None:
                # A shared part: one image, another picture pointing at it.
                existing["blips"].append(blip)
                existing["occurrences"] += 1
                continue

            part = doc.part.related_parts.get(r_id)
            if part is None:
                continue
            try:
                if not part.blob:
                    continue
            except Exception:
                continue

            entry = {
                "index": len(targets),
                "r_id": r_id,
                "part": part,
                "mime": getattr(part, "content_type", None) or "image/png",
                "width_emu": width,
                "height_emu": height,
                "anchor_index": paragraph_count if is_paragraph else None,
                "blips": [blip],
                "occurrences": 1,
            }
            targets.append(entry)
            by_r_id[r_id] = entry

        if is_paragraph:
            paragraph_count += 1

    return targets


def docx_image_descriptors(doc) -> list:
    """JSON-safe view of :func:`collect_docx_image_targets`."""
    return [
        {
            "index": t["index"],
            "r_id": t["r_id"],
            "mime": t["mime"],
            "width": round(t["width_emu"] / _EMU_PER_PX) if t["width_emu"] else None,
            "height": round(t["height_emu"] / _EMU_PER_PX) if t["height_emu"] else None,
            "anchor_index": t["anchor_index"],
            "occurrences": t["occurrences"],
        }
        for t in collect_docx_image_targets(doc)
    ]


def iter_docx_body_items(doc_path: str):
    """Yield ``(kind, payload)`` for every body item in true document order.

    ``kind`` is ``"paragraph"``, ``"table"`` or ``"image"``. Paragraph payloads
    keep the same ``index`` that :func:`get_docx_content` assigns (their
    position in ``doc.paragraphs``) so the existing edit/save/rewrite flows -
    which key off that index - keep working unchanged.

    Image ``image_index`` values are looked up from
    :func:`collect_docx_image_targets` rather than counted here. This function
    already walks the body to interleave items, and counting a *second*, subtly
    different index space in that walk is precisely the bug that used to make
    the writer replace a different picture than the one the user clicked. One
    numbering, one definition.

    Note: lxml hands out a fresh Python proxy object each time an element is
    reached, so the body children cannot be matched to ``doc.paragraphs`` by
    object identity. ``doc.paragraphs``/``doc.tables`` are simply the direct
    ``w:p``/``w:tbl`` children of the body in order, so counting is both exact
    and free of that trap.
    """
    doc = docx.Document(doc_path)
    body = doc._body

    # The canonical index space, resolved up front.
    targets = collect_docx_image_targets(doc)
    by_r_id = {t["r_id"]: t for t in targets}
    emitted_indexes = set()

    def _images_for(child, anchor_index):
        for r_id, _w, _h, _blip in _iter_blips_in(child, doc):
            target = by_r_id.get(r_id)
            if target is None or target["index"] in emitted_indexes:
                continue
            emitted_indexes.add(target["index"])
            yield {
                "image_index": target["index"],
                "anchor_index": anchor_index,
                "mime": target["mime"],
                "width_px": round(target["width_emu"] / _EMU_PER_PX) if target["width_emu"] else None,
                "height_px": round(target["height_emu"] / _EMU_PER_PX) if target["height_emu"] else None,
                "occurrences": target["occurrences"],
            }

    paragraph_no = 0
    table_no = 0

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
                ["\n".join(_p_text(p) for p in cell.paragraphs) for cell in row.cells]
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
                # >1 means several pictures share this one stored file, so
                # replacing it will change all of them. The editor says so
                # rather than letting the user be surprised.
                "occurrences": payload.get("occurrences", 1),
                "anchor_index": payload.get("anchor_index"),
            })
        blocks.append({"kind": kind, **payload})

    return {"content": content, "blocks": blocks, "images": images}


def get_docx_image_parts(doc_path: str) -> list:
    """Every image in the document, in reading order, with its bytes.

    The ``index`` here is read straight off
    :func:`collect_docx_image_targets`, the same numbering the editor tiles use
    and the replacement writer looks up, so one index space is shared by reads
    and writes. Previously this function re-counted images with its own copy of
    the walk; the docstring already *claimed* the spaces matched, and a
    deduplication difference between the two copies silently broke that claim.
    """
    doc = docx.Document(doc_path)
    return [
        {
            "index": t["index"],
            "mime": t["mime"],
            "width": round(t["width_emu"] / _EMU_PER_PX) if t["width_emu"] else None,
            "height": round(t["height_emu"] / _EMU_PER_PX) if t["height_emu"] else None,
            "anchor_index": t["anchor_index"],
            "occurrences": t["occurrences"],
            "blob": t["part"].blob,
        }
        for t in collect_docx_image_targets(doc)
    ]


# ---------------------------------------------------------------------------
# Image replacement
# ---------------------------------------------------------------------------

# How a new image that does not match the old one's aspect ratio is handled.
SIZE_MODE_FIT = "fit"        # scale down to fit inside the original box (default)
SIZE_MODE_STRETCH = "stretch"  # keep the exact box, distorting if ratios differ
SIZE_MODE_ORIGINAL = "original"  # render at native/original image dimensions


def _drawing_extent(drawing):
    """Current ``(cx, cy)`` of a picture drawing, or ``(None, None)``.

    ``wp:extent`` is the usual source but not the only one: a ``w:pict``/VML
    picture, or a drawing whose layout element was written by another tool, can
    carry the size only in ``pic:spPr/a:xfrm/a:ext``. Both are read so the
    aspect-ratio fit below never divides by ``None``.
    """
    for extent in drawing.iter(qn("wp:extent")):
        try:
            return int(extent.get("cx")), int(extent.get("cy"))
        except (TypeError, ValueError):
            break
    for xfrm in drawing.iter(qn("a:xfrm")):
        for ext in xfrm.iter(qn("a:ext")):
            try:
                return int(ext.get("cx")), int(ext.get("cy"))
            except (TypeError, ValueError):
                break
    return None, None


def _fit_extents(drawing, target_cx: int, target_cy: int, drop_crop: bool = False) -> None:
    """Rewrite every size declaration inside a ``w:drawing`` / ``w:pict``.

    A picture's rendered size is stated three times and Word uses different ones
    in different contexts, so leaving any of them stale is what makes a replaced
    image come out stretched:

      * ``wp:extent``   - the inline/anchor box (layout)
      * ``a:ext``       - the shape transform inside ``pic:spPr/a:xfrm``
      * ``a:srcRect``   - a *crop* of the source image

    The crop matters most and is easy to miss: if the original picture was
    cropped, a replacement inherits that crop and shows up with pieces missing.

    Only a *replacement* clears the crop. A resize must keep it - the user asked
    for the same picture at a different size, and silently revealing cropped-away
    regions is a different edit.
    """
    if target_cx is None or target_cy is None:
        return

    for extent in drawing.iter(qn("wp:extent")):
        extent.set("cx", str(int(target_cx)))
        extent.set("cy", str(int(target_cy)))
        break

    for xfrm in drawing.iter(qn("a:xfrm")):
        for ext in xfrm.iter(qn("a:ext")):
            ext.set("cx", str(int(target_cx)))
            ext.set("cy", str(int(target_cy)))

    if not drop_crop:
        return

    # Drop any inherited crop so the new image is shown whole.
    for src_rect in drawing.iter(qn("a:srcRect")):
        parent = src_rect.getparent()
        if parent is not None:
            parent.remove(src_rect)


def _fit_to_aspect(cx: int, cy: int, new_image):
    """Shrink a ``(cx, cy)`` box to a new image's aspect ratio, never enlarging.

    Shrinking the *box* rather than stretching the image is what keeps a
    replacement undistorted. Position is untouched: an inline picture is placed
    by paragraph alignment and an anchored one by its ``positionH``/``positionV``
    offsets, neither of which changes here.

    Returns ``(new_cx, new_cy, was_scaled)``.
    """
    try:
        new_ratio = float(new_image.px_width) / float(new_image.px_height)
        old_ratio = float(cx) / float(cy)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return cx, cy, False
    if new_ratio <= 0 or abs(new_ratio - old_ratio) <= 0.01:
        return cx, cy, False
    if new_ratio > old_ratio:
        new_cy = max(1, min(int(round(cx / new_ratio)), cy))
        new_cx = cx
    else:
        new_cx = max(1, min(int(round(cy * new_ratio)), cx))
        new_cy = cy
    return new_cx, new_cy, True


def _ensure_page_break_before_if_large(drawing, height_emu: int, force: bool = False):
    """Place image paragraph on a new page if it exceeds available space or force is True."""
    # Standard printable page height is ~9 inches (8.2M EMUs).
    # If image exceeds ~5 inches (4.5M EMUs), or force is requested, break to a new page.
    if force or (height_emu and height_emu > 4500000):
        node = drawing
        while node is not None and node.tag != qn("w:p"):
            node = node.getparent()
        if node is not None:
            pPr = node.get_or_add_pPr()
            if pPr.find(qn("w:pageBreakBefore")) is None:
                pPr.append(OxmlElement("w:pageBreakBefore"))


def _apply_docx_image_replacements(doc, replacements: list, size_mode: str = SIZE_MODE_FIT) -> list:
    """Swap the bytes behind specific images of an open Document.

    ``replacements`` is a list of ``{"target_index": int, "image_bytes": bytes}``
    resolved against :func:`collect_docx_image_targets`, i.e. the same integers
    the editor renders.

    Why this repoints relationships instead of overwriting a part's blob
    ---------------------------------------------------------------------
    The old implementation did ``image_part._blob = new_bytes``. That is wrong
    twice over:

    * **It corrupted the file whenever the formats differed.** The part keeps its
      declared ``content_type`` and its ``word/media/imageN.jpeg`` filename while
      now holding PNG bytes. Word treats that as a corrupt document and offers
      to "repair" it, losing the edit. ``get_or_add_image`` instead creates a
      part with the correct extension and content type, so format never matters.
    * **It could not target the picture the user clicked**, because it looked the
      target up in ``doc.inline_shapes`` - a different numbering from the reader
      (see :func:`collect_docx_image_targets`).

    Repointing also means every picture sharing the old part is repointed, which
    is the correct behaviour for "replace the logo": the user sees one tile, so
    replacing it changes all of its occurrences. ``occurrences`` in the returned
    report says so out loud instead of doing it silently.

    Returns one report dict per replacement; never raises for a single bad
    target, so a batch where image 4 is out of range still writes images 0-3.
    """
    if not replacements:
        return []

    targets = collect_docx_image_targets(doc)
    by_index = {t["index"]: t for t in targets}
    reports = []

    for rep in replacements:
        idx = rep.get("target_index")
        img_bytes = rep.get("image_bytes")
        report = {"index": idx, "replaced": False, "occurrences": 0}

        if idx is None or not img_bytes:
            report["error"] = "No image data was provided."
            reports.append(report)
            continue

        target = by_index.get(idx)
        if target is None:
            report["error"] = (
                f"Image {idx} does not exist in this document "
                f"(it has {len(targets)} image{'s' if len(targets) != 1 else ''})."
            )
            reports.append(report)
            continue

        try:
            new_r_id, new_image = doc.part.get_or_add_image(io.BytesIO(img_bytes))
        except Exception as exc:
            report["error"] = f"That file is not a usable image: {exc}"
            reports.append(report)
            continue

        scaled = False
        no_extent = False

        for blip in target["blips"]:
            blip.set(qn("r:embed"), new_r_id)

            drawing = blip.getparent()
            while drawing is not None and drawing.tag not in (qn("w:drawing"), qn("w:pict")):
                drawing = drawing.getparent()
            if drawing is None:
                continue

            # The extent is re-resolved per drawing rather than trusting the
            # value cached during the read: a VML picture, or a drawing written
            # by another tool, may declare its size only in a:xfrm/a:ext - and a
            # missing extent must not be read as a zero-size box.
            cx, cy = _drawing_extent(drawing)
            if cx is None or cy is None:
                # Nothing declares a size, so there is no aspect ratio to
                # preserve and nothing to rewrite. The swap itself still happened.
                no_extent = True
                continue

            if size_mode in (SIZE_MODE_ORIGINAL, "original"):
                try:
                    orig_cx = int(new_image.width)
                    orig_cy = int(new_image.height)
                    max_page_cx = int(6.0 * 914400)
                    if orig_cx > max_page_cx:
                        orig_cy = max(1, int(orig_cy * (max_page_cx / orig_cx)))
                        orig_cx = max_page_cx
                    new_cx, new_cy, changed = orig_cx, orig_cy, True
                except Exception:
                    new_cx, new_cy, changed = _fit_to_aspect(cx, cy, new_image)
            elif size_mode == SIZE_MODE_FIT:
                new_cx, new_cy, changed = _fit_to_aspect(cx, cy, new_image)
            else:
                new_cx, new_cy, changed = (cx, cy, False)
            _fit_extents(drawing, new_cx, new_cy, drop_crop=True)
            _ensure_page_break_before_if_large(drawing, new_cy)
            scaled = scaled or changed

        report["replaced"] = True
        report["occurrences"] = target["occurrences"]
        report["previous_mime"] = target["mime"]
        report["new_mime"] = new_image.content_type
        report["scaled"] = scaled
        if no_extent:
            report["no_extent"] = True
        reports.append(report)
        logger.info(
            "Replaced DOCX image %d (%s -> %s, %d occurrence(s), scaled=%s)",
            idx, target["mime"], new_image.content_type, target["occurrences"], scaled,
        )

    return reports


def replace_docx_images(
    doc_path: str,
    output_path: str,
    replacements: list,
    size_mode: str = SIZE_MODE_FIT,
) -> dict:
    """Replace images in a DOCX and write the result to ``output_path``.

    Returns ``{"ok": bool, "replaced": n, "reports": [...], "error": str|None}``.
    Never raises: callers turn ``error`` into an HTTP message.
    """
    try:
        doc = docx.Document(doc_path)
    except Exception as exc:
        return {"ok": False, "replaced": 0, "reports": [], "error": f"Could not open the document: {exc}"}

    try:
        reports = _apply_docx_image_replacements(doc, replacements, size_mode)
    except Exception as exc:
        logger.error("Error replacing DOCX images: %s", exc)
        return {"ok": False, "replaced": 0, "reports": [], "error": str(exc)}

    replaced = sum(1 for r in reports if r.get("replaced"))
    if not replaced:
        first_error = next((r.get("error") for r in reports if r.get("error")), None)
        return {
            "ok": False,
            "replaced": 0,
            "reports": reports,
            "error": first_error or "No images were replaced.",
        }

    try:
        _save_docx_clean(doc, output_path)
    except Exception as exc:
        logger.error("Error saving DOCX after image replacement: %s", exc)
        return {"ok": False, "replaced": replaced, "reports": reports, "error": str(exc)}

    return {"ok": True, "replaced": replaced, "reports": reports, "error": None}


def _drawing_for_blip(blip):
    """The ``w:drawing`` / ``w:pict`` element wrapping an ``a:blip``."""
    node = blip.getparent()
    while node is not None and node.tag not in (qn("w:drawing"), qn("w:pict")):
        node = node.getparent()
    return node


def _apply_docx_image_resizes(doc, resizes: list) -> list:
    """Apply resize requests to an open DOCX, on the canonical index space.

    Unlike replacement, a resize is a *layout* change, so each picture is resized
    independently even when several of them share one image part: the same logo
    used at 2in in the header and 0.5in in the footer must keep both sizes.

    Returns one report per request rather than raising, so a bad entry in a batch
    does not abandon the good ones next to it.
    """
    targets = {t["index"]: t for t in collect_docx_image_targets(doc)}
    reports = []

    for req in resizes:
        idx = req.get("target_index")
        report = {"index": idx, "resized": False, "placements": 0}

        if idx is None:
            report["error"] = "No image was identified to resize."
            reports.append(report)
            continue

        target = targets.get(idx)
        if target is None:
            report["error"] = (
                f"Image {idx} does not exist in this document "
                f"(it has {len(targets)} image{'s' if len(targets) != 1 else ''})."
            )
            reports.append(report)
            continue

        try:
            changed = 0
            last = None
            for blip in target["blips"]:
                drawing = _drawing_for_blip(blip)
                if drawing is None:
                    continue
                old_cx, old_cy = _drawing_extent(drawing)
                new_cx, new_cy = resolve_target_box(
                    old_cx, old_cy,
                    width=req.get("width"),
                    height=req.get("height"),
                    unit=req.get("unit", "px"),
                    keep_aspect=req.get("keep_aspect", True),
                )
                if (new_cx, new_cy) != (old_cx, old_cy):
                    _fit_extents(drawing, new_cx, new_cy)
                    _ensure_page_break_before_if_large(drawing, new_cy, force=bool(req.get("new_page")))
                    changed += 1
                last = (old_cx, old_cy, new_cx, new_cy)
        except ResizeError as exc:
            report["error"] = str(exc)
            reports.append(report)
            continue

        if not target["blips"]:
            report["error"] = "That image could not be located in the document body."
            reports.append(report)
            continue

        report["resized"] = True
        report["placements"] = changed
        if last:
            report["change"] = describe_change(*last)
        reports.append(report)

    return reports


def resize_docx_images(doc_path: str, output_path: str, resizes: list) -> dict:
    """Resize images in a DOCX, writing the result to ``output_path``.

    ``resizes`` is ``[{"target_index": int, "width": float|None,
    "height": float|None, "unit": "px", "keep_aspect": bool}]``.

    Returns ``{"ok": bool, "resized": n, "reports": [...], "error": str|None}``
    with the same never-raises contract as :func:`replace_docx_images`.
    """
    if not resizes:
        return {"ok": False, "resized": 0, "reports": [], "error": "No image was identified to resize."}

    try:
        doc = docx.Document(doc_path)
    except Exception as exc:
        return {"ok": False, "resized": 0, "reports": [], "error": f"Could not open the document: {exc}"}

    try:
        reports = _apply_docx_image_resizes(doc, resizes)
    except Exception as exc:
        logger.error("Error resizing DOCX images: %s", exc)
        return {"ok": False, "resized": 0, "reports": [], "error": str(exc)}

    resized = sum(1 for r in reports if r.get("resized"))
    if not resized:
        first_error = next((r.get("error") for r in reports if r.get("error")), None)
        return {
            "ok": False,
            "resized": 0,
            "reports": reports,
            "error": first_error or "No images were resized.",
        }

    try:
        _save_docx_clean(doc, output_path)
    except Exception as exc:
        logger.error("Error saving DOCX after image resize: %s", exc)
        return {"ok": False, "resized": resized, "reports": reports, "error": str(exc)}

    return {"ok": True, "resized": resized, "reports": reports, "error": None}


def _docx_core_title(doc) -> str:
    """The document's own title property, used as the ``{TITLE}`` cached value.

    Word recomputes a ``TITLE`` field on open, so this only affects viewers that
    show the cached result instead of evaluating the field.
    """
    try:
        return (doc.core_properties.title or "").strip()
    except Exception:
        return ""


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
    alignment: str = None,
    header_text_odd: str = None,
    header_text_even: str = None,
    header_text_first: str = None,
    footer_text_odd: str = None,
    footer_text_even: str = None,
    footer_text_first: str = None,
    header_alignment: str = None,
    footer_alignment: str = None,
    doc_title: str = None,
    line_spacing: float = None,
) -> bool:
    try:
        doc = docx.Document(doc_path)

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

        if line_spacing:
            for paragraph in doc.paragraphs:
                try:
                    paragraph.paragraph_format.line_spacing = float(line_spacing)
                except Exception:
                    pass

        # 2. Update Header/Footer
        hf.apply_docx_headers_footers(
            doc,
            hf.restrict_docx_spec(
                doc,
                hf.spec_from_legacy(
                    header_text=header_text,
                    header_odd=header_text_odd,
                    header_even=header_text_even,
                    header_first=header_text_first,
                    footer_text=footer_text,
                    footer_odd=footer_text_odd,
                    footer_even=footer_text_even,
                    footer_first=footer_text_first,
                ),
                target_header=target_header_text,
                target_footer=target_footer_text,
            ),
            font_name=font_name,
            font_size=font_size,
            header_align=header_alignment or alignment or "center",
            footer_align=footer_alignment or alignment or "center",
            title=doc_title if doc_title is not None else _docx_core_title(doc),
        )

        # 3. Image replacement
        #    Delegates to the shared writer so /style and /replace-image cannot
        #    drift apart in how they number or match pictures.
        if image_replacements:
            _apply_docx_image_replacements(doc, image_replacements)

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
                "text": _p_text(p),
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
        return hf.read_docx_headers_footers(doc)
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

    before = "\n".join(_p_text(p) for p in cell.paragraphs)
    if before == new_text:
        return False

    lines = new_text.split("\n")
    paragraphs = list(cell.paragraphs)

    for offset, line in enumerate(lines):
        if offset < len(paragraphs):
            target = paragraphs[offset]
            if _p_text(target) != line:
                replace_paragraph_text_preserving_format(target, line, old_text=_p_text(target))
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


def _insert_paragraph_after_formatted(p, text: str):
    """Insert a new paragraph right after ``p`` carrying the same paragraph
    style and first-run formatting but with ``text`` as its content.

    Used to turn ``\\n``-separated edit text into real paragraphs. Writing a
    literal newline into a single run makes Word/LibreOffice render it as stray
    whitespace, so the text that used to live in its own paragraph (e.g. a
    "Conclusion" heading) ends up floating and mis-positioned.
    """
    new_el = copy.deepcopy(p._p)
    p._p.addnext(new_el)
    new_p = Paragraph(new_el, p._parent)
    runs = new_p.runs
    keep = runs[0] if runs else None
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    if keep is not None:
        _el_set_text(keep._r, text)
    else:
        new_p.add_run(text)
    return new_p


def _apply_paragraph_edit(p, new_text: str) -> None:
    """Apply one paragraph edit, expanding ``\\n`` breaks into real paragraphs.

    The rewriter brain and the multi-line paragraph textarea routinely produce
    ``\\n``-separated text. Keeping that internal to one paragraph corrupts the
    layout in the original document, so each line becomes its own paragraph,
    sharing the target's paragraph style and run formatting.
    """
    lines = new_text.split("\n")
    first = lines[0]
    if _p_text(p) != first:
        replace_paragraph_text_preserving_format(p, first, old_text=_p_text(p))
    anchor = p
    for line in lines[1:]:
        anchor = _insert_paragraph_after_formatted(anchor, line)


def update_docx_content(doc_path: str, output_path: str, edits: list) -> bool:
    """Apply paragraph and table-cell edits to a DOCX file, including run-level
    inline formatting (bold, italic, underline, color, font size), paragraph
    alignment, heading levels, and list styles.

    Each edit is ``{"index": int, "text": str}`` for a body paragraph, or
    ``{"table_index": int, "row": int, "col": int, "text": str}`` for a table
    cell. Table edits used to be dropped on the floor because this function
    only walked ``doc.paragraphs``, which is why table content could be read in
    the editor but never written back. Paragraph edits that contain ``\\n`` are
    expanded into separate paragraphs so the document keeps its structure.
    """
    try:
        doc = docx.Document(doc_path)

        paragraph_edits = {}
        cell_edits = {}
        for edit in edits or []:
            if not isinstance(edit, dict):
                continue
            text = re.sub(r"\r\n?", "\n", edit.get("text") or "")
            if edit.get("table_index") is not None:
                cell_edits[edit["table_index"]] = cell_edits.get(edit["table_index"], {})
                cell_edits[edit["table_index"]][(edit.get("row"), edit.get("col"))] = edit
            elif edit.get("index") is not None:
                paragraph_edits[edit["index"]] = {**edit, "text": text}

        for idx, p in enumerate(doc.paragraphs):
            if idx in paragraph_edits:
                p_edit = paragraph_edits[idx]
                if isinstance(p_edit, str):
                    p_edit = {"text": p_edit}
                runs = p_edit.get("runs")
                alignment = p_edit.get("alignment")
                style = p_edit.get("style")
                heading_level = p_edit.get("heading_level")
                new_text = p_edit.get("text")

                # Handle runs reconstruction if runs are provided
                if runs and isinstance(runs, list) and len(runs) > 0:
                    for r in list(p.runs):
                        p._p.remove(r._r)
                    for r_item in runs:
                        r_text = r_item.get("text", "")
                        if not r_text:
                            continue
                        r = p.add_run(r_text)
                        if r_item.get("bold") is not None:
                            r.bold = bool(r_item["bold"])
                        if r_item.get("italic") is not None:
                            r.italic = bool(r_item["italic"])
                        if r_item.get("underline") is not None:
                            r.underline = bool(r_item["underline"])
                        if r_item.get("strike") is not None:
                            r.font.strike = bool(r_item["strike"])
                        if r_item.get("color"):
                            c = str(r_item["color"]).lstrip("#")
                            if len(c) == 6:
                                try:
                                    r.font.color.rgb = RGBColor.from_string(c)
                                except Exception:
                                    pass
                        if r_item.get("font_size"):
                            try:
                                r.font.size = Pt(float(r_item["font_size"]))
                            except Exception:
                                pass
                        if r_item.get("font_name"):
                            r.font.name = str(r_item["font_name"])
                        if r_item.get("highlight"):
                            _el_highlight_yellow(r._r)
                elif new_text is not None and _p_text(p) != new_text:
                    _apply_paragraph_edit(p, new_text)

                # Alignment
                if alignment:
                    align_lower = str(alignment).lower()
                    if align_lower in ("left", "wd_align_paragraph.left"):
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    elif align_lower in ("center", "wd_align_paragraph.center"):
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif align_lower in ("right", "wd_align_paragraph.right"):
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    elif align_lower in ("justify", "wd_align_paragraph.justify"):
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                # Heading / Style
                if heading_level:
                    try:
                        p.style = f"Heading {heading_level}"
                    except Exception:
                        pass
                elif style:
                    try:
                        p.style = style
                    except Exception:
                        pass

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
                for (row_idx, col_idx), cell_data in cells.items():
                    c_text = cell_data.get("text") if isinstance(cell_data, dict) else str(cell_data or "")
                    _set_table_cell_text(table, row_idx, col_idx, c_text)

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
        escaped_tokens = [re.escape(tok) for tok in re.split(r"\s+", find_text.strip()) if tok]
        escaped_pattern = r"\s+".join(escaped_tokens) if escaped_tokens else re.escape(find_text)
        start_b = r"\b" if (find_text and (find_text[0].isalnum() or find_text[0] == "_")) else r"(?<!\w)"
        end_b = r"\w*" if (find_text and (find_text[-1].isalnum() or find_text[-1] == "_")) else r"(?!\w)"
        prefix_pattern = re.compile(start_b + escaped_pattern + end_b, flags)

        groups = {}
        for loc, p in _collect_docx_paragraphs(doc):
            text = _p_text(p)
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
            original = _p_text(p)
            paragraph_count = 0
            for variant in variants:
                escaped_tokens = [re.escape(tok) for tok in re.split(r"\s+", variant.strip()) if tok]
                escaped_variant = r"\s+".join(escaped_tokens) if escaped_tokens else re.escape(variant)
                start_b = r"\b" if (variant and (variant[0].isalnum() or variant[0] == "_")) else r"(?<!\w)"
                end_b = r"\b" if (variant and (variant[-1].isalnum() or variant[-1] == "_")) else r"(?!\w)"
                pattern = re.compile(start_b + escaped_variant + end_b, flags)
                matches = list(pattern.finditer(_p_text(p)))
                for m in reversed(matches):
                    _replace_span(p, m.start(), m.end(), replace_text)
                    paragraph_count += 1
            count += paragraph_count
            if paragraph_count > 0:
                changes.append({
                    "paragraph": loc["label"],
                    "index": loc.get("index"),
                    "old_text": original,
                    "new_text": _p_text(p),
                })

        _save_docx_clean(doc, output_path)
        return {"matches_replaced": count, "changes": changes}
    except Exception as e:
        logger.error("Error in selective find-replace DOCX: %s", e)
        return {"matches_replaced": 0, "changes": []}


# ---------------------------------------------------------------------------
# Universal Command Bar: Structural Table & Heading Mutations
# ---------------------------------------------------------------------------

def delete_docx_table_column(
    doc_path: str,
    output_path: str,
    table_index: int = None,
    col_index: int = 1,
) -> dict:
    """Delete a column from one or all tables in a DOCX document.

    col_index is 0-indexed (e.g. 0 for 1st column, 1 for 2nd column, -1 for last column).
    """
    try:
        doc = docx.Document(doc_path)
        tables = doc.tables
        if not tables:
            return {"success": False, "modified_tables": 0, "message": "No tables found in this document."}

        target_tables = [tables[table_index]] if (table_index is not None and 0 <= table_index < len(tables)) else tables
        modified_count = 0

        for tbl in target_tables:
            if not tbl.rows:
                continue
            num_cols = len(tbl.rows[0].cells)
            target_col = col_index if col_index >= 0 else num_cols + col_index
            if 0 <= target_col < num_cols:
                for row in tbl.rows:
                    if target_col < len(row.cells):
                        tc = row.cells[target_col]._tc
                        parent = tc.getparent()
                        if parent is not None:
                            parent.remove(tc)
                # Cleanup gridCol in tblGrid
                tblGrid = tbl._tbl.find(qn("w:tblGrid"))
                if tblGrid is not None:
                    gridCols = tblGrid.findall(qn("w:gridCol"))
                    if 0 <= target_col < len(gridCols):
                        tblGrid.remove(gridCols[target_col])
                modified_count += 1

        if modified_count > 0:
            _save_docx_clean(doc, output_path)
            col_label = f"column {col_index + 1}" if col_index >= 0 else "the last column"
            return {
                "success": True,
                "modified_tables": modified_count,
                "message": f"Done — deleted {col_label} from {modified_count} table(s).",
            }
        return {"success": False, "modified_tables": 0, "message": f"Column index {col_index + 1} was out of range for the document tables."}
    except Exception as e:
        logger.error("Error deleting table column in DOCX: %s", e)
        return {"success": False, "modified_tables": 0, "message": f"Failed to delete table column: {str(e)}"}


def delete_docx_table_row(
    doc_path: str,
    output_path: str,
    table_index: int = None,
    row_index: int = 0,
) -> dict:
    """Delete a row from one or all tables in a DOCX document.

    row_index is 0-indexed (e.g. 0 for 1st row, -1 for last row).
    """
    try:
        doc = docx.Document(doc_path)
        tables = doc.tables
        if not tables:
            return {"success": False, "modified_tables": 0, "message": "No tables found in this document."}

        target_tables = [tables[table_index]] if (table_index is not None and 0 <= table_index < len(tables)) else tables
        modified_count = 0

        for tbl in target_tables:
            num_rows = len(tbl.rows)
            target_row = row_index if row_index >= 0 else num_rows + row_index
            if 0 <= target_row < num_rows:
                tr = tbl.rows[target_row]._tr
                parent = tr.getparent()
                if parent is not None:
                    parent.remove(tr)
                modified_count += 1

        if modified_count > 0:
            _save_docx_clean(doc, output_path)
            row_label = f"row {row_index + 1}" if row_index >= 0 else "the last row"
            return {
                "success": True,
                "modified_tables": modified_count,
                "message": f"Done — deleted {row_label} from {modified_count} table(s).",
            }
        return {"success": False, "modified_tables": 0, "message": f"Row index {row_index + 1} was out of range for the document tables."}
    except Exception as e:
        logger.error("Error deleting table row in DOCX: %s", e)
        return {"success": False, "modified_tables": 0, "message": f"Failed to delete table row: {str(e)}"}


def delete_docx_table(
    doc_path: str,
    output_path: str,
    table_index: int = None,
) -> dict:
    """Delete a specific table or all tables from a DOCX document."""
    try:
        doc = docx.Document(doc_path)
        tables = list(doc.tables)
        if not tables:
            return {"success": False, "deleted_tables": 0, "message": "No tables found in this document."}

        target_tables = [tables[table_index]] if (table_index is not None and 0 <= table_index < len(tables)) else tables
        deleted_count = 0

        for tbl in target_tables:
            tbl_elm = tbl._tbl
            parent = tbl_elm.getparent()
            if parent is not None:
                parent.remove(tbl_elm)
                deleted_count += 1

        if deleted_count > 0:
            _save_docx_clean(doc, output_path)
            return {
                "success": True,
                "deleted_tables": deleted_count,
                "message": f"Done — deleted {deleted_count} table(s).",
            }
        return {"success": False, "deleted_tables": 0, "message": "Target table could not be found."}
    except Exception as e:
        logger.error("Error deleting table in DOCX: %s", e)
        return {"success": False, "deleted_tables": 0, "message": f"Failed to delete table: {str(e)}"}


def style_docx_headings(
    doc_path: str,
    output_path: str,
    font_size: float = None,
    bold: bool = None,
    italic: bool = None,
    color_rgb: tuple = None,
    font_name: str = None,
    level: int = None,
) -> dict:
    """Format and style headings in a DOCX document (color, size, weight, font family)."""
    try:
        doc = docx.Document(doc_path)
        modified_count = 0

        for p in doc.paragraphs:
            lvl = _heading_level(p, _paragraph_style_name(p))
            sname = (p.style.name or "").lower()
            text_strip = p.text.strip()
            # If paragraph is Heading 1-6 or starts with heading style or Title / Subtitle or manual heading
            is_heading = (
                (lvl > 0)
                or sname.startswith("heading")
                or sname in ("title", "subtitle")
                or text_strip.startswith("#")
                or (0 < len(text_strip) < 80 and p.runs and any(r.font.bold for r in p.runs if r.text.strip()))
            )
            if is_heading:
                if level is not None and lvl != level and lvl != 0:
                    continue
                # If paragraph has no runs but has text, add a run
                if not p.runs and p.text:
                    p.add_run(p.text)
                for run in p.runs:
                    if font_size is not None:
                        run.font.size = Pt(font_size)
                    if bold is not None:
                        run.font.bold = bold
                    if italic is not None:
                        run.font.italic = italic
                    if color_rgb is not None:
                        run.font.color.rgb = RGBColor(*color_rgb)
                    if font_name:
                        run.font.name = font_name
                modified_count += 1

        if modified_count > 0:
            _save_docx_clean(doc, output_path)
            details = []
            if color_rgb: details.append(f"color {color_rgb}")
            if font_size: details.append(f"{font_size}pt")
            if bold: details.append("bold")
            if font_name: details.append(font_name)
            detail_str = f" ({', '.join(details)})" if details else ""
            return {
                "success": True,
                "headings_modified": modified_count,
                "message": f"Done — styled {modified_count} heading(s){detail_str}.",
            }
        return {"success": False, "headings_modified": 0, "message": "No headings were detected in this document."}
    except Exception as e:
        logger.error("Error styling headings in DOCX: %s", e)
        return {"success": False, "headings_modified": 0, "message": f"Failed to style headings: {str(e)}"}


def delete_docx_images(
    doc_path: str,
    output_path: str,
    image_indexes: list = None,
) -> dict:
    """Delete all images or specific indexed images in a DOCX document."""
    try:
        doc = docx.Document(doc_path)
        targets = collect_docx_image_targets(doc)
        if not targets:
            return {"success": False, "deleted_images": 0, "message": "No images found in this document."}

        target_set = set(image_indexes) if image_indexes is not None else None
        deleted_count = 0

        for target in targets:
            idx = target.get("index")
            if target_set is not None and idx not in target_set:
                continue
            blip = target.get("blip")
            drawing = _drawing_for_blip(blip)
            if drawing is not None:
                parent = drawing.getparent()
                if parent is not None:
                    parent.remove(drawing)
                    deleted_count += 1

        if deleted_count > 0:
            _save_docx_clean(doc, output_path)
            return {
                "success": True,
                "deleted_images": deleted_count,
                "message": f"Done — deleted {deleted_count} image(s).",
            }
        return {"success": False, "deleted_images": 0, "message": "Selected image could not be removed."}
    except Exception as e:
        logger.error("Error deleting images in DOCX: %s", e)
        return {"success": False, "deleted_images": 0, "message": f"Failed to delete images: {str(e)}"}


# ---------------------------------------------------------------------------
# Visual Table Operations (MOD-02)
# ---------------------------------------------------------------------------

def insert_docx_table(
    doc_path: str,
    output_path: str,
    rows: int = 3,
    cols: int = 3,
    after_paragraph_index: int = None,
) -> dict:
    """Insert a new table into a DOCX document."""
    try:
        doc = docx.Document(doc_path)
        table = doc.add_table(rows=max(1, rows), cols=max(1, cols))
        table.style = 'Table Grid'

        # Set placeholder header labels and cell text
        for c_idx, cell in enumerate(table.rows[0].cells):
            cell.text = f"Header {c_idx + 1}"
        for row in table.rows[1:]:
            for cell in row.cells:
                cell.text = "—"

        # Position after target paragraph if specified
        if after_paragraph_index is not None and 0 <= after_paragraph_index < len(doc.paragraphs):
            target_p = doc.paragraphs[after_paragraph_index]
            target_p._p.addnext(table._tbl)

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "rows": rows,
            "cols": cols,
            "table_index": len(doc.tables) - 1,
            "message": f"Done — inserted a {rows}x{cols} table.",
        }
    except Exception as e:
        logger.error("Error inserting table in DOCX: %s", e)
        return {"success": False, "message": f"Failed to insert table: {str(e)}"}


def add_docx_table_row(
    doc_path: str,
    output_path: str,
    table_index: int = 0,
    position: str = "below",
    reference_index: int = None,
) -> dict:
    """Add a row above or below a reference row in a DOCX table."""
    try:
        doc = docx.Document(doc_path)
        tables = doc.tables
        if not tables or table_index < 0 or table_index >= len(tables):
            return {"success": False, "message": f"Table {table_index + 1} not found."}

        tbl = tables[table_index]
        if not tbl.rows:
            return {"success": False, "message": "Table has no rows."}

        num_cols = len(tbl.rows[0].cells)
        new_row = tbl.add_row()
        for cell in new_row.cells:
            cell.text = "—"

        if reference_index is not None and 0 <= reference_index < len(tbl.rows) - 1:
            ref_tr = tbl.rows[reference_index]._tr
            new_tr = new_row._tr
            if position == "above":
                ref_tr.addprevious(new_tr)
            elif position == "below":
                ref_tr.addnext(new_tr)

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "table_index": table_index,
            "total_rows": len(tbl.rows),
            "message": f"Done — added a new row to Table {table_index + 1}.",
        }
    except Exception as e:
        logger.error("Error adding table row in DOCX: %s", e)
        return {"success": False, "message": f"Failed to add table row: {str(e)}"}


def add_docx_table_column(
    doc_path: str,
    output_path: str,
    table_index: int = 0,
    position: str = "right",
    reference_index: int = None,
    header_title: str = "New Column",
) -> dict:
    """Add a column to the left or right of a reference column in a DOCX table."""
    try:
        doc = docx.Document(doc_path)
        tables = doc.tables
        if not tables or table_index < 0 or table_index >= len(tables):
            return {"success": False, "message": f"Table {table_index + 1} not found."}

        tbl = tables[table_index]
        if not tbl.rows:
            return {"success": False, "message": "Table has no rows."}

        for r_idx, row in enumerate(tbl.rows):
            cell_text = header_title if r_idx == 0 else "—"
            tc = parse_xml(f'<w:tc {nsdecls("w")}><w:tcPr/><w:p><w:pPr/><w:r><w:t>{cell_text}</w:t></w:r></w:p></w:tc>')
            if reference_index is not None and 0 <= reference_index < len(row.cells):
                ref_tc = row.cells[reference_index]._tc
                if position == "left":
                    ref_tc.addprevious(tc)
                else:
                    ref_tc.addnext(tc)
            else:
                row._tr.append(tc)

        # Update tblGrid
        tblGrid = tbl._tbl.find(qn("w:tblGrid"))
        if tblGrid is not None:
            new_grid = parse_xml(f'<w:gridCol {nsdecls("w")} w:w="2160"/>')
            tblGrid.append(new_grid)

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "table_index": table_index,
            "message": f"Done — added column '{header_title}' to Table {table_index + 1}.",
        }
    except Exception as e:
        logger.error("Error adding table column in DOCX: %s", e)
        return {"success": False, "message": f"Failed to add table column: {str(e)}"}


# ---------------------------------------------------------------------------
# In-Flow Image Operations (MOD-06)
# ---------------------------------------------------------------------------

def insert_docx_image(
    doc_path: str,
    output_path: str,
    image_bytes: bytes,
    after_paragraph_index: int = None,
    width_inches: float = 4.0,
) -> dict:
    """Insert a new image directly into the document flow."""
    try:
        doc = docx.Document(doc_path)
        new_p = doc.add_paragraph()
        run = new_p.add_run()
        run.add_picture(io.BytesIO(image_bytes), width=Inches(max(0.5, float(width_inches))))

        if after_paragraph_index is not None and 0 <= after_paragraph_index < len(doc.paragraphs):
            target_p = doc.paragraphs[after_paragraph_index]
            target_p._p.addnext(new_p._p)

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "message": "Done — inserted image into the document.",
        }
    except Exception as e:
        logger.error("Error inserting image into DOCX: %s", e)
        return {"success": False, "message": f"Failed to insert image: {str(e)}"}


def move_docx_image(
    doc_path: str,
    output_path: str,
    image_index: int,
    direction: str = "up",
    target_paragraph_index: int = None,
) -> dict:
    """Move an image within the document relative to surrounding paragraphs."""
    try:
        doc = docx.Document(doc_path)
        targets = collect_docx_image_targets(doc)
        target = next((t for t in targets if t.get("index") == image_index), None)
        if not target or not target.get("blips"):
            return {"success": False, "message": f"Image {image_index + 1} not found."}

        blip = target["blips"][0]
        drawing = _drawing_for_blip(blip)
        if drawing is None:
            return {"success": False, "message": "Image container could not be located."}

        parent_p = drawing.getparent()
        while parent_p is not None and parent_p.tag != qn("w:p"):
            parent_p = parent_p.getparent()

        if parent_p is None:
            return {"success": False, "message": "Image paragraph could not be located."}

        if target_paragraph_index is not None and 0 <= target_paragraph_index < len(doc.paragraphs):
            dest_p = doc.paragraphs[target_paragraph_index]._p
            dest_p.addnext(parent_p)
        else:
            prev_sibling = parent_p.getprevious()
            next_sibling = parent_p.getnext()
            if direction == "up" and prev_sibling is not None:
                prev_sibling.addprevious(parent_p)
            elif direction == "down" and next_sibling is not None:
                next_sibling.addnext(parent_p)
            else:
                return {"success": False, "message": f"Cannot move image further {direction}."}

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "message": f"Done — moved image {image_index + 1} {direction}.",
        }
    except Exception as e:
        logger.error("Error moving image in DOCX: %s", e)
        return {"success": False, "message": f"Failed to move image: {str(e)}"}


# ---------------------------------------------------------------------------
# Page Setup & Layout Operations (MOD-05)
# ---------------------------------------------------------------------------

def update_docx_page_setup(
    doc_path: str,
    output_path: str,
    orientation: str = None,
    margin_inches: float = None,
    page_size: str = None,
) -> dict:
    """Apply page orientation, margin sizing, and paper dimensions."""
    try:
        doc = docx.Document(doc_path)
        for section in doc.sections:
            if orientation:
                ori_lower = orientation.lower()
                if ori_lower == "landscape":
                    section.orientation = WD_ORIENT.LANDSCAPE
                    w, h = section.page_width, section.page_height
                    if w < h:
                        section.page_width, section.page_height = h, w
                elif ori_lower == "portrait":
                    section.orientation = WD_ORIENT.PORTRAIT
                    w, h = section.page_width, section.page_height
                    if w > h:
                        section.page_width, section.page_height = h, w

            if page_size:
                ps_lower = page_size.lower()
                is_landscape = (section.orientation == WD_ORIENT.LANDSCAPE)
                if "a4" in ps_lower:
                    w_in, h_in = (11.69, 8.27) if is_landscape else (8.27, 11.69)
                    section.page_width = Inches(w_in)
                    section.page_height = Inches(h_in)
                elif "letter" in ps_lower:
                    w_in, h_in = (11.0, 8.5) if is_landscape else (8.5, 11.0)
                    section.page_width = Inches(w_in)
                    section.page_height = Inches(h_in)

            if margin_inches is not None:
                m = Inches(float(margin_inches))
                section.top_margin = m
                section.bottom_margin = m
                section.left_margin = m
                section.right_margin = m

        _save_docx_clean(doc, output_path)
        details = []
        if orientation: details.append(orientation)
        if page_size: details.append(page_size)
        if margin_inches is not None: details.append(f"{margin_inches} in margins")
        return {
            "success": True,
            "message": f"Done — updated page setup ({', '.join(details)}).",
        }
    except Exception as e:
        logger.error("Error updating page setup in DOCX: %s", e)
        return {"success": False, "message": f"Failed to update page setup: {str(e)}"}


def insert_docx_page_break(
    doc_path: str,
    output_path: str,
    paragraph_index: int,
) -> dict:
    """Insert a page break after a specific paragraph."""
    try:
        doc = docx.Document(doc_path)
        if paragraph_index < 0 or paragraph_index >= len(doc.paragraphs):
            return {"success": False, "message": "Target paragraph index out of range."}

        target_p = doc.paragraphs[paragraph_index]
        pb_p = doc.add_paragraph()
        pb_p.add_run().add_break(WD_BREAK.PAGE)
        target_p._p.addnext(pb_p._p)

        _save_docx_clean(doc, output_path)
        return {
            "success": True,
            "message": f"Done — inserted page break after paragraph {paragraph_index + 1}.",
        }
    except Exception as e:
        logger.error("Error inserting page break in DOCX: %s", e)
        return {"success": False, "message": f"Failed to insert page break: {str(e)}"}


# ---------------------------------------------------------------------------
# Heading Numbering & TOC (MOD-10)
# ---------------------------------------------------------------------------

def apply_hierarchical_heading_numbers(doc_path: str, output_path: str) -> dict:
    """Apply hierarchical numbering (1, 1.1, 1.1.1) to document headings."""
    try:
        doc = docx.Document(doc_path)
        counters = [0, 0, 0]
        modified_count = 0

        for p in doc.paragraphs:
            style_name = (p.style.name or "").lower() if p.style else ""
            lvl = _heading_level(p, style_name)
            if lvl in (1, 2, 3):
                counters[lvl - 1] += 1
                for i in range(lvl, 3):
                    counters[i] = 0
                prefix = ".".join(str(counters[i]) for i in range(lvl)) + ". "
                # Remove any existing leading numeric prefix
                clean_text = re.sub(r"^([0-9]+\.)*\s*", "", p.text)
                p.text = prefix + clean_text
                modified_count += 1

        if modified_count > 0:
            _save_docx_clean(doc, output_path)
            return {
                "success": True,
                "modified_count": modified_count,
                "message": f"Done — applied hierarchical numbering to {modified_count} heading(s).",
            }
        return {"success": False, "modified_count": 0, "message": "No headings found to number."}
    except Exception as e:
        logger.error("Error applying heading numbers in DOCX: %s", e)
        return {"success": False, "message": f"Failed to apply heading numbers: {str(e)}"}


