import fitz  # PyMuPDF
import io
import logging
import math
import os
import re

from . import header_footer as hf
from .image_geometry import (
    EMU_PER_PT,
    ResizeError,
    describe_change,
    resolve_target_box,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The canonical PDF image index space
# ---------------------------------------------------------------------------
#
# Every PDF feature that refers to an image by number - the editor tiles, the
# image endpoint, `images_count`, PPTX export and the replacement writer -
# numbers them with `iter_pdf_image_slots` below. There used to be three
# independent walks that agreed by luck:
#
#   * `_iter_pdf_images` (export_service)  - counted every *occurrence*
#   * `_page_image_base` (here)            - counted every *occurrence*
#   * the old replacement writer            - counted every *distinct xref*
#
# The third is the bug. A logo used on three pages is three occurrences but one
# xref, so a PDF with any repeat had every image after it off by however many
# repeats came first - the editor said "Image 4", the writer swapped whatever
# xref happened to be fourth in its own list. Deduplicating was introduced to
# avoid double-swapping the same stream, but it silently renumbered every
# image in the document, which is far worse than replacing a logo twice.
#
# This one walk is occurrence-based and is what everything now uses.

def iter_pdf_image_slots(doc):
    """Yield every image occurrence in a PDF, in reading order.

    Each entry is a dict::

        {
          "index": 0,          # the stable public id (occurrence-based)
          "page_num": 0,       # 0-based page
          "xref": 12,          # the image object this occurrence draws
          "mime": "image/png",
          "width": 800,        # stored pixel size
          "height": 600,
          "occurrence": 0,     # 0-based slot on this page (readable ones only)
          "occurrences": 2,    # how many places draw this same xref
        }

    Occurrences of one xref are numbered separately but carry the same ``xref``.
    Replacing any one of them replaces all of them, because a PDF stores the
    pixels once and only the placement is per-page; that is a property of the
    format, not a shortcut. ``occurrences`` lets the caller tell the user.

    Unreadable xrefs are skipped entirely and consume no index, matching what the
    editor renders. ``extract_image`` decodes the whole image, so results are
    cached - a logo stamped on forty pages is decoded once, not forty times.
    """
    readable = {}
    for page in doc:
        for info in page.get_images(full=True):
            xref = info[0]
            if xref in readable:
                continue
            try:
                extracted = doc.extract_image(xref)
            except Exception:
                continue
            if extracted and extracted.get("image"):
                readable[xref] = extracted

    total_by_xref = {}
    for page in doc:
        for info in page.get_images(full=True):
            xref = info[0]
            if xref in readable:
                total_by_xref[xref] = total_by_xref.get(xref, 0) + 1

    index = 0
    for page_num, page in enumerate(doc):
        occurrence = 0
        for info in page.get_images(full=True):
            xref = info[0]
            extracted = readable.get(xref)
            if extracted is None:
                continue
            yield {
                "index": index,
                "page_num": page_num,
                "xref": xref,
                "mime": f"image/{extracted.get('ext', 'png')}",
                "width": extracted.get("width"),
                "height": extracted.get("height"),
                "occurrence": occurrence,
                "occurrences": total_by_xref.get(xref, 1),
            }
            occurrence += 1
            index += 1


def attach_pdf_image_placements(slots, doc):
    """Give every slot the page rectangle it is drawn in.

    ``page.get_images()`` reports images in resource order, which is not the
    order a reader sees them in. Anything that has to talk about "the second
    image on this page" needs geometry, and so does resizing an image (the new
    size has to be applied to the placement, not the stored pixels).

    Each xref can be stamped several times on one page, and ``get_image_info``
    reports those bboxes in placement order - so occurrences of one xref consume
    that list in turn, exactly as :func:`iter_pdf_image_slots` numbers them.
    Sharing one cursor across both is what keeps "the 2nd image" meaning the same
    thing here as in the editor.
    """
    bbox_by_page_xref = {}
    for page_num, page in enumerate(doc):
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception:
            infos = []
        per_xref = {}
        for info in infos:
            per_xref.setdefault(info.get("xref"), []).append(
                list(info["bbox"]) if info.get("bbox") else None
            )
        bbox_by_page_xref[page_num] = per_xref

    cursors = {}
    for slot in slots:
        candidates = bbox_by_page_xref.get(slot["page_num"], {}).get(slot["xref"], [])
        seen = cursors.get((slot["page_num"], slot["xref"]), 0)
        slot["bbox"] = candidates[seen] if seen < len(candidates) else None
        cursors[(slot["page_num"], slot["xref"])] = seen + 1
    return slots


def get_pdf_image_slots(pdf_path: str) -> list:
    """:func:`iter_pdf_image_slots` as a list, for callers holding a path.

    Includes the drawn rectangle (``bbox``) for each slot, because callers that
    address images by position ("the 2nd one on page 3") or resize them need
    geometry, and re-deriving it per caller is how two views end up numbering the
    same page differently.
    """
    try:
        doc = _open_pdf(pdf_path)
    except Exception as exc:
        logger.error("Error opening PDF for image slots: %s", exc)
        return []
    try:
        return attach_pdf_image_placements(list(iter_pdf_image_slots(doc)), doc)
    except Exception as exc:
        logger.error("Error listing PDF image slots: %s", exc)
        return []
    finally:
        doc.close()


def pdf_image_descriptors(pdf_path: str) -> list:
    """JSON-safe image list for the editor, on the canonical index space."""
    return [
        {
            "index": s["index"],
            "mime": s["mime"],
            "width": s["width"],
            "height": s["height"],
            "page_num": s["page_num"],
            "occurrences": s["occurrences"],
        }
        for s in get_pdf_image_slots(pdf_path)
    ]

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
    """Number of images in a PDF, on the canonical index space.

    Was counting distinct xrefs, which disagreed with the editor the moment a
    document repeated a logo - "6 images" in the sidebar next to 9 tiles.
    """
    try:
        doc = _open_pdf(pdf_path)
    except Exception as exc:
        logger.error("Error counting images in PDF: %s", exc)
        return 0
    try:
        return sum(1 for _ in iter_pdf_image_slots(doc))
    except Exception as e:
        logger.error("Error counting images in PDF: %s", e)
        return 0
    finally:
        doc.close()

def apply_pdf_styling(
    pdf_path: str,
    output_path: str,
    font_name: str = None,  # For new additions like headers/footers
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
    doc_filename: str = None,
    line_spacing: float = None,
    target_page: int = None,
) -> bool:
    try:
        doc = _open_pdf(pdf_path)

        # 1. Image replacement
        #    Delegates to the shared writer so /style and /replace-image cannot
        #    drift apart in how they number or match pictures.
        if image_replacements:
            _apply_pdf_image_replacements(doc, image_replacements)

        # 2. Add Header & Footer overlays
        # A font the caller did not choose stays None so the writer inherits the
        # page's existing furniture, rather than imposing Helvetica 10pt grey on
        # a header that was Times New Roman 12pt bold. base14_font keeps the
        # weight: the old family-only mapping turned "TimesNewRomanPS-BoldMT"
        # into regular Times.
        pdf_font = hf.base14_font(font_name) if font_name else None
        f_size = float(font_size) if font_size else None

        header_spec = hf.spec_from_legacy(
            header_text=header_text,
            header_odd=header_text_odd,
            header_even=header_text_even,
            header_first=header_text_first,
        )["header"]
        footer_spec = hf.spec_from_legacy(
            footer_text=footer_text,
            footer_odd=footer_text_odd,
            footer_even=footer_text_even,
            footer_first=footer_text_first,
        )["footer"]

        if target_page is not None:
            if header_text is not None:
                header_spec = {target_page: header_text, "all": None}
            if footer_text is not None:
                footer_spec = {target_page: footer_text, "all": None}

        # "Apply to matching text only" narrows the change to pages whose current
        # band text matches what the editor was showing.
        header_spec = _restrict_spec(header_spec, target_header_text, "header", doc)
        footer_spec = _restrict_spec(footer_spec, target_footer_text, "footer", doc)

        hf.apply_pdf_headers_footers(
            doc,
            {"header": header_spec, "footer": footer_spec},
            fontname=pdf_font,
            fontsize=f_size,
            header_align=header_alignment or alignment or "center",
            footer_align=footer_alignment or alignment or "center",
            title=doc_title or _pdf_title(doc),
            filename=doc_filename or os.path.basename(pdf_path or ""),
            targets={"header": target_header_text, "footer": target_footer_text},
        )

        _save_pdf(doc, output_path)
        doc.close()
        return True
    except Exception as e:
        logger.error("Error applying PDF styling: %s", e)
        return False


def _restrict_spec(spec, target_text, which, doc):
    """Keep a header/footer spec only for pages whose current text matches.

    Returning a per-page variant map is what lets the caller apply the change to
    one repeated header without touching the rest of the document.
    """
    if target_text is None:
        return spec

    wanted_pages = set()
    page_count = doc.page_count
    for index, page in enumerate(doc):
        if hf.band_text(page, which, index + 1, page_count) == target_text:
            wanted_pages.add(index + 1)

    if not wanted_pages:
        return {"all": None, "odd": None, "even": None, "first": None}

    restricted = {"all": None, "odd": None, "even": None, "first": None}
    last = max(wanted_pages)
    for page_number in range(1, last + 1):
        if page_number in wanted_pages:
            restricted["odd" if page_number % 2 else "even"] = spec.get("all")
        else:
            restricted["odd" if page_number % 2 else "even"] = None
    restricted["first"] = spec.get("first") if 1 in wanted_pages else None
    return restricted

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


_BASE14_FONT_NAMES = {
    "tiro": "times-roman",
    "helv": "helvetica",
    "cour": "courier",
}
_BASE14_CODES = tuple(_BASE14_FONT_NAMES)


def _wrap_to_fit(text: str, font, size: float, width: float) -> list:
    """Greedily wrap text to `width` points for base-14 `font` at `size`.

    Explicit newlines are preserved as hard line breaks; a single token wider
    than the target width (long URLs, wide numbers) is placed on its own line
    and allowed to overflow rather than being silently dropped.
    """
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if not current or font.text_length(candidate, fontsize=size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _whiteout_and_write_text(page, rect, text: str, style: dict):
    """Replace the region's content: redact the original glyphs, white-out,
    then write the new text using the detected formatting. No highlight is
    drawn — edits look native in the file; highlighting is preview-only.

    The replacement is added at the *original* font size, wrapped to the region
    width and allowed to flow downward past the box when it is longer than what
    was there. Auto-shrinking (the old behaviour) made a one-line edit of a long
    paragraph render far smaller than the surrounding text, and made a multi-line
    rewrite illegible; flowing keeps the edit legible and never drops text.
    """
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

    size = min(28.0, max(6.0, float(style.get("size") or 9.0)))
    font_code = style.get("font") if style.get("font") in _BASE14_CODES else "helv"
    color = style.get("color") or (0.1, 0.1, 0.1)

    try:
        measure = fitz.Font(fontname=_BASE14_FONT_NAMES[font_code])
    except Exception:
        measure = fitz.Font(fontname="helvetica")

    leading = size * 1.2
    width = max(12.0, rect.width - 6.0)
    page_bottom = page.rect.y1 - size
    y = rect.y0 + size * 0.85

    for line in _wrap_to_fit(text, measure, size, width):
        if y > page_bottom:
            logger.warning("Whiteout write clipped at page bottom (y=%.1f).", y)
            break
        if line:
            page.insert_text(
                (rect.x0, y),
                line,
                fontsize=size,
                fontname=font_code,
                color=color,
                overlay=True,
            )
        y += leading


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


def _pdf_block_rect(page, block_no: int):
    """Rect of the text block numbered ``block_no`` on ``page``, or None.

    Numbering matches :func:`get_pdf_content` exactly: image blocks and blocks
    with no text content are skipped and only counted text blocks advance the
    counter. The `save` path re-derives geometry this way when an edit arrives
    without a bbox - or with a bbox that went stale after an earlier rewrite -
    instead of silently dropping the user's edit.
    """
    counter = -1
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        spans = [sp for line in b.get("lines", []) for sp in line.get("spans", [])]
        spans = [sp for sp in spans if sp.get("text")]
        if not _join_spans(spans):
            continue
        counter += 1
        if counter == block_no:
            return fitz.Rect(b["bbox"])
    return None


def get_pdf_content(pdf_path: str) -> list:
    """Pages of text blocks plus per-page image placements.

    The image ``image_index`` values come from :func:`iter_pdf_image_slots`, the
    same numbering the image endpoint and the replacement writer use. This used
    to number them from ``page.get_image_info()`` while the image endpoint
    numbered from ``page.get_images()`` - PyMuPDF returns those in different
    orders (placement order vs. resource order), so on a page holding two
    different pictures the editor could label one tile with the other's index and
    render the wrong image. The bounding boxes are still taken from
    ``get_image_info`` (it is the only source of placement geometry) but they are
    paired onto slots by xref and occurrence, so the index always comes from the
    canonical walk.
    """
    try:
        doc = _open_pdf(pdf_path)

        slots = list(iter_pdf_image_slots(doc))
        attach_pdf_image_placements(slots, doc)
        slots_by_page = {}
        for slot in slots:
            slots_by_page.setdefault(slot["page_num"], []).append(slot)

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

            for slot in slots_by_page.get(i, []):
                images.append({
                    "image_index": slot["index"],
                    "page_num": i,
                    "xref": slot["xref"],
                    "bbox": slot["bbox"],
                    "width": slot.get("width"),
                    "height": slot.get("height"),
                    "occurrences": slot.get("occurrences", 1),
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


def _pad_to_aspect(img_bytes: bytes, target_ratio: float | None):
    """Letterbox `img_bytes` onto a canvas of `target_ratio`.

    PyMuPDF's ``replace_image`` swaps the pixel stream but keeps the original
    placement rectangle, so a 16:9 upload dropped into a 1:1 slot comes out
    squashed. The content stream's transformation matrix cannot be rewritten
    through the API, so instead the *pixels* are padded to the old box's aspect
    ratio; the rectangle then maps 1:1 onto a correctly-proportioned picture.

    Returns ``(padded_bytes, was_padded)``. Never raises - if padding fails the
    original bytes are returned and the caller proceeds unletterboxed.
    """
    if not target_ratio or target_ratio <= 0:
        return img_bytes, False
    try:
        from PIL import Image

        with Image.open(io.BytesIO(img_bytes)) as src:
            src.load()
            width, height = src.size
            if not width or not height:
                return img_bytes, False
            current_ratio = width / height
            if abs(current_ratio - target_ratio) <= 0.01:
                return img_bytes, False

            if current_ratio > target_ratio:
                new_w, new_h = width, max(1, int(round(width / target_ratio)))
            else:
                new_w, new_h = max(1, int(round(height * target_ratio))), height

            canvas = Image.new("RGB", (new_w, new_h), (255, 255, 255))
            if src.mode in ("RGBA", "LA", "P"):
                src = src.convert("RGBA")
                canvas = Image.new("RGBA", (new_w, new_h), (255, 255, 255, 255))
            canvas.paste(src, ((new_w - width) // 2, (new_h - height) // 2))

            buffer = io.BytesIO()
            canvas.convert("RGB").save(buffer, format="PNG")
            return buffer.getvalue(), True
    except Exception as exc:
        logger.warning("Aspect-ratio padding skipped: %s", exc)
        return img_bytes, False


def _rewrite_pdf_image_xref(doc, xref: int, new_bytes: bytes):
    """Rewrite an image XObject's pixels in place. Returns ``(ok, reason)``.

    Why not ``Page.replace_image``
    ------------------------------
    ``Page.replace_image`` is the obvious call and it does rewrite the object -
    but it also leaves a *second* copy of the XObject entry in that page's
    resource dictionary. PyMuPDF's own ``page.get_images()`` then reports the
    image twice, while the content stream still draws it once.

    That duplicate is not cosmetic here: every image index in this module is an
    occurrence count, so a stray extra entry shifts every subsequent image by
    one. Replacing "Image 5" would quietly become "Image 6" on the next save.
    Rewriting the stream touches only the pixel data and provably leaves the
    page resources and content stream byte-identical, so the index space cannot
    move.

    Returns ``(False, reason)`` for the image flavours this cannot represent
    faithfully - palette (``/Indexed``) images, stencils, odd bit depths - and
    the caller falls back to ``Page.replace_image`` for those.
    """
    # Colour spaces whose samples are not plain component bytes.
    exotic = ("Indexed", "Separation", "DeviceN", "Pattern")

    try:
        if (doc.xref_get_key(xref, "ImageMask")[1] or "false").strip().lower() == "true":
            return False, "it is a stencil mask, not a picture"

        bpc = (doc.xref_get_key(xref, "BitsPerComponent")[1] or "").strip()
        if bpc and bpc != "8":
            return False, f"it uses a {bpc}-bit colour depth"

        cs_kind, cs_value = doc.xref_get_key(xref, "ColorSpace")
        cs = (cs_value or "").strip()
        if cs_kind == "xref":
            resolved = doc.xref_object(int(cs.split()[0])).strip()
            family = re.match(r"\[\s*/(\w+)", resolved)
            family = family.group(1) if family else resolved.lstrip("/").split()[0]
        else:
            family = cs.lstrip("/").split()[0] if cs else ""
        if family in exotic:
            return False, f"it uses a {family} colour space"

        from PIL import Image

        with Image.open(io.BytesIO(new_bytes)) as im:
            im.load()
            rgb = im.convert("RGB")
            raw = rgb.tobytes()
            width, height = rgb.size

        # An inherited soft mask would be composited onto an opaque replacement
        # and punch holes through it, so it is dropped rather than honoured.
        if (doc.xref_get_key(xref, "SMask")[1] or "null").strip() != "null":
            doc.xref_set_key(xref, "SMask", "null")

        doc.xref_set_key(xref, "ColorSpace", "/DeviceRGB")
        doc.xref_set_key(xref, "BitsPerComponent", "8")
        doc.xref_set_key(xref, "Width", str(width))
        doc.xref_set_key(xref, "Height", str(height))
        doc.xref_set_key(xref, "Filter", "/FlateDecode")
        doc.xref_set_key(xref, "DecodeParms", "null")
        doc.update_stream(xref, raw, new=0, compress=1)
        return True, ""
    except Exception as exc:
        logger.warning("In-place PDF image rewrite failed for xref %s: %s", xref, exc)
        return False, str(exc)


def _apply_pdf_image_replacements(doc, replacements: list, size_mode: str = "fit") -> list:
    """Swap image streams in an open PDF, on the canonical index space.

    ``replacements`` is ``[{"target_index": int, "image_bytes": bytes}]`` resolved
    against :func:`iter_pdf_image_slots`. The old implementation built its own
    ``xref`` list with ``if xref not in xrefs``, i.e. it numbered distinct
    streams while the editor numbered occurrences, so any repeated image shifted
    every subsequent target by one.

    ``page.replace_image`` replaces the stream behind an xref everywhere it is
    drawn. That is correct for "replace the logo" and unavoidable for a single
    occurrence - a PDF stores the pixels once - so ``occurrences`` is reported
    back so the caller can say so plainly.
    """
    if not replacements:
        return []

    slots = {s["index"]: s for s in iter_pdf_image_slots(doc)}
    reports = []

    for rep in replacements:
        idx = rep.get("target_index")
        img_bytes = rep.get("image_bytes")
        report = {"index": idx, "replaced": False, "occurrences": 0}

        if idx is None or not img_bytes:
            report["error"] = "No image data was provided."
            reports.append(report)
            continue

        slot = slots.get(idx)
        if slot is None:
            report["error"] = (
                f"Image {idx} does not exist in this document "
                f"(it has {len(slots)} image{'s' if len(slots) != 1 else ''})."
            )
            reports.append(report)
            continue

        payload = img_bytes
        padded = False
        page = doc[slot["page_num"]]
        if size_mode == "fit":
            target_ratio = None
            try:
                for rect in page.get_image_rects(slot["xref"]):
                    if rect.width > 0 and rect.height > 0:
                        target_ratio = rect.width / rect.height
                        break
            except Exception:
                target_ratio = None
            payload, padded = _pad_to_aspect(img_bytes, target_ratio)

        try:
            # Preferred path: rewrite the pixel stream in place. Leaves the page
            # resources and content stream untouched, so no image can shift
            # position in the index space afterwards.
            ok, reason = _rewrite_pdf_image_xref(doc, slot["xref"], payload)
            if not ok:
                # Fallback for image flavours an in-place rewrite cannot express.
                # NOTE: `replace_image` is a *Page* method in PyMuPDF, not a
                # Document one. Calling it on the document raised AttributeError,
                # so PDF image replacement silently did nothing at all - every
                # attempt was swallowed by the broad `except` and logged while
                # the endpoint still reported success.
                #
                # It also leaves a duplicate XObject entry in that page's
                # resources, which shifts later image indices by one, so the
                # report says so and the caller is expected to re-read content.
                doc[slot["page_num"]].replace_image(slot["xref"], stream=payload)
                report["fallback"] = reason
                report["resource_warning"] = True
        except Exception as exc:
            report["error"] = f"Could not write the new image into the PDF: {exc}"
            reports.append(report)
            continue

        report["replaced"] = True
        report["occurrences"] = slot.get("occurrences", 1)
        report["page_num"] = slot["page_num"]
        report["padded"] = padded
        reports.append(report)
        logger.info(
            "Replaced PDF image %d on page %d (xref %d, %d occurrence(s), padded=%s)",
            idx, slot["page_num"], slot["xref"], slot.get("occurrences", 1), padded,
        )

    return reports


def _fmt_pdf_number(value: float) -> bytes:
    """A matrix component, without exponent notation or trailing noise.

    PDF numbers are plain decimals; ``1e-05`` is not a valid operand for every
    consumer, and a full float repr would churn every byte of the stream.
    """
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return (text if text not in ("", "-", "-0") else "0").encode("ascii")


# "... 200 0 0 100 50 682 cm" - the matrix that scales the unit square an image
# is drawn into, which is the only place a PDF records how big a picture prints.
_PDF_CM_RE = re.compile(
    rb"(?P<pre>[-\d\.\s]{6,})cm\b",
)

_PDF_DO_RE = re.compile(rb"/(?P<name>[A-Za-z0-9_.#+\-]+)\s+Do\b")


def _pdf_title(doc) -> str:
    """The document's own title, for the ``{TITLE}`` header/footer field.

    PyMuPDF hands back ``None`` for the common case of a file that never had its
    metadata filled in, so an empty string is the honest answer rather than the
    string "None".
    """
    try:
        return (doc.metadata or {}).get("title") or ""
    except Exception:
        return ""


def _resource_names_for(doc, page) -> dict:
    """``{resource name: xref}`` for the image XObjects on ``page``."""
    names = {}
    try:
        listed = page.get_images(full=True)
    except Exception:
        return names
    for entry in listed:
        # (xref, smask, width, height, bpc, colorspace, alt_colorspace, name, ...)
        if len(entry) > 7 and entry[7]:
            names[str(entry[7])] = entry[0]
    return names


def _scaled_matrix(raw: bytes, new_w: float, new_h: float, anchor: str):
    """Rewrite one ``cm`` operand list to a new size.

    Returns ``(new_bytes, error)``. For an unrotated picture the matrix is
    ``a 0 0 d e f`` where ``a``/``d`` are the printed width and height in points
    and ``e``/``f`` the origin, so only four of the six numbers change.

    Only the numbers are replaced. The whitespace around them is part of the
    stream's structure - dropping the newline after ``q`` yields ``q288`` and the
    page stops parsing.
    """
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    numbers = raw.split()
    if len(numbers) != 6:
        return None, "the image's transform is not a simple six-number matrix"
    try:
        a, b, c, d, e, f = (float(n) for n in numbers)
    except ValueError:
        return None, "the image's transform contains unreadable numbers"

    if abs(b) > 1e-6 or abs(c) > 1e-6:
        # Rotated or skewed. Scaling that correctly means recomposing the
        # matrix rather than replacing components, which is a different (and
        # much larger) piece of work; refuse rather than write a wrong one.
        return None, "this image is rotated, which cannot be resized safely yet"

    if a == 0 or d == 0:
        return None, "this image has a zero-size transform"

    new_a = math.copysign(new_w, a)
    new_d = math.copysign(new_h, d)

    # An image XObject paints into the unit square with its first image row at
    # y=1, so (e, f) is the *bottom* left corner of what the reader sees. Holding
    # e and f unchanged therefore pins the bottom edge and makes a shorter image
    # grow upwards, which is the opposite of what "keep the top left" means.
    if anchor == "center":
        # Keep the middle where it was instead of the top-left corner.
        e += (a - new_a) / 2.0
        f += (d - new_d) / 2.0
    else:
        # top_left: slide the bottom edge down so the top edge stays put.
        f += (d - new_d)

    body = b" ".join(_fmt_pdf_number(v) for v in (new_a, b, c, new_d, e, f))
    return lead + body + (trail or b" "), None


def _resize_pdf_placements(doc, page_num: int, xref: int, new_w: float, new_h: float,
                           anchor: str = "top_left"):
    """Rewrite the drawing matrix of every placement of ``xref`` on a page.

    Returns ``(placements_changed, error)``. PyMuPDF exposes no API for the
    transformation matrix, so the page's content streams are edited directly -
    the same low-level approach already used to swap the pixel streams, and for
    the same reason: the alternatives (redact-and-reinsert) destroy whatever the
    image overlaps.
    """
    page = doc[page_num]
    names = [name for name, value in _resource_names_for(doc, page).items() if value == xref]
    if not names:
        return 0, "this image is not named in the page resources"

    try:
        content_xrefs = list(page.get_contents())
    except Exception:
        content_xrefs = []

    if not content_xrefs:
        return 0, "this page has no content stream to resize"

    wanted = {name.encode("ascii") for name in names}
    changed = 0
    first_error = None

    for cxref in content_xrefs:
        try:
            stream = doc.xref_stream(cxref)
        except Exception:
            continue
        if not stream:
            continue

        pieces = []
        cursor = 0
        stream_changed = False

        for match in _PDF_DO_RE.finditer(stream):
            if match.group("name") not in wanted:
                continue
            # The matrix immediately governing this Do, per the PDF drawing
            # model: a Do paints the unit square as transformed by the current
            # graphics state, which producers set with a cm just above it.
            cm = None
            for cm_match in _PDF_CM_RE.finditer(stream, 0, match.start()):
                cm = cm_match
            if cm is None:
                first_error = first_error or (
                    "this image's size is set in a way that cannot be rewritten safely"
                )
                continue

            replacement, error = _scaled_matrix(
                cm.group("pre"), new_w, new_h, anchor
            )
            if error:
                first_error = first_error or error
                continue

            pieces.append(stream[cursor:cm.start("pre")])
            pieces.append(replacement)
            cursor = cm.end("pre")
            stream_changed = True
            changed += 1

        if stream_changed:
            pieces.append(stream[cursor:])
            try:
                doc.update_stream(cxref, b"".join(pieces))
            except Exception as exc:
                logger.error("Failed to write resized content stream %d: %s", cxref, exc)
                changed = max(0, changed - 1)
                first_error = first_error or f"could not save the resized page: {exc}"

    if not changed:
        return 0, first_error or "this image could not be resized"
    return changed, None


def _apply_pdf_image_resizes(doc, resizes: list) -> list:
    """Apply resize requests to an open PDF, on the canonical index space."""
    slots = {s["index"]: s for s in iter_pdf_image_slots(doc)}
    # A resize is measured against what is currently printed, so the placement
    # rectangles are required - iter_pdf_image_slots does not attach them.
    attach_pdf_image_placements(list(slots.values()), doc)
    reports = []

    for req in resizes:
        idx = req.get("target_index")
        report = {"index": idx, "resized": False, "placements": 0}

        if idx is None:
            report["error"] = "No image was identified to resize."
            reports.append(report)
            continue

        slot = slots.get(idx)
        if slot is None:
            report["error"] = (
                f"Image {idx} does not exist in this document "
                f"(it has {len(slots)} image{'s' if len(slots) != 1 else ''})."
            )
            reports.append(report)
            continue

        anchor = req.get("anchor", "top_left")
        current_w = slot.get("bbox")
        try:
            old_w_emu = int(round((current_w[2] - current_w[0]) * EMU_PER_PT)) if current_w else 0
            old_h_emu = int(round((current_w[3] - current_w[1]) * EMU_PER_PT)) if current_w else 0
            new_w_emu, new_h_emu = resolve_target_box(
                old_w_emu, old_h_emu,
                width=req.get("width"),
                height=req.get("height"),
                unit=req.get("unit", "px"),
                keep_aspect=req.get("keep_aspect", True),
            )
        except ResizeError as exc:
            report["error"] = str(exc)
            reports.append(report)
            continue

        if old_w_emu <= 0 or old_h_emu <= 0:
            report["error"] = (
                "This image has no readable position on the page, so it cannot "
                "be resized. Replace it instead."
            )
            reports.append(report)
            continue

        new_w_pt = new_w_emu / EMU_PER_PT
        new_h_pt = new_h_emu / EMU_PER_PT

        changed, error = _resize_pdf_placements(
            doc, slot["page_num"], slot["xref"], new_w_pt, new_h_pt, anchor
        )
        if error and not changed:
            report["error"] = error
            reports.append(report)
            continue

        report["resized"] = True
        report["placements"] = changed
        report["change"] = describe_change(old_w_emu, old_h_emu, new_w_emu, new_h_emu)
        reports.append(report)

    return reports


def resize_pdf_images(pdf_path: str, output_path: str, resizes: list) -> dict:
    """Resize images in a PDF, writing the result to ``output_path``.

    Same request shape and ``{"ok", "resized", "reports", "error"}`` contract as
    :func:`replace_pdf_images`.
    """
    if not resizes:
        return {"ok": False, "resized": 0, "reports": [], "error": "No image was identified to resize."}

    try:
        doc = _open_pdf(pdf_path)
    except Exception as exc:
        return {"ok": False, "resized": 0, "reports": [], "error": f"Could not open the PDF: {exc}"}

    try:
        reports = _apply_pdf_image_resizes(doc, resizes)
    except Exception as exc:
        logger.error("Error resizing PDF images: %s", exc)
        return {"ok": False, "resized": 0, "reports": [], "error": str(exc)}

    resized = sum(1 for r in reports if r.get("resized"))

    if resized:
        try:
            _save_pdf(doc, output_path)
        except Exception as exc:
            logger.error("Error saving PDF after image resize: %s", exc)
            return {"ok": False, "resized": resized, "reports": reports, "error": str(exc)}
    else:
        doc.close()

    if not resized:
        first_error = next((r.get("error") for r in reports if r.get("error")), None)
        return {
            "ok": False,
            "resized": 0,
            "reports": reports,
            "error": first_error or "No images were resized.",
        }

    doc.close()
    return {"ok": True, "resized": resized, "reports": reports, "error": None}


def replace_pdf_images(
    pdf_path: str,
    output_path: str,
    replacements: list,
    size_mode: str = "fit",
) -> dict:
    """Replace images in a PDF and write the result to ``output_path``.

    Returns ``{"ok": bool, "replaced": n, "reports": [...], "error": str|None}``.
    Never raises: callers turn ``error`` into an HTTP message.
    """
    try:
        doc = _open_pdf(pdf_path)
    except Exception as exc:
        return {"ok": False, "replaced": 0, "reports": [], "error": f"Could not open the document: {exc}"}

    try:
        reports = _apply_pdf_image_replacements(doc, replacements, size_mode)
        replaced = sum(1 for r in reports if r.get("replaced"))
        if not replaced:
            first_error = next((r.get("error") for r in reports if r.get("error")), None)
            doc.close()
            return {
                "ok": False, "replaced": 0, "reports": reports,
                "error": first_error or "No images were replaced.",
            }
        _save_pdf(doc, output_path)
        doc.close()
    except Exception as exc:
        logger.error("Error replacing PDF images: %s", exc)
        return {"ok": False, "replaced": 0, "reports": [], "error": str(exc)}

    return {"ok": True, "replaced": replaced, "reports": reports, "error": None}


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
                text = b_edit.get("text")
                if text is None:
                    continue

                bbox = b_edit.get("bbox")
                rect = None
                if bbox:
                    try:
                        rect = fitz.Rect(bbox)
                    except Exception:
                        rect = None

                # The preview may carry no bbox at all, or a stale one once a
                # surrounding rewrite changed the page. Re-derive it from the
                # live page before giving up on the edit.
                if rect is None or rect.is_empty:
                    rect = _pdf_block_rect(page, b_edit.get("block_no"))
                    if rect is None:
                        logger.warning(
                            "Skipping PDF edit with no resolvable block (page %s, block %s).",
                            page_num, b_edit.get("block_no"),
                        )
                        continue

                style = _pick_block_style(doc, page_num, [rect.x0, rect.y0, rect.x1, rect.y1])
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
        escaped_tokens = [re.escape(tok) for tok in re.split(r"\s+", find_text.strip()) if tok]
        escaped_pattern = r"\s+".join(escaped_tokens) if escaped_tokens else re.escape(find_text)
        start_b = r"\b" if (find_text and (find_text[0].isalnum() or find_text[0] == "_")) else r"(?<!\w)"
        end_b = r"\w*" if (find_text and (find_text[-1].isalnum() or find_text[-1] == "_")) else r"(?!\w)"
        prefix_pattern = re.compile(start_b + escaped_pattern + end_b, flags)

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
        try:
            result = hf.read_pdf_headers_footers(doc)
            return result
        finally:
            doc.close()
    except Exception as e:
        logger.error("Error getting PDF headers/footers: %s", e)
        return {"headers": [], "footers": []}

def update_pdf_header_footer(
    pdf_path: str,
    output_path: str,
    header_text: str = None,
    footer_text: str = None,
    **kwargs,
) -> bool:
    return apply_pdf_styling(pdf_path, output_path, header_text=header_text,
                             footer_text=footer_text, **kwargs)

