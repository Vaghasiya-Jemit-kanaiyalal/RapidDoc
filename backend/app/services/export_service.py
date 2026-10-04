"""Export / format-conversion pipeline.

The goal of this module is fidelity. The previous implementation flattened
every document to a single string of plain text and re-rendered it into a blank
document, which silently destroyed images, tables, fonts and layout on every
PDF -> DOCX/TXT/PPTX export. This version:

* PDF  -> DOCX : real layout-aware conversion via ``pdf2docx`` (PyMuPDF based),
  which keeps images, tables, columns, fonts, sizes, colours and bold/italic.
  A text-only builder is kept as a last-resort fallback so an export never
  hard-fails just because the converter choked on one odd page.
* DOCX -> TXT  : paragraphs *and* tables are walked in true document order
  (previously every table was dumped at the end of the file).
* PDF  -> TXT  : uses PyMuPDF's own text extraction, which keeps line breaks
  instead of gluing every word of a line together.
* *    -> PPTX : keeps the existing text layout and additionally embeds images
  found in the source document.
"""

import hashlib
import io
import logging
import os
import re
import tempfile
import threading
from collections import OrderedDict

import docx
from docx.shared import Pt

from RapidDoc.backend.app.services.docx_editor import (
    get_docx_content,
    get_docx_image_parts,
    iter_docx_body_items,
)
from RapidDoc.backend.app.services.pdf_converter import convert_docx_bytes_to_pdf
from RapidDoc.backend.app.services.pdf_editor import get_pdf_content, get_pdf_image_slots

logger = logging.getLogger(__name__)

# pdf2docx renders by rasterising pages, so give it room on large documents
# but never let a single export hold a worker thread forever.
PDF2DOCX_TIMEOUT_SECONDS = 180

# ---------------------------------------------------------------------------
# Export result cache
#
# Conversion is a pure function of the stored file plus the requested options,
# so the same document exported twice produced byte-identical output while
# redoing all the work: 1.5s for a DOCX->PPTX build and 2.6s for PDF->PPTX on
# every single click, and ~1s for a PDF->DOCX rebuild. Keying on the content
# hash makes a repeat export instant, and because the key is the content itself
# an edited document can never serve a stale deck.
#
# DOCX->PDF is deliberately not cached here; pdf_converter already caches it
# around the LibreOffice subprocess, which is by far the slowest step.
# ---------------------------------------------------------------------------
_CACHE_MAX_ENTRIES = 12
_CACHE_MAX_BYTES = 128 * 1024 * 1024
_cache_lock = threading.Lock()
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_cache_bytes = 0

# Collapse concurrent identical builds: a user double-clicking "Export to
# PowerPoint" should trigger one render, not two.
_inflight: dict = {}
_inflight_lock = threading.Lock()


def _export_cache_key(file_path: str, fmt: str, file_type: str, theme: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{digest.hexdigest()}:{file_type}:{fmt}:{theme or ''}"


def _cache_get(key: str):
    with _cache_lock:
        value = _cache.get(key)
        if value is not None:
            _cache.move_to_end(key)
        return value


def _cache_put(key: str, value: bytes) -> None:
    global _cache_bytes
    with _cache_lock:
        if key in _cache:
            _cache_bytes -= len(_cache.pop(key))
        _cache[key] = value
        _cache.move_to_end(key)
        _cache_bytes += len(value)
        while _cache and (len(_cache) > _CACHE_MAX_ENTRIES
                          or _cache_bytes > _CACHE_MAX_BYTES):
            evicted_key, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted)
            logger.debug("Evicted cached export %s", evicted_key[:12])


def clear_export_cache() -> None:
    global _cache_bytes
    with _cache_lock:
        _cache.clear()
        _cache_bytes = 0


def _cached_build(file_path: str, fmt: str, file_type: str, theme: str, build):
    """Return ``(bytes, was_cached)`` for an export, rendering at most once.

    The inflight map means a second request for the same document and format
    waits on the first render rather than starting a duplicate one - the deck
    build is CPU-bound, so two at once is slower than either alone.

    Cache status is returned rather than stashed in module state, because these
    builds run in a threadpool and a shared flag would report whichever request
    happened to finish last.
    """
    try:
        key = _export_cache_key(file_path, fmt, file_type, theme)
    except OSError:
        # Unreadable source: let the builder raise its own, clearer error.
        return build(), False

    hit = _cache_get(key)
    if hit is not None:
        logger.info("Export cache hit: %s/%s", fmt, theme or "-")
        return hit, True

    with _inflight_lock:
        event = _inflight.get(key)
        if event is None:
            event = threading.Event()
            _inflight[key] = event
            owner = True
        else:
            owner = False

    if not owner:
        # Another thread is already building exactly this output.
        event.wait(timeout=PDF2DOCX_TIMEOUT_SECONDS)
        hit = _cache_get(key)
        if hit is not None:
            return hit, True
        return build(), False

    try:
        data = build()
        _cache_put(key, data)
        return data, False
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        event.set()


def _read_bytes(file_path: str) -> bytes:
    with open(file_path, "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_docx_text(file_path: str) -> str:
    """Plain text of a DOCX with tables kept in their real document position."""
    parts = []
    for kind, payload in iter_docx_body_items(file_path):
        if kind == "paragraph":
            parts.append(payload.get("text") or "")
        elif kind == "table":
            for row in payload.get("rows") or []:
                parts.append(" | ".join((cell or "").replace("\n", " ") for cell in row))
    return "\n".join(parts)


def _extract_pdf_text(file_path: str) -> str:
    """Plain text of a PDF, one line per text line (no word-gluing)."""
    import fitz  # PyMuPDF

    lines = []
    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc):
            lines.append(f"\n--- Page {i + 1} ---")
            lines.append(page.get_text("text").rstrip())
    return "\n".join(lines)


def _extract_text(file_path: str, file_type: str) -> str:
    """Plain-text dump of a stored DOCX or PDF file."""
    if file_type == "docx":
        return _extract_docx_text(file_path)
    if file_type == "pdf":
        return _extract_pdf_text(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


# ---------------------------------------------------------------------------
# PDF -> DOCX
# ---------------------------------------------------------------------------

def _pdf_to_docx_with_layout(pdf_path: str) -> bytes:
    """Layout-preserving PDF -> DOCX using pdf2docx."""
    from pdf2docx import Converter

    with tempfile.TemporaryDirectory(prefix="rapiddoc_export_") as tmp_dir:
        # pdf2docx's Converter can take a path; give it a private copy so a
        # concurrent edit of the stored file cannot corrupt the conversion.
        local_pdf = os.path.join(tmp_dir, "source.pdf")
        with open(local_pdf, "wb") as fh:
            fh.write(_read_bytes(pdf_path))

        local_docx = os.path.join(tmp_dir, "converted.docx")
        cv = Converter(local_pdf)
        try:
            cv.convert(local_docx)
        finally:
            try:
                cv.close()
            except Exception:
                pass

        if not os.path.exists(local_docx) or os.path.getsize(local_docx) == 0:
            raise RuntimeError("pdf2docx produced no output")
        with open(local_docx, "rb") as fh:
            return fh.read()


def _text_to_docx_bytes(text: str) -> bytes:
    """Last-resort fallback: rebuild a readable DOCX from flat text."""
    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--- Page "):
            d.add_heading(stripped.strip("-").strip(), level=1)
        elif not stripped:
            d.add_paragraph("")
        else:
            d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def build_docx_bytes(file_path: str, file_type: str, theme: str = "") -> bytes:
    return build_docx_bytes_with_status(file_path, file_type, theme)[0]


def build_docx_bytes_with_status(file_path: str, file_type: str,
                                 theme: str = "") -> tuple:
    """DOCX export as ``(bytes, was_cached)``."""
    return _cached_build(file_path, "docx", file_type, theme,
                         lambda: _build_docx_uncached(file_path, file_type))


def _build_docx_uncached(file_path: str, file_type: str) -> bytes:
    if file_type == "docx":
        return _read_bytes(file_path)
    if file_type == "pdf":
        try:
            data = _pdf_to_docx_with_layout(file_path)
        except Exception as exc:
            # Never fail the download outright: a text-only Word file is far
            # better than a 500, and the caller already validates the output.
            logger.error(
                "Layout-aware PDF->DOCX conversion failed (%s); falling back to "
                "the text-only builder. Images and tables will be missing.",
                exc,
            )
            return _text_to_docx_bytes(_extract_text(file_path, "pdf"))
        if not data[:4] == b"PK\x03\x04":
            logger.error("pdf2docx returned a non-DOCX payload; using the text-only builder.")
            return _text_to_docx_bytes(_extract_text(file_path, "pdf"))
        return data
    raise ValueError(f"Unsupported file type: {file_type}")


# ---------------------------------------------------------------------------
# Other formats
# ---------------------------------------------------------------------------

def build_pdf_bytes(file_path: str, file_type: str) -> bytes:
    if file_type == "pdf":
        return _read_bytes(file_path)
    if file_type == "docx":
        return convert_docx_bytes_to_pdf(_read_bytes(file_path))
    raise ValueError(f"Unsupported file type: {file_type}")


def build_txt_bytes(file_path: str, file_type: str, theme: str = "") -> bytes:
    return build_txt_bytes_with_status(file_path, file_type, theme)[0]


def build_txt_bytes_with_status(file_path: str, file_type: str,
                                theme: str = "") -> tuple:
    """TXT export as ``(bytes, was_cached)``."""
    return _cached_build(
        file_path, "txt", file_type, theme,
        lambda: _extract_text(file_path, file_type).encode("utf-8"),
    )


def document_items(file_path: str, file_type: str) -> list:
    """Content items for a document, used by the PPT suitability check."""
    if file_type == "docx":
        return _docx_items(file_path)
    if file_type == "pdf":
        return _pdf_items(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


def _docx_items(file_path: str) -> list:
    """Ordered body items (paragraphs / tables / images) as plain dicts."""
    return [{"kind": kind, **payload} for kind, payload in iter_docx_body_items(file_path)]


_TRAILING_PAGE_NO = re.compile(r"[\s\-–—_|/\\]*\d+\s*$")


def _normalize_for_match(text: str) -> str:
    """Collapse a block to a comparable key for repeated-content detection.

    A trailing page number is stripped first. A report footer reads
    ``DEPSTAR - CSE - C   1`` on page 1 and ``...   2`` on page 2; without
    removing the number no two footers ever match, so the footer was not
    recognised as furniture and became the heading of every slide.
    """
    collapsed = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return _TRAILING_PAGE_NO.sub("", collapsed).strip()


def _is_margin_furniture(block: dict, page_height: float) -> bool:
    """True for a block sitting entirely inside the top or bottom page margin.

    Page headers and footers live in the margin band. Content never starts
    there, so position alone is enough to recognise them - and unlike text
    matching it still works when the footer carries a page number.
    """
    bbox = block.get("bbox")
    if not bbox or not page_height:
        return False
    top, bottom = bbox[1], bbox[3]
    band = page_height * 0.09
    return bottom <= band or top >= page_height - band


def _running_text_blocks(pages: list) -> set:
    """Identify running headers/footers, which repeat on most pages.

    A PDF report prints its title block at the top of every page. The exporter
    used to take the largest-font block as the slide heading, so every slide in
    the deck came out titled "Subject: ITUE301 - Advanced Web Development
    Frameworks ..." - eight slides, one repeated heading, and the real content
    buried underneath. Two signals are used: text that repeats across the
    document, and blocks positioned in the page margin.
    """
    seen = {}
    for page in pages:
        for key in {
            _normalize_for_match(b.get("text"))
            for b in (page.get("blocks") or [])
            if (b.get("text") or "").strip()
        }:
            seen[key] = seen.get(key, 0) + 1

    threshold = max(2, int(len(pages) * 0.6))
    running = {key for key, count in seen.items() if count >= threshold}
    if not running and len(pages) < 3:
        return set()
    return running


def _pdf_items(file_path: str) -> list:
    """One pseudo-item per PDF page, carrying the page index for image matching.

    A PDF has no heading structure to read, so each page becomes one item. The
    heading is the largest *real* block on the page; the rest is body text.
    Running headers and footers are detected across the whole document and
    dropped, because promoting one to a slide title gave every slide the same
    heading. A page with no text of its own is emitted as an image slide, since
    in a screenshot report such a page *is* the screenshot.
    """
    pages = get_pdf_content(file_path)
    running = _running_text_blocks(pages)
    # Position only means "page furniture" once repetition has been seen, so on
    # a one or two page document a title that happens to sit high on the page is
    # still treated as content.
    use_geometry = len(pages) >= 3

    def is_furniture(block, page_height):
        if _normalize_for_match(block.get("text")) in running:
            return True
        return use_geometry and _is_margin_furniture(block, page_height)

    items = []
    used_titles = {}
    for page in pages:
        page_height = page.get("height") or 0
        blocks = [
            b for b in (page.get("blocks") or [])
            if (b.get("text") or "").strip()
        ]
        # Drop page furniture: margin-positioned blocks, and text repeated
        # across the document. Note there is deliberately no fallback to the
        # unfiltered list - if every block on a page is furniture then the page
        # holds no text at all, which is handled below.
        content_blocks = [b for b in blocks if not is_furniture(b, page_height)]

        biggest = max(content_blocks, key=lambda b: b.get("size") or 0) if content_blocks else None
        title = (biggest.get("text") or "").strip() if biggest else ""
        title = re.sub(r"\s+", " ", title).strip()

        body_lines = []
        for b in content_blocks:
            if b is biggest:
                continue
            for line in re.split(r"\n+", (b.get("text") or "")):
                line = line.strip()
                if line:
                    body_lines.append(line)

        page_label = f"Page {page['page_num'] + 1}"
        if not title and not body_lines:
            # A text-free page in a report is a screenshot; let the deck show it
            # instead of emitting an empty slide.
            items.append({
                "kind": "image_page",
                "index": page["page_num"],
                "text": page_label,
                "source_page": page["page_num"],
            })
            continue

        # A heading still repeated across pages (e.g. "Chapter 2") must not
        # become an identical slide title either - qualify it with the page.
        if title:
            if title in used_titles:
                used_titles[title] += 1
                title = f"{title} - {page_label}"
            else:
                used_titles[title] = 1
        else:
            title = page_label

        # The heading and the body are emitted separately. Joining them with
        # newlines into one paragraph made the title-inference heuristic treat
        # the whole first page as the document title, producing a title slide
        # that was a wall of text immediately followed by a slide repeating it.
        items.append({
            "kind": "paragraph",
            "index": page["page_num"],
            "text": title,
            "heading_level": 1,
            "is_list_item": False,
            "source_page": page["page_num"],
        })
        if body_lines:
            items.append({
                "kind": "paragraph",
                "index": page["page_num"],
                "text": "\n".join(body_lines),
                "heading_level": 0,
                "is_list_item": False,
                "source_page": page["page_num"],
            })
    return items


def _attach_pictures(slides: list, file_path: str, file_type: str) -> list:
    """Give slides an image where the source document had one.

    DOCX pictures are matched by the paragraph they are anchored after, so a
    screenshot lands on the slide built from the text it illustrates rather than
    on whichever slide happened to come first. PDF page images are matched to the
    slide built from that page via `source_page`. Anything that cannot be placed
    is left out - a picture that will not embed must never cost us the text.
    """
    if file_type == "docx":
        try:
            parts = [p for p in get_docx_image_parts(file_path) if p.get("blob")]
        except Exception as exc:
            logger.warning("Could not read DOCX images for PPTX export: %s", exc)
            return slides
        if not parts:
            return slides

        placeable = ("bullets", "section", "image")

        def as_picture(part):
            return io.BytesIO(part["blob"]), (part.get("mime") or "image/png").split("/")[-1]

        # Anchor-order first so document order is respected, then the unanchored
        # pictures (logos and anything inside a table) fill whatever is left.
        anchored = [p for p in parts if p.get("anchor_index") is not None]
        unanchored = [p for p in parts if p.get("anchor_index") is None]

        for part in sorted(anchored, key=lambda p: p["anchor_index"]):
            anchor = part["anchor_index"]
            for slide in slides:
                if slide.get("picture") or slide["layout"] not in placeable:
                    continue
                if anchor in (slide.get("source_paragraphs") or ()):
                    slide["picture"] = as_picture(part)
                    break

        for part in unanchored:
            for slide in slides:
                if slide.get("picture") or slide["layout"] != "bullets":
                    continue
                slide["picture"] = as_picture(part)
                break

        return slides

    if file_type == "pdf":
        for slide in slides:
            page_num = slide.get("source_page")
            if page_num is None or slide.get("picture"):
                continue
            try:
                picture = get_page_image_stream(file_path, "pdf", page_num)
            except Exception as exc:
                logger.warning("Could not read page image for PPTX export: %s", exc)
                picture = None
            if picture:
                slide["picture"] = picture
    return slides


def build_pptx_bytes(file_path: str, file_type: str, theme: str = "modern") -> bytes:
    return build_pptx_bytes_with_status(file_path, file_type, theme)[0]


def build_pptx_bytes_with_status(file_path: str, file_type: str,
                                 theme: str = "modern") -> tuple:
    """PPTX export as ``(bytes, was_cached)``."""
    return _cached_build(file_path, "pptx", file_type, theme,
                         lambda: _build_pptx_uncached(file_path, file_type, theme))


def _build_pptx_uncached(file_path: str, file_type: str, theme: str) -> bytes:
    """Render a document into a real slide deck.

    Structure comes from the document itself (heading levels, then table shape),
    and each slide is laid out by a named template rather than one generic
    textbox, so prose, tables and images each get a layout that suits them.
    """
    from RapidDoc.backend.app.services.ppt_templates import build_outline, render_deck

    if file_type == "docx":
        items = _docx_items(file_path)
    elif file_type == "pdf":
        items = _pdf_items(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    slides = _attach_pictures(build_outline(items), file_path, file_type)

    prs = render_deck(slides, theme=theme)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Image extraction (shared by the /content image endpoint and PPTX export)
# ---------------------------------------------------------------------------

def _iter_pdf_images(file_path: str):
    """Yield ``(index, xref, mime, width, height)`` for every PDF image, in order.

    Thin adapter over :func:`pdf_editor.iter_pdf_image_slots`, which is the one
    canonical PDF image index space. This used to re-implement the walk itself;
    the replacement writer numbered distinct xrefs while this counted
    occurrences, so any PDF that repeated an image handed out numbers the writer
    could not resolve. Deriving both from the same slots is what stops that.
    """
    for slot in get_pdf_image_slots(file_path):
        yield (
            slot["index"],
            slot["xref"],
            slot["mime"],
            slot["width"],
            slot["height"],
        )


def get_document_images(file_path: str, file_type: str) -> list:
    """Image descriptors for a document, in reading order.

    Each entry is ``{"index", "mime", "width", "height"}``. The raw bytes are
    intentionally not included; callers fetch them through the image endpoint.
    """
    if file_type == "docx":
        return [
            {"index": part["index"], "mime": part["mime"],
             "width": part["width"], "height": part["height"]}
            for part in get_docx_image_parts(file_path)
        ]

    if file_type == "pdf":
        return [
            {"index": idx, "mime": mime, "width": width, "height": height}
            for idx, _xref, mime, width, height in _iter_pdf_images(file_path)
        ]

    raise ValueError(f"Unsupported file type: {file_type}")


def get_document_image_bytes(file_path: str, file_type: str, index: int):
    """``(bytes, mime)`` for one image, or ``(None, None)`` when out of range."""
    if file_type == "docx":
        for part in get_docx_image_parts(file_path):
            if part["index"] == index:
                return part["blob"], part["mime"]
        return None, None

    if file_type == "pdf":
        import fitz

        for idx, xref, mime, _w, _h in _iter_pdf_images(file_path):
            if idx != index:
                continue
            with fitz.open(file_path) as doc:
                extracted = doc.extract_image(xref)
            if extracted and extracted.get("image"):
                return extracted["image"], mime
            return None, None
        return None, None

    raise ValueError(f"Unsupported file type: {file_type}")


def get_page_image_stream(file_path: str, file_type: str, page_num: int):
    """First image on a given page as ``(BytesIO, ext)``, for PPTX embedding."""
    if file_type != "pdf" or page_num < 0:
        return None
    import fitz

    with fitz.open(file_path) as doc:
        if page_num >= doc.page_count:
            return None
        page = doc[page_num]
        for info in page.get_images(full=True):
            try:
                extracted = doc.extract_image(info[0])
            except Exception:
                continue
            if extracted and extracted.get("image"):
                return io.BytesIO(extracted["image"]), extracted.get("ext", "png")
    return None

