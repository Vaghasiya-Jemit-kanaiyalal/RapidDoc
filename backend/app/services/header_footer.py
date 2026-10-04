"""Headers and footers that behave the way a word processor's do.

Three things were wrong with the previous implementation, and all three showed up
in real documents:

1. It painted an opaque white rectangle across the whole top (and bottom) 45
   points of *every* page. Any body content that started up in that band -
   which is common in reports with a small top margin - disappeared behind a
   white box. The fix is to erase only the glyphs that are actually there: each
   existing span is redacted by its own bounding box, so nothing else is
   touched.

2. A page number was written as literal text, so every page carried the same
   number. Fields are now real: DOCX gets Word field codes (``{ PAGE }``), and
   PDF gets the correct value for *that* page, because a PDF page has no
   page-number context to interpolate later.

3. There was no way to say "left pages differ from right pages", which is the
   normal case for a report with the ID on one side and the title on the other.
   Both formats now support odd/even variants plus a separate first page.

A header is a *band* taken from the page's own top margin rather than a fixed
45 points, so it lands where the reader expects it and does not eat into the
body on documents with generous margins.
"""

import logging
import re
from datetime import datetime

import fitz
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

logger = logging.getLogger(__name__)

# Field macros the UI can insert. Both the brace and the guillemet spelling are
# accepted because documents in the wild use either.
FIELD_NAMES = ("PAGE", "NUMPAGES", "DATE", "TIME", "TITLE", "FILENAME")

FIELD_RE = re.compile(
    r"\{\s*(" + "|".join(FIELD_NAMES) + r")\s*\}"
    r"|<<\s*(" + "|".join(FIELD_NAMES) + r")\s*>>",
    re.IGNORECASE,
)

# Header/footer text is grey rather than black: it is furniture, and the body is
# what the reader is there for. Only used when there is no existing furniture to
# inherit from - replacing a black bold header with small grey text is a
# downgrade the user never asked for.
DEFAULT_COLOR = (0.25, 0.25, 0.25)

# Likewise the fallback size for a page that has no furniture to learn from.
DEFAULT_FONT_SIZE = 10.0

# The nominal band depth, used when the page's own margin cannot be read.
DEFAULT_BAND = 45.0

# How far from the paper edge a band is allowed to reach. Furniture never starts
# here - body text on a marginless page can, which is what NEAR_EDGE guards.
EDGE_INSET = 8.0

# A band thinner than this cannot hold 8-10pt text without clipping, and a band
# deeper than this starts covering body content.
MIN_BAND = 30.0
MAX_BAND = 72.0

# Used only when a page has no existing furniture to align to: roughly the 1in
# margin of a US Letter page, capped so it never eats a narrow page.
FALLBACK_INSET = 72.0

# The narrowest text column a replacement will be laid out in before the writer
# gives up and falls back to the full band.
MIN_COLUMN = 48.0

ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

PDF_ALIGNMENTS = {
    "left": fitz.TEXT_ALIGN_LEFT,
    "center": fitz.TEXT_ALIGN_CENTER,
    "right": fitz.TEXT_ALIGN_RIGHT,
}

# A tab inside a variant's text splits it into a left and a right section. This
# is the way a real report header is built - the subject on the left, the ID on
# the right - and a tab is how Word itself expresses it, so the same stored text
# renders correctly in a DOCX tab stop and in a PDF as two aligned boxes.
SPLIT_CHAR = "\t"


def split_parts(text):
    """``(left, right)`` for a variant's text.

    Text without a tab is a single section and comes back as ``(text, "")``, so
    every existing header keeps rendering exactly as it did.
    """
    if not text:
        return "", ""
    if SPLIT_CHAR not in text:
        return text, ""
    left, _, right = text.partition(SPLIT_CHAR)
    return left, right


def join_parts(left, right):
    """Build a variant's text from its two sections."""
    left = (left or "").strip()
    right = (right or "").strip()
    if not right:
        return left
    if not left:
        return SPLIT_CHAR + right
    return f"{left}{SPLIT_CHAR}{right}"


def has_split(text) -> bool:
    return bool(text) and SPLIT_CHAR in text


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------

def parse_segments(text):
    """Split header/footer text into ``("text"|"field", value)`` segments.

    Splitting rather than substituting up front is what lets DOCX emit a live
    Word field while PDF renders that page's actual value from the same input.
    """
    if not text:
        return []

    segments = []
    cursor = 0
    for match in FIELD_RE.finditer(text):
        if match.start() > cursor:
            segments.append(("text", text[cursor:match.start()]))
        segments.append(("field", (match.group(1) or match.group(2)).upper()))
        cursor = match.end()
    if cursor < len(text):
        segments.append(("text", text[cursor:]))
    return segments


def has_field(text) -> bool:
    return any(kind == "field" for kind, _ in parse_segments(text))


def field_value(name, page_number=None, page_count=None, title="", filename=""):
    """Resolve one field macro to the value it should show."""
    now = datetime.now()
    if name == "PAGE":
        return str(page_number if page_number is not None else 1)
    if name == "NUMPAGES":
        return str(page_count if page_count is not None else 1)
    if name == "DATE":
        return now.strftime("%Y-%m-%d")
    if name == "TIME":
        return now.strftime("%H:%M")
    if name == "TITLE":
        return title or ""
    if name == "FILENAME":
        return filename or ""
    return ""


def render(text, page_number=None, page_count=None, title="", filename="") -> str:
    """Header/footer text with every field replaced by a concrete value."""
    out = []
    for kind, value in parse_segments(text):
        out.append(value if kind == "text" else field_value(
            value, page_number, page_count, title, filename))
    return "".join(out)


# ---------------------------------------------------------------------------
# Choosing which text a page gets
# ---------------------------------------------------------------------------

def text_for_page(spec, page_number):
    """The variant that applies to a 1-based page number.

    ``first`` wins on page 1, then odd/even by page number, then the blanket
    value. Returning ``None`` means "leave this page alone" - which is what makes
    a different-first-page setting possible without blanking the rest.
    """
    if not spec:
        return None
    if page_number == 1 and spec.get("first") is not None:
        return spec["first"]
    if spec.get("odd") is not None or spec.get("even") is not None:
        variant = "odd" if page_number % 2 else "even"
        chosen = spec.get(variant)
        if chosen is not None:
            return chosen
    return spec.get("all")


def _blank_to_none(value):
    """A text box the user cleared means "not set", not "erase the band".

    The browser posts ``""`` for a field the user emptied. Treating that as a
    real value made the writer erase the existing furniture and then decline to
    write anything, which is how a whole header/footer could disappear.
    """
    if value is None:
        return None
    if not str(value).strip():
        return None
    return value


def spec_from_legacy(header_text=None, footer_text=None,
                     header_odd=None, header_even=None, header_first=None,
                     footer_odd=None, footer_even=None, footer_first=None) -> dict:
    """Build the variant spec from the flat request fields the API accepts.

    An odd/even pair supplied without a blanket value falls back to the odd text
    for odd pages and the even text for even pages, and leaves the first page on
    the odd variant unless a first-page value is given - so enabling the option
    never silently blanks half the document.
    """
    def build(all_text, odd, even, first):
        all_text = _blank_to_none(all_text)
        odd = _blank_to_none(odd)
        even = _blank_to_none(even)
        first = _blank_to_none(first)
        spec = {"all": all_text, "odd": odd, "even": even, "first": first}
        if all_text is None and (odd is not None or even is not None):
            spec["all"] = odd if odd is not None else even
        return spec

    return {
        "header": build(header_text, header_odd, header_even, header_first),
        "footer": build(footer_text, footer_odd, footer_even, footer_first),
    }


# ---------------------------------------------------------------------------
# PDF geometry
# ---------------------------------------------------------------------------

def page_margin(page, which: str):
    """The top or bottom margin of ``page``, or ``None`` when it cannot be read.

    A PDF does not really have margins - they survive only as the coordinates
    Word happened to lay text out at - so this is best-effort. The previous code
    read ``page.margins`` inside a bare ``except`` and then used
    ``min(depth, 45)`` on the result, which capped the depth back to 45 even
    when the margin *was* available. On the installed PyMuPDF (1.24.x)
    ``Page.margins`` does not exist at all, so every document silently fell back
    to the fixed band and furniture sitting outside it was clipped: a 16-page A4
    lab report with its header at y=35.9-49.2 lost the bottom 4.2pt, and its
    footer at y=793.3-806.6 lost the top 3.6pt, because the nominal footer band
    starts at y=796.9.

    The band is therefore derived from whichever source answers, and membership
    is decided by ``zone_spans`` with a tolerance rather than by the band alone.
    """
    sources = []
    margins = getattr(page, "margins", None)
    if margins is not None:
        sources.append(getattr(margins, "top" if which == "header" else "bottom", None))

    rect = getattr(page, "rect", None)
    if rect is not None:
        sources.append(rect.y1 if which == "footer" else None)

    for value in sources:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if MIN_BAND <= value <= MAX_BAND:
            return value
    return None


def band_rect(page, which: str):
    """The strip of the page reserved for a header or footer.

    A nominal 45pt band, widened to the page's own margin when one can be read.
    It is a *search* region, not a boundary: ``zone_spans`` decides membership
    from a span's centre with ``CLIP_TOLERANCE`` of slack, so furniture that
    straddles the nominal line is still found and still replaceable.
    """
    width = page.rect.width
    height = page.rect.height
    depth = page_margin(page, which) or DEFAULT_BAND
    half = height / 2.0

    if which == "header":
        return fitz.Rect(EDGE_INSET, EDGE_INSET, width - EDGE_INSET,
                         min(depth, half))
    return fitz.Rect(EDGE_INSET, max(height - depth, half),
                     width - EDGE_INSET, height - EDGE_INSET)


# Real headers often straddle the nominal 45pt line - the reference document's
# runs from y=35.9 to y=49.2. Judging membership by the span's centre and
# redacting its whole box keeps such a header replaceable without widening the
# zone into the body.
CLIP_TOLERANCE = 8.0

# Body text on a page with no top margin starts right at the paper edge. Header
# furniture never does: a template with a 36pt top margin puts the header
# baseline around y=49. Refusing to treat the first 30pt as a header zone is what
# stops an edit from deleting a body line, and erring that way is deliberate -
# a stale header is visible and fixable, deleted body text is not.
NEAR_EDGE = 30.0


def _span_text(span):
    return " ".join((span.get("text") or "").split())


def zone_spans(page, rect, which="header", force_text=None):
    """Text spans belonging to a header/footer band.

    ``force_text`` is the header the editor was showing when the user picked it.
    Spans matching it count as furniture wherever they sit, which is what lets
    the user target a specific header the heuristics would otherwise skip.
    """
    search = fitz.Rect(rect.x0 - 4, rect.y0 - CLIP_TOLERANCE,
                       rect.x1 + 4, rect.y1 + CLIP_TOLERANCE)
    forced = " ".join(force_text.split()) if force_text else None

    spans = []
    for block in page.get_text("dict", clip=search).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = _span_text(span)
                if not text:
                    continue

                if forced is not None:
                    if forced in text or text in forced:
                        spans.append(span)
                    continue

                box = fitz.Rect(span["bbox"])
                baseline = span["origin"][1] if span.get("origin") else box.y1
                if which == "header" and baseline < NEAR_EDGE:
                    continue
                if which == "footer" and baseline > page.rect.height - NEAR_EDGE:
                    continue

                centre_y = (box.y0 + box.y1) / 2
                if rect.y0 - CLIP_TOLERANCE <= centre_y <= rect.y1 + CLIP_TOLERANCE:
                    spans.append(span)
    return spans


# ---------------------------------------------------------------------------
# Reading a band back as left and right sections
# ---------------------------------------------------------------------------

# A gap wider than this is a column break rather than a word space. Word spacing
# in body text runs to about a quarter of the font size; the gap between a
# left-aligned subject and a right-aligned ID in a report header is far wider
# than that. The threshold also scales with the font so a large header does not
# get read as one column.
COLUMN_GAP_MIN = 18.0

# Two spans belong to the same row when their baselines are this close, relative
# to the font size. Keying rows on the exact top of the box instead put the page
# number on its own line: Word exported it at y0=793.5 against the footer's
# 793.3, an eighth of a point apart, which is a baseline rounding difference
# rather than a second row.
ROW_TOLERANCE = 0.6


def band_rows(spans):
    """Spans grouped into rows by baseline proximity, top to bottom."""
    ordered = sorted(
        spans,
        key=lambda s: ((fitz.Rect(s["bbox"]).y0 + fitz.Rect(s["bbox"]).y1) / 2,
                       fitz.Rect(s["bbox"]).x0),
    )
    rows = []
    for span in ordered:
        box = fitz.Rect(span["bbox"])
        centre = (box.y0 + box.y1) / 2
        tolerance = max(2.0, ROW_TOLERANCE * (span.get("size") or 0))

        for row in rows:
            if abs(centre - row["centre"]) <= tolerance:
                row["spans"].append(span)
                row["centre"] = sum(
                    (fitz.Rect(s["bbox"]).y0 + fitz.Rect(s["bbox"]).y1) / 2
                    for s in row["spans"]
                ) / len(row["spans"])
                break
        else:
            rows.append({"centre": centre, "spans": [span]})
    return [row["spans"] for row in rows]


def band_columns(spans):
    """A band's spans grouped into rows, then into columns within each row.

    This is what makes "the left and the right are both in the page" survive a
    round trip. A real report header is two things on one line - the subject on
    the left, the ID on the right - and PyMuPDF reports them as separate spans
    with a wide gap between them. Joining them with a space, as the reader used
    to, collapses the layout: the editor then shows one string, and saving
    rewrites the whole line as a single centred block, so the ID ends up in the
    middle of the page instead of flush right.
    """
    result = []
    for row in band_rows(spans):
        row = sorted(row, key=lambda s: fitz.Rect(s["bbox"]).x0)
        columns = [[row[0]]]
        for previous, span in zip(row, row[1:]):
            gap = fitz.Rect(span["bbox"]).x0 - fitz.Rect(previous["bbox"]).x1
            biggest = max(span.get("size") or 0, previous.get("size") or 0)
            if gap > max(COLUMN_GAP_MIN, 1.2 * biggest):
                columns.append([span])
            else:
                columns[-1].append(span)
        result.append([" ".join(_span_text(s) for s in column) for column in columns])
    return result


def _page_number_field(cell, page_number, page_count):
    """Turn a cell that is only this page's number into a ``{PAGE}`` macro.

    Without this a 16-page document reads as having 16 different footers,
    ``different_odd_even`` comes back True purely because the number changes,
    and a save then freezes page 2's number onto every left-hand page.

    Only an outermost column is considered, because a page number lives in a
    corner. A bare number in the middle of a footer is far more likely to be part
    of the content - a roll number, a year, a version - and turning that into a
    field would silently replace the user's data.
    """
    stripped = cell.strip()
    if not stripped.isdigit() or len(stripped) > 4:
        return cell

    value = int(stripped)
    if page_number is not None and value == page_number:
        return "{PAGE}"
    if page_count and value == page_count and value != (page_number or 0):
        return "{NUMPAGES}"
    return cell


def band_text(page, which="header", page_number=None, page_count=None,
              force_text=None):
    """The band's text as the editor should show it, sections joined by a tab.

    One extraction path, used by the reader, by the "apply to matching text
    only" filter and by the tests, so the three can never disagree about what a
    page's furniture says. Reading used to clip to the raw band while erasing
    searched with ``CLIP_TOLERANCE`` of slack, so a header sitting just outside
    the band was visible in the editor, failed to match when targeted, and was
    then drawn a second time on top of itself.
    """
    rect = band_rect(page, which)
    rows = band_columns(zone_spans(page, rect, which, force_text))
    if not rows:
        return ""

    lines = []
    for columns in rows:
        cells = columns[:]
        if len(cells) > 1:
            # Only the outermost columns can be a page number.
            cells[0] = _page_number_field(cells[0], page_number, page_count)
            cells[-1] = _page_number_field(cells[-1], page_number, page_count)
        if len(cells) == 2:
            lines.append(join_parts(cells[0], cells[1]))
        else:
            lines.append(" ".join(cells))
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------------
# Inheriting the look of the furniture being replaced
# ---------------------------------------------------------------------------

# Base-14 names, indexed by family then weight. PyMuPDF can only write these
# without embedding a font file, so a detected family is mapped onto the closest
# one instead of silently becoming Helvetica.
BASE14_BOLD = {"tiro": "tibo", "helv": "hebo", "cour": "cobo"}
BASE14_ITALIC = {"tiro": "tiit", "helv": "heit", "cour": "coit"}

BASE14_FAMILIES = (
    ("courier", "cour"), ("mono", "cour"),
    ("times", "tiro"), ("serif", "tiro"), ("roman", "tiro"),
    ("cambria", "tiro"), ("georgia", "tiro"), ("garamond", "tiro"),
    ("book", "tiro"), ("minion", "tiro"),
    ("helvetica", "helv"), ("arial", "helv"), ("calibri", "helv"),
    ("segoe", "helv"), ("verdana", "helv"), ("tahoma", "helv"),
)

BASE14_CODES = frozenset(
    list(BASE14_BOLD) + list(BASE14_ITALIC) + ["hebi", "tibi", "cobi"]
) | {code for code in ("tiro", "helv", "cour")}

# The names a browser actually understands, so a detected style can be shown to
# the user and echoed back in the preview instead of a raw PDF font code.
BASE14_DISPLAY = {
    "tiro": "Times New Roman", "tibo": "Times New Roman",
    "tiit": "Times New Roman", "tibi": "Times New Roman",
    "helv": "Helvetica", "hebo": "Helvetica",
    "heit": "Helvetica", "hebi": "Helvetica",
    "cour": "Courier New", "cobo": "Courier New",
    "coit": "Courier New", "cobi": "Courier New",
}


def base14_font(name):
    """Map a font name onto a base-14 code, keeping bold and italic.

    The old mapping tested only for the family, so ``TimesNewRomanPS-BoldMT``
    became ``tiro`` and a bold header came back regular. Weight is part of a
    header's appearance and has to survive the round trip.
    """
    if not name:
        return "helv"
    key = str(name).strip().lower()
    if key in BASE14_CODES:
        return key

    family = "helv"
    for needle, code in BASE14_FAMILIES:
        if needle in key:
            family = code
            break

    if any(word in key for word in ("bold", "black", "heavy", "semibold", "demibold")):
        return BASE14_BOLD[family]
    if any(word in key for word in ("italic", "oblique")):
        return BASE14_ITALIC[family]
    return family


def _span_rgb(span):
    """A span's colour as the float triple ``insert_textbox`` wants."""
    packed = span.get("color")
    if packed is None:
        return None
    try:
        packed = int(packed)
    except (TypeError, ValueError):
        return None
    return (((packed >> 16) & 255) / 255.0,
            ((packed >> 8) & 255) / 255.0,
            (packed & 255) / 255.0)


def band_style(spans):
    """The dominant ``(font, size, colour)`` of the furniture being replaced.

    Weighted by character count rather than taken from the first span, so one
    stray glyph in a different font does not decide the look of the whole band.
    Returns ``(None, None, None)`` when there is no furniture to learn from.
    """
    if not spans:
        return None, None, None

    weights = {}
    for span in spans:
        text = _span_text(span)
        if not text:
            continue
        key = (base14_font(span.get("font")),
               round(float(span.get("size") or 0), 1),
               span.get("color"))
        weights[key] = weights.get(key, 0) + len(text)

    if not weights:
        return None, None, None

    font, size, packed = max(weights.items(), key=lambda item: item[1])[0]
    return font, (size or None), _span_rgb({"color": packed})


def _style_report(spans):
    """The band's look in a shape the editor can display.

    "Match document" is only a useful promise if the user can see what it is
    going to match, so the detected font, weight, size and colour are reported
    back alongside the text rather than being applied invisibly.
    """
    font, size, rgb = band_style(spans)
    if font is None and size is None:
        return None
    return {
        "font": BASE14_DISPLAY.get(font, "Helvetica"),
        "bold": font in ("tibo", "hebo", "cobo"),
        "italic": font in ("tiit", "heit", "coit", "tibi", "hebi", "cobi"),
        "size": size,
        "color": "#%02x%02x%02x" % tuple(round(c * 255) for c in (rgb or (0, 0, 0))),
    }


def text_column(page, which="header", erased_box=None, fallback=None):
    """The horizontal text column a replacement should be aligned to.

    A PDF has no page margins, so the only trustworthy column is the one the
    existing furniture already occupies. Writing to a fixed inset instead put a
    rewritten header 64pt left of the body text and 47pt right of it on an A4
    lab report whose margins sat at x=72 and x=540 - furniture hanging into the
    paper edge, visibly not part of the document.
    """
    width = page.rect.width
    if erased_box is not None and erased_box.width > 1:
        left, right = erased_box.x0, erased_box.x1
    elif fallback:
        left, right = fallback
    else:
        left, right = FALLBACK_INSET, width - FALLBACK_INSET

    left = max(EDGE_INSET, min(float(left), width - MIN_COLUMN))
    right = min(width - EDGE_INSET, max(float(right), left + MIN_COLUMN))
    return left, right


def body_column(doc, sample=4):
    """The body's own text column, sampled from the first few pages.

    Only used for pages that carry no furniture at all, so a first-time header
    lands on the text column instead of an arbitrary inset.
    """
    for index, page in enumerate(doc):
        if index >= sample:
            break
        rect = band_rect(page, "header")
        floor = fitz.Rect(EDGE_INSET, rect.y1 + CLIP_TOLERANCE,
                          page.rect.width - EDGE_INSET,
                          band_rect(page, "footer").y0 - CLIP_TOLERANCE)
        left, right = None, None
        for block in page.get_text("dict", clip=floor).get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if not _span_text(span):
                        continue
                    box = fitz.Rect(span["bbox"])
                    left = box.x0 if left is None else min(left, box.x0)
                    right = box.x1 if right is None else max(right, box.x1)
        if left is not None and right - left >= MIN_COLUMN:
            return left, right
    return None


def clear_zone_text(page, rect, which="header", force_text=None):
    """Erase only the text that already occupies a band.

    A full-band white rectangle is what used to blank body content; redacting
    each span's own box keeps everything outside those boxes - including
    images, rules and body text - exactly as it was.
    """
    try:
        spans = zone_spans(page, rect, which, force_text)
        if not spans:
            return 0

        for span in spans:
            page.add_redact_annot(fitz.Rect(span["bbox"]), fill=(1, 1, 1))

        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
        return len(spans)
    except Exception as e:
        logger.warning("Could not clear existing text from a header/footer band: %s", e)
        return 0


def _written_lines(page, clip):
    """How many lines of text ended up inside ``clip``."""
    total = 0
    for block in page.get_text("dict", clip=clip).get("blocks", []):
        total += len(block.get("lines", []))
    return total


def _fits(page_rect, body, inner, fontsize, fontname, align):
    """The largest size at or below ``fontsize`` that lays ``body`` out in ``inner``.

    ``insert_textbox`` never reports "this does not fit" the way the old code
    assumed. Given a narrow box it silently *wraps* onto a second line and
    reports success, so shrinking never triggered and the overflow line landed
    below the band, where it was clipped - a header of
    "Practical2_AWDF_24DCS140.pdf" came back missing its "p". The line count is
    therefore checked explicitly: furniture wraps only when the author asked it
    to, with a newline.

    Asking the question on a scratch page is what lets the caller leave the
    existing furniture alone instead of erasing it and only then discovering
    there was no room for the replacement.
    """
    allowed = max(1, len(body.split("\n")))
    size = float(fontsize)
    while size >= 6.0:
        try:
            probe = fitz.open()
            page = probe.new_page(width=page_rect.width, height=page_rect.height)
            written = page.insert_textbox(
                inner, body, fontsize=size, fontname=fontname, align=align,
            )
            lines = _written_lines(page, inner) if written >= 0 else 0
            probe.close()
            if written >= 0 and 0 < lines <= allowed:
                return size
        except Exception:
            return size
        size -= 1.0
    return None


def _zone_box(page, rect, erased_box, which="header", fallback_column=None):
    """The box a replacement header/footer is laid out in.

    ``insert_textbox`` writes downwards from the top of its rectangle, so the top
    edge is what decides where the text lands, and it has to sit on the old
    furniture. The footer branch used to set the top to ``old_top - ZONE_GROWTH``,
    growing the box *upwards* to make room; that moved the rewritten footer 18pt
    above where it had been, which put it outside the band entirely - so the
    edit reported success and the footer then read as absent.

    Growth is therefore added to the far edge, and the near edge stays put on both
    sides. Horizontally the box is the text column the document already uses.
    """
    left, right = text_column(page, which, erased_box, fallback_column)
    height = page.rect.height

    if which == "header":
        top = (erased_box.y0 if erased_box is not None else rect.y0) - 2
        floor = max(rect.y1, erased_box.y1 if erased_box is not None else rect.y1)
        return fitz.Rect(left, top, right, min(floor + ZONE_GROWTH, height - EDGE_INSET))

    top = (erased_box.y0 if erased_box is not None else rect.y0) - 2
    bottom = (erased_box.y1 if erased_box is not None else rect.y1) + ZONE_GROWTH
    return fitz.Rect(left, top, right, min(bottom, height - EDGE_INSET))


# How far a replacement may extend past the furniture it replaces. Enough for a
# second or third line, small enough to stay well clear of the body: the AWDF and
# OSD reports both start their body around y=76.
ZONE_GROWTH = 18.0


# Base-14 PDF fonts carry WinAnsi, and PyMuPDF maps anything outside it to '?'
# instead of raising. Rewriting the footer of a report whose text read
# "DEPSTAR (CSE) - 5CSE - 2(C)" with an en dash produced
# "DEPSTAR (CSE) ? 5CSE - 2(C)": the save returned success and silently
# corrupted the text, one '?' per occurrence on every page. These substitutions
# keep the meaning and stay inside the font.
PDF_SAFE_TEXT = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "―": "-",
    "—": "--", "―": "--",
    "‘": "'", "’": "'", "‚": ",", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "…": "...",
    "•": "-", "‣": "-", "⁃": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
    "": "", "‌": "", "‍": "", "﻿": "",
    "′": "'", "″": '"',
    "­": "",
}

# Above Latin-1 nothing can be assumed renderable in a base-14 font.
_PDF_SAFE_LIMIT = 0xFF


def pdf_safe_text(text):
    """``text`` with typographic characters folded into the base-14 repertoire.

    Anything still outside Latin-1 after this cannot be drawn in a base-14 font.
    PyMuPDF would emit '?' for it, so it is dropped and logged: losing a glyph is
    bad, but silently writing a page full of question marks is worse, and the log
    says exactly what was dropped.
    """
    if not text:
        return text

    out = []
    dropped = set()
    for char in text:
        if ord(char) <= _PDF_SAFE_LIMIT:
            out.append(char)
            continue
        replacement = PDF_SAFE_TEXT.get(char)
        if replacement is None:
            dropped.add(char)
            continue
        out.append(replacement)

    if dropped:
        logger.warning(
            "Header/footer text has %d character(s) a base-14 PDF font cannot "
            "show and they were dropped: %s",
            len(dropped), " ".join(f"U+{ord(c):04X}" for c in sorted(dropped)),
        )
    return "".join(out)


def _zone_sections(text, page_number, page_count, title, filename):
    """The rendered left and right sections of one variant's text."""
    left_raw, right_raw = split_parts(text)
    return (render(pdf_safe_text(left_raw), page_number, page_count, title, filename),
            render(pdf_safe_text(right_raw), page_number, page_count, title, filename))


def _zone_plan(sections, inner, alignment, fontname="helv", fontsize=10.0):
    """Which box and alignment each section of a band is written into.

    The right-hand section is measured rather than given half the column. A
    midpoint split leaves the left section only half the text width, which on a
    real report header is narrower than the subject line itself: a 302pt subject
    in a 289pt box wraps onto a second row and pushes the header down into the
    body. Measuring the right section and giving the left everything else keeps
    both on one line, which is what a tab stop does in Word.

    Falls back to the midpoint when the right section is too wide for that to
    leave the left a usable column.
    """
    left = sections.get("left", "")
    right = sections.get("right", "")

    if right:
        try:
            reserved = fitz.get_text_length(right, fontname=fontname,
                                            fontsize=fontsize)
        except Exception:
            reserved = inner.width / 2
        gap = max(6.0, float(fontsize))
        split = inner.x1 - reserved - gap

        if split > inner.x0 + inner.width * 0.35:
            return (("left", fitz.Rect(inner.x0, inner.y0, split, inner.y1),
                     fitz.TEXT_ALIGN_LEFT),
                    ("right", fitz.Rect(split + gap, inner.y0, inner.x1, inner.y1),
                     fitz.TEXT_ALIGN_RIGHT))

        middle = inner.x0 + inner.width / 2
        return (("left", fitz.Rect(inner.x0, inner.y0, middle, inner.y1),
                 fitz.TEXT_ALIGN_LEFT),
                ("right", fitz.Rect(middle, inner.y0, inner.x1, inner.y1),
                 fitz.TEXT_ALIGN_RIGHT))

    align = PDF_ALIGNMENTS.get((alignment or "center").lower(), fitz.TEXT_ALIGN_CENTER)
    return (("left", inner, align),)


def write_pdf_zone(page, rect, text, page_number, page_count, fontname,
                   fontsize, alignment, color=DEFAULT_COLOR, erased_box=None,
                   title="", filename="", which="header", fallback_column=None):
    """Write one header/footer band, with this page's field values resolved.

    When the old text was found it is replaced in its own vertical position, so
    an edited header stays on the same line instead of jumping to the top.

    Text containing a tab is written as two sections: the part before the tab
    flush against the left text margin and the part after it flush against the
    right one, which is what "subject on the left, ID on the right" means on the
    page.
    """
    if text is None:
        return False

    sections = dict(zip(("left", "right"),
                        _zone_sections(text, page_number, page_count, title, filename)))
    inner = _zone_box(page, rect, erased_box, which, fallback_column)
    plan = _zone_plan(sections, inner, alignment, fontname, fontsize)
    if not any(sections.get(name, "").strip() for name, _, _ in plan):
        return False

    written = True
    for name, box, align in plan:
        body = sections.get(name, "")
        if not body.strip():
            continue
        written &= _write_pdf_text(page, box, body, page.rect, fontname,
                                   fontsize, color, align)
    return bool(written)


def zone_fits(page, rect, text, erased_box, which, alignment, fontname, fontsize,
              title="", filename="", page_number=1, page_count=1,
              fallback_column=None):
    """Whether every section of a band can be laid out, trying smaller sizes.

    ``insert_textbox`` writes nothing and returns a negative height when text
    does not fit. Asking that question before erasing the old furniture is what
    keeps a too-long header from being wiped and replaced with nothing.
    """
    sections = dict(zip(("left", "right"),
                        _zone_sections(text, page_number, page_count, title, filename)))
    inner = _zone_box(page, rect, erased_box, which, fallback_column)
    for name, box, align in _zone_plan(sections, inner, alignment, fontname, fontsize):
        body = sections.get(name, "")
        if not body.strip():
            continue
        if _fits(page.rect, body, box, fontsize, fontname, align) is None:
            return False
    return True


def _write_pdf_text(page, box, body, page_rect, fontname, fontsize, color, align):
    """Lay one aligned section out in ``box``, shrinking rather than dropping it."""
    size = _fits(page_rect, body, box, fontsize, fontname, align)
    if size is None:
        return False
    return page.insert_textbox(
        box, body, fontsize=size, fontname=fontname, color=color,
        align=align, overlay=True,
    ) >= 0


def _union_box(spans):
    box = fitz.Rect(spans[0]["bbox"])
    for span in spans[1:]:
        box |= fitz.Rect(span["bbox"])
    return box


def apply_pdf_headers_footers(doc, spec: dict, fontname=None, fontsize=None,
                              header_align="center", footer_align="center",
                              title="", filename="", targets=None, color=None):
    """Apply the header/footer spec to every page of an open PDF.

    ``fontname``/``fontsize``/``color`` left as ``None`` mean "keep whatever the
    page already looks like". That is the default from the editor, because
    rewriting a black 12pt bold Times header as 10pt grey Helvetica is a visible
    downgrade the user did not ask for; the change they asked for was to the
    words.
    """
    targets = targets or {}
    page_count = doc.page_count
    fallback_column = body_column(doc)
    touched = {"header": 0, "footer": 0}
    failed = []

    for index, page in enumerate(doc):
        page_number = index + 1
        for which, rect in (("header", band_rect(page, "header")),
                            ("footer", band_rect(page, "footer"))):
            wanted = text_for_page(spec.get(which), page_number)
            if wanted is None:
                continue

            # Resolve the fields *before* touching the page. Erasing first and
            # writing afterwards loses the header entirely whenever the requested
            # text turns out to be empty - which is exactly what an emptied text
            # box, or a page whose variant was never filled in, produced.
            sections = _zone_sections(wanted, page_number, page_count, title, filename)
            if not any(part.strip() for part in sections):
                continue

            spans = zone_spans(page, rect, which, targets.get(which))
            erased_box = _union_box(spans) if spans else None

            inherited_font, inherited_size, inherited_color = band_style(spans)
            use_font = fontname or inherited_font or "helv"
            use_size = float(fontsize or inherited_size or DEFAULT_FONT_SIZE)
            if color is not None:
                use_color = color
            else:
                use_color = inherited_color or DEFAULT_COLOR

            align_name = header_align if which == "header" else footer_align

            # Prove the replacement fits *before* erasing the old furniture.
            # Otherwise a header too long for its band is wiped and then nothing
            # is drawn in its place, which is how a header disappears entirely.
            if not zone_fits(page, rect, wanted, erased_box, which, align_name,
                             use_font, use_size, title=title, filename=filename,
                             page_number=page_number, page_count=page_count,
                             fallback_column=fallback_column):
                failed.append((which, page_number))
                continue

            if spans:
                clear_zone_text(page, rect, which, targets.get(which))
            ok = write_pdf_zone(
                page, rect, wanted, page_number, page_count, use_font, use_size,
                align_name, color=use_color, erased_box=erased_box, title=title,
                filename=filename, which=which, fallback_column=fallback_column,
            )
            if ok:
                touched[which] += 1
            else:
                failed.append((which, page_number))

    if failed:
        # Reported rather than swallowed: a header that is too long for its band
        # is a problem the user has to be told about, not a silent no-op.
        logger.warning(
            "Header/footer text did not fit its band on %d page(s): %s",
            len(failed), sorted({f"{w} p{n}" for w, n in failed})[:8],
        )
        touched["failed"] = [
            {"zone": w, "page": n} for w, n in failed[:20]
        ]
        touched["failure_count"] = len(failed)
    return touched


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _field_char(kind):
    element = OxmlElement("w:fldChar")
    element.set(qn("w:fldCharType"), kind)
    return element


def _add_field_run(paragraph, name, placeholder=""):
    """Append a real Word field (``{ PAGE }`` and friends) to a paragraph.

    Word and LibreOffice recalculate it on open; the cached result between the
    field separator and end keeps something sensible on screen before that
    happens, so a header never reads as blank in a preview.
    """
    paragraph.add_run()._r.append(_field_char("begin"))

    instr_run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {name} "
    instr_run._r.append(instr)

    paragraph.add_run()._r.append(_field_char("separate"))
    result_run = paragraph.add_run(placeholder)
    paragraph.add_run()._r.append(_field_char("end"))
    return result_run


def _set_right_tab(paragraph, position_emu):
    """Give a header/footer paragraph a right-aligned tab stop.

    This is how Word expresses "left section here, right section there": text
    before the tab is left at the margin and text after it is pushed flush right.
    """
    p_pr = paragraph._p.get_or_add_pPr()
    for existing in p_pr.findall(qn("w:tabs")):
        p_pr.remove(existing)

    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:pos"), str(int(position_emu)))
    tabs.append(tab)
    p_pr.append(tabs)


def _add_tab_run(paragraph):
    run = paragraph.add_run()
    run._r.append(OxmlElement("w:tab"))
    return run


def write_docx_paragraph(paragraph, text, font_name=None, font_size=None,
                         alignment=None, title=""):
    """Replace a header/footer paragraph's content, honouring field macros.

    A tab in ``text`` splits it into a left and a right section. The paragraph
    then carries a right-aligned tab stop, so the subject stays at the left
    margin and the ID sits flush right - the layout Word produces when a student
    types a tab between the two.

    The font is applied to every run, not only to the field runs. Applying it
    only inside the field branch meant the literal text of a header came out in
    whatever the document default happened to be, so choosing Times New Roman
    12pt in the editor changed the page number and left the words alone.
    """
    for run in list(paragraph.runs):
        run._r.getparent().remove(run._r)

    if alignment and alignment.lower() in ALIGNMENTS:
        paragraph.alignment = ALIGNMENTS[alignment.lower()]

    left_raw, right_raw = split_parts(text)

    def style(run):
        if font_name:
            run.font.name = font_name
        if font_size:
            run.font.size = Pt(font_size)

    def emit(chunk):
        for kind, value in parse_segments(chunk):
            if kind == "text":
                if value:
                    style(paragraph.add_run(value))
                continue
            style(_add_field_run(paragraph, value,
                                 placeholder=field_value(value, 1, 1, title)))

    if has_split(text):
        emit(left_raw)
        _add_tab_run(paragraph)
        emit(right_raw)
        _set_right_tab(paragraph, _right_margin_emu(paragraph))
    else:
        emit(text)


def part_style(part):
    """The ``(font_name, size)`` of a header/footer part's existing text.

    Lets "match the document" mean the same thing for DOCX as it does for PDF:
    keep the look the part already had instead of imposing Helvetica 10pt on a
    header that was Times New Roman 12pt bold.
    """
    try:
        for paragraph in part.paragraphs:
            for run in paragraph.runs:
                if not run.text.strip():
                    continue
                return (run.font.name or None,
                        run.font.size.pt if run.font.size else None)
    except Exception:
        pass
    return None, None


def _right_margin_emu(paragraph):
    """Position of the right text margin, for the right-aligned tab stop.

    Taken from the section the header/footer belongs to so the right section
    lines up with the body text rather than with the paper edge.
    """
    try:
        # python-docx exposes the owning section through the header/footer part.
        document_part = paragraph.part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/document"
        )
        for section in document_part.document.sections:
            width = section.page_width - section.left_margin - section.right_margin
            if width:
                return int(width)
    except Exception:
        pass

    # Fall back to US Letter with 1in margins, which is what most of these
    # reports use; a tab stop a little short still reads correctly.
    return int(6.5 * 914400)


def _single_paragraph(container):
    """A header/footer part reduced to exactly one empty paragraph.

    Clearing text but leaving the paragraphs behind leaves blank lines that push
    the *body* down - which is another way a header change silently reflows a
    document.
    """
    paragraphs = list(container.paragraphs)
    if not paragraphs:
        return container.add_paragraph()
    keep = paragraphs[0]
    for extra in paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    for run in list(keep.runs):
        run._r.getparent().remove(run._r)
    return keep


def _part_text(part):
    return "\n".join(p.text for p in part.paragraphs).strip()


def _all_parts(section, which):
    if which == "header":
        return [section.header, section.even_page_header, section.first_page_header]
    return [section.footer, section.even_page_footer, section.first_page_footer]


EMPTY_SPEC = {"all": None, "odd": None, "even": None, "first": None}


def restrict_docx_spec(doc, spec, target_header=None, target_footer=None):
    """Blank a zone's spec when no section currently carries the target text.

    This preserves the editor's "apply to the header I clicked" behaviour: if the
    document's headers all differ from what the editor showed, nothing is written.
    """
    result = {which: dict(variants or EMPTY_SPEC) for which, variants in spec.items()}

    for which, target in (("header", target_header), ("footer", target_footer)):
        if target is None:
            continue
        wanted = " ".join(target.split())
        matched = any(
            " ".join(_part_text(part).split()) == wanted
            for section in doc.sections
            for part in _all_parts(section, which)
        )
        if not matched:
            result[which] = dict(EMPTY_SPEC)

    return result


def apply_docx_headers_footers(doc, spec: dict, font_name=None, font_size=None,
                               header_align="center", footer_align="center",
                               title=""):
    """Apply the header/footer spec to every section of a DOCX."""
    touched = {"header": 0, "footer": 0}

    for section in doc.sections:
        header_spec = spec.get("header") or {}
        footer_spec = spec.get("footer") or {}

        wants_odd_even = any(
            (variants.get("odd") is not None or variants.get("even") is not None)
            for variants in (header_spec, footer_spec)
        )
        wants_first = any(
            variants.get("first") is not None
            for variants in (header_spec, footer_spec)
        )

        if wants_odd_even:
            _enable_odd_even_headers(doc)
            section.different_first_page_header_footer = wants_first
        elif wants_first:
            section.different_first_page_header_footer = True
        else:
            # Switching a previously odd/even document back to "all pages" must
            # switch the setting off too, or Word keeps using the stale even part.
            _disable_odd_even_headers(doc)
            section.different_first_page_header_footer = False

        for which, align in (("header", header_align), ("footer", footer_align)):
            variants = spec.get(which) or {}
            if not variants or all(v is None for v in variants.values()):
                continue

            for variant, part in _docx_parts(section, which, variants):
                wanted = _docx_variant_text(variants, variant)
                paragraph = _single_paragraph(part)
                if wanted is None:
                    # This variant is not part of the new header/footer, but an
                    # earlier edit may have left text in the part. Leaving it
                    # behind is how a "side-specific" header survived being
                    # replaced with a single line for every page.
                    if _clear_paragraph(paragraph):
                        touched[which] += 1
                    continue

                # "Match the document" means keep the part's own font unless the
                # user actually chose one. Read before the paragraph is emptied,
                # because afterwards there is nothing left to read it from.
                if font_name is None or font_size is None:
                    existing_font, existing_size = part_style(part)
                    run_font = font_name or existing_font
                    run_size = font_size or existing_size
                else:
                    run_font, run_size = font_name, font_size

                write_docx_paragraph(paragraph, wanted, run_font, run_size,
                                     align, title)
                touched[which] += 1

    return touched


def _clear_paragraph(paragraph) -> bool:
    """Empty a header/footer paragraph, leaving one empty run behind.

    Word wants at least one paragraph in a header part, so the runs are emptied
    rather than the paragraph removed.
    """
    runs = paragraph.runs
    if not runs:
        if not paragraph.text.strip():
            return False
        paragraph.add_run("")
        return True
    for run in runs[1:]:
        run._r.getparent().remove(run._r)
    runs[0].text = ""
    # A field code left behind would re-render on open.
    for field in paragraph._p.findall(qn("w:fldSimple")):
        paragraph._p.remove(field)
    for instr in paragraph._p.iter(qn("w:instrText")):
        parent = instr.getparent()
        if parent is not None:
            parent.text = ""
    return True


def _disable_odd_even_headers(doc):
    """Turn Word's "different odd & even pages" document setting back off."""
    settings = doc.settings.element
    element = settings.find(qn("w:evenAndOddHeaders"))
    if element is not None:
        settings.remove(element)


def _docx_parts(section, which, variants):
    """The header/footer parts a section needs written, in a stable order."""
    if which == "header":
        first, odd, even = section.first_page_header, section.header, section.even_page_header
    else:
        first, odd, even = section.first_page_footer, section.footer, section.even_page_footer

    side_specific = variants.get("odd") is not None or variants.get("even") is not None
    if not side_specific:
        # No odd/even split: writing the default part alone would leave the
        # document-wide odd/even setting pointing at stale text, so clear the
        # even (and first) parts when they exist.
        yield "all", odd
        yield "even", even
        yield "first", first
        return

    yield "odd", odd
    yield "even", even
    if variants.get("first") is not None:
        yield "first", first


def _docx_variant_text(variants, variant):
    """Which text belongs in a part, falling back the way Word does."""
    if variant == "even":
        return variants.get("even")
    if variant == "first":
        return variants.get("first")
    if variant == "odd":
        return variants.get("odd")
    # The blanket part: prefer an explicit value, else the odd side's.
    return variants.get("all", variants.get("odd"))


def _enable_odd_even_headers(doc):
    """Turn on Word's "different odd & even pages" document setting."""
    settings = doc.settings.element
    if settings.find(qn("w:evenAndOddHeaders")) is None:
        settings.append(OxmlElement("w:evenAndOddHeaders"))


def read_docx_headers_footers(doc) -> dict:
    """Report the header/footer variants a DOCX already defines.

    Odd/even are reported separately so the editor can prefill both sides instead
    of showing one and silently overwriting the other.
    """
    result = {
        "headers": [], "footers": [],
        "header_odd": None, "header_even": None, "header_first": None,
        "footer_odd": None, "footer_even": None, "footer_first": None,
        "different_odd_even": False, "different_first": False,
    }
    try:
        seen_h = set()
        seen_f = set()

        def part_text(part):
            return _part_text(part)

        for section in doc.sections:
            if section.different_first_page_header_footer:
                result["different_first"] = True
            odd_h = part_text(section.header)
            even_h = part_text(section.even_page_header)
            if even_h and even_h != odd_h:
                result["different_odd_even"] = True
            if odd_h and odd_h not in seen_h:
                seen_h.add(odd_h)
                result["headers"].append(odd_h)
            if even_h and even_h not in seen_h:
                seen_h.add(even_h)
                result["headers"].append(even_h)

            odd_f = part_text(section.footer)
            even_f = part_text(section.even_page_footer)
            if even_f and even_f != odd_f:
                result["different_odd_even"] = True
            if odd_f and odd_f not in seen_f:
                seen_f.add(odd_f)
                result["footers"].append(odd_f)
            if even_f and even_f not in seen_f:
                seen_f.add(even_f)
                result["footers"].append(even_f)

            if result["header_odd"] is None and odd_h:
                result["header_odd"] = odd_h
            if result["header_even"] is None and even_h:
                result["header_even"] = even_h
            if result["header_first"] is None and part_text(section.first_page_header):
                result["header_first"] = part_text(section.first_page_header)
            if result["footer_odd"] is None and odd_f:
                result["footer_odd"] = odd_f
            if result["footer_even"] is None and even_f:
                result["footer_even"] = even_f
            if result["footer_first"] is None and part_text(section.first_page_footer):
                result["footer_first"] = part_text(section.first_page_footer)

        return result
    except Exception as e:
        logger.error("Error reading DOCX headers/footers: %s", e)
        return result


def read_pdf_headers_footers(doc) -> dict:
    """Report the header/footer bands of an open PDF, split by page side.

    Every page is read through ``band_text``, so a two-column header comes back
    tab-separated and a page number comes back as a ``{PAGE}`` macro. That is
    what lets the editor show the left and right sections separately and re-save
    them without flattening the layout.

    It is also what stops a false positive on ``different_odd_even``. Comparing
    raw band text made a document with one footer and a page number look like it
    had different left and right footers, purely because "1" and "2" differ; the
    editor then opened in side-specific mode and a save wrote page 2's literal
    number onto every even page in the document.
    """
    result = {
        "headers": [], "footers": [],
        "header_odd": None, "header_even": None, "header_first": None,
        "footer_odd": None, "footer_even": None, "footer_first": None,
        "different_odd_even": False, "different_first": False,
        "header_style": None, "footer_style": None,
    }
    try:
        seen = {"header": set(), "footer": set()}
        styles = {"header": None, "footer": None}
        longest_seen = {"header": 0, "footer": 0}
        page_count = doc.page_count

        for index, page in enumerate(doc):
            page_number = index + 1
            for which in ("header", "footer"):
                rect = band_rect(page, which)
                spans = zone_spans(page, rect, which)
                text = band_text(page, which, page_number, page_count)
                if not text:
                    continue

                if text not in seen[which]:
                    seen[which].add(text)
                    result["headers" if which == "header" else "footers"].append(text)

                # Whichever band carries the most text is the one most worth
                # keeping, so its look is what "Match document" reports on.
                longest = max((len(_span_text(s)) for s in spans), default=0)
                if longest > longest_seen[which]:
                    longest_seen[which] = longest
                    styles[which] = _style_report(spans)

                slot = f"{which}_{'odd' if page_number % 2 else 'even'}"
                if result[slot] is None:
                    result[slot] = text
                if page_number == 1 and result[f"{which}_first"] is None:
                    result[f"{which}_first"] = text

        result["header_style"] = styles["header"]
        result["footer_style"] = styles["footer"]

        result["different_odd_even"] = (
            bool(result["header_even"] and result["header_odd"]
                 and result["header_odd"] != result["header_even"])
            or bool(result["footer_even"] and result["footer_odd"]
                    and result["footer_odd"] != result["footer_even"])
        )
        result["different_first"] = bool(
            result["header_first"] and result["header_first"] != result["header_odd"]
        ) or bool(
            result["footer_first"] and result["footer_first"] != result["footer_odd"]
        )
        return result
    except Exception as e:
        logger.error("Error reading PDF headers/footers: %s", e)
        return result