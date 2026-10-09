"""Slide template engine for PPTX generation.

The previous PPTX builder packed five paragraphs into a slide and used the first
one as the title, which produced nonsense decks: half a sentence became a
heading, table rows became slide titles, and every slide used PowerPoint's blank
layout so nothing was aligned or branded.

This module turns a parsed document into a real outline first, then renders that
outline through named, reusable templates. Three things make the output usable:

* **Outline** - document headings and table structure decide slide boundaries
  and titles. A document with real headings gets one slide per section; a
  document with none (the common case for the lab reports this app receives) has
  structure inferred from its tables, because "Objective | ...", "Problem
  Statement | ..." label columns are effectively headings in everything but name.
* **Templates** - each slide is rendered by a template that owns its geometry and
  styling, so title / section / bullets / table / image slides all look
  deliberate instead of being the same textbox.
* **Overflow control** - bullet lists are capped per slide and long tables spill
  across slides, and text is shrunk to fit its frame, so nothing runs off the
  bottom of a slide.
"""

import logging
import re

from pptx import Presentation

logger = logging.getLogger(__name__)

# 16:9 at 13.333in x 7.5in
SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5

# A bullet list longer than this becomes a new slide instead of overflowing.
MAX_BULLETS_PER_SLIDE = 7
# Headings at or below this level open their own slide.
MAX_HEADING_DEPTH = 3
# Rows a single table slide can show before the rest spill over.
MAX_TABLE_ROWS = 14
# Longest cell text rendered inside a table cell.
MAX_CELL_CHARS = 220

_LABEL_MAX_WORDS = 6
_WORD_RE = re.compile(r"[\w'\-]+", re.UNICODE)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _clean(text) -> str:
    if not text:
        return ""
    # Collapse the blank-line padding DOCX paragraphs carry, and normalise the
    # non-breaking / zero-width spaces Word likes to insert.
    text = text.replace("\xa0", " ").replace("\u200b", "")
    # Adjacent dashes separated by a space come out of a line-wrapped DOCX cell
    # and rendered as `— — {proj.demo}` mid-line. The lookbehind keeps this away
    # from leading indentation and from file-tree glyphs.
    text = re.sub(r"(?<=\S)\s+([—–])\s+", r" \1 ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _clean_code_line(line: str) -> str:
    """Normalise a code line without destroying its indentation."""
    out = (line or "").replace("\xa0", " ").replace("\u200b", "")
    out = re.sub(r"(?<=\S)[ \t]+([—–])[ \t]+", r" \1 ", out)
    return out.rstrip()


def _truncate(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text or ""
    clipped = text[: limit - 1].rsplit(" ", 1)[0]
    return f"{clipped.rstrip(' .,;:')}..."


# A single bullet longer than this is unreadable at any font size that fits a
# slide, so it gets broken into sentence-sized pieces instead.
MAX_BULLET_CHARS = 150
# Consecutive code-ish lines are grouped into one monospace block.
MAX_CODE_LINES_PER_SLIDE = 12

# A short prose line right before a snippet reads as that snippet's label
# ("Server.js:", "ConnectDB()"). Longest such line still treated as a label.
SHORT_CAPTION_CHARS = 60
MAX_CODE_CHARS_PER_LINE = 96

# Box-drawing characters, file trees, shell prompts and common code tokens. These
# used to be dumped into the bullet list as prose, so a slide ended up reading
# "student-portfolio/ - src/ - App.jsx" and the indentation that gave the tree
# its structure was meaningless once every line became its own bullet.
_TREE_CHARS = "\u2500\u2502\u251c\u2514\u2502\u251c\u2514\u2500"
_CODE_TOKENS = re.compile(
    r"(?:^|\s)(?:npm|npx|yarn|cd|git|mkdir|pip|docker|node|python|curl|sudo|"
    r"const|let|var|function|return|import|export|def|class|public|private|"
    r"if|else|for|while|async|await|require|console\.log|SELECT|INSERT|"
    r"=>|\{\}|\(\)|;\s*$)",
    re.IGNORECASE,
)
_CODE_EXTENSIONS = re.compile(
    r"\.(?:js|jsx|ts|tsx|py|json|html|css|java|c|cpp|go|rb|php|sql|sh|yml|yaml|md)\b",
    re.IGNORECASE,
)


def _native_image_size(stream):
    """Return the image's true pixel ``(width, height)``, or ``None``.

    ``python-pptx`` hard-requires Pillow, so this needs no new dependency.
    """
    try:
        from PIL import Image
        stream.seek(0)
        with Image.open(stream) as im:
            size = im.size
        stream.seek(0)
        if size and size[0] > 0 and size[1] > 0:
            return size
    except Exception:
        pass
    return None


def _add_picture_fit(slide, stream, left, top, max_w, max_h):
    """Place a picture inside a box, scaled to fit and centred.

    ``add_picture(height=...)`` alone keeps the native aspect ratio, so a wide
    screenshot placed on a bullets slide came out 28 inches wide on a 13.3 inch
    slide and ran far off the right edge. The image is scaled to fit and then
    centred in the box.

    ``max_w``/``max_h`` are inches, but ``add_picture`` and ``Picture.width``
    work in EMU. The fit is therefore computed entirely in inches and converted
    once, at placement: mixing the two units scaled every image down by ~10^6
    and left a 3x4 EMU dot on the slide, i.e. no visible image at all.
    """
    from pptx.util import Inches

    # `add_picture` consumes the stream, so rewind before every use - including
    # the throwaway probe used to read the image's native aspect ratio.
    def _rewind():
        try:
            if hasattr(stream, "seek"):
                stream.seek(0)
        except Exception:
            pass

    native_px = _native_image_size(stream)

    # Aspect ratio from the real pixels when we can get them.
    aspect = (native_px[0] / native_px[1]) if native_px else None

    if not aspect:
        # Fall back to python-pptx: give it ONE dimension so it reports the
        # image's own proportions instead of the box we asked for.
        try:
            _rewind()
            probe = Presentation()
            pic = probe.slides.add_slide(probe.slide_layouts[6]).shapes.add_picture(
                stream, 0, 0, height=Inches(1))
            if pic.width and pic.height:
                aspect = pic.width / pic.height
        except Exception:
            aspect = None

    _rewind()
    if not aspect or aspect <= 0:
        return slide.shapes.add_picture(stream, Inches(left), Inches(top),
                                        height=Inches(max_h))

    # Contain-fit, in inches.
    width_in = max_h * aspect
    height_in = max_h
    if width_in > max_w:
        width_in = max_w
        height_in = max_w / aspect

    # Never upscale a small image beyond its own resolution.
    if native_px:
        max_w_in = native_px[0] / 96.0
        max_h_in = native_px[1] / 96.0
        if width_in > max_w_in and height_in > max_h_in:
            shrink = min(max_w_in / width_in, max_h_in / height_in)
            width_in *= shrink
            height_in *= shrink

    _rewind()
    return slide.shapes.add_picture(
        stream, Inches(left + max(0.0, (max_w - width_in) / 2)),
        Inches(top + max(0.0, (max_h - height_in) / 2)),
        width=Inches(width_in), height=Inches(height_in))


def _looks_like_code(line: str) -> bool:
    """True for a line that is really code, a shell command, or a file tree.

    These belong in a monospace block with their indentation intact, not in the
    bullet list, where each line would otherwise be bulleted separately and the
    structure of a file tree or a snippet would be destroyed.

    The bar is deliberately high. Treating every line containing a `<`, `(` or
    `}` as code split a JSX component into a dozen slides - one for `<header>`,
    one for `</header>`, one for `)` - which is worse than the original problem.
    A line only counts as code if it is substantial (a real command, a file
    name, a tree edge) rather than a lone punctuation fragment.
    """
    text = line.rstrip()
    stripped = text.strip()
    if not stripped:
        return False

    # Tree edges are unambiguous no matter how short the line is.
    if any(ch in text for ch in _TREE_CHARS):
        return True
    if _CODE_EXTENSIONS.search(stripped):
        return True
    if stripped.startswith(("$", ">", "#")):
        return True
    if stripped.startswith(("npm ", "npx ", "yarn ", "cd ", "git ", "pip ", "docker ")):
        return True

    # Symbol-dense lines are code, not prose.
    symbols = sum(1 for ch in stripped if ch in "{}[]()<>=;|")

    # A line that is *only* punctuation - `);`, `}`, `};`, `)` - carries no
    # meaning on its own. Rejecting those keeps stray closers from being
    # promoted, while `<header>` and `return (` are kept so a JSX block stays
    # together in one snippet instead of being split between a code slide and
    # the bullet list.
    if len(re.sub(r"[^\w]", "", stripped)) < 2:
        return False

    if symbols >= 2 and len(stripped) <= 200:
        return True
    if _CODE_TOKENS.search(stripped) and symbols >= 1:
        return True

    # A JSX/JS object literal: `{ id: 1, title: 'E-Commerce ...' }`. A line
    # that opens with a brace is never prose, and the symbol count above misses
    # these because the punctuation is mostly quotes and commas.
    if stripped.startswith("{") and re.search(r"[\w'\"]\s*:\s*[\w'\"{]", stripped):
        return True
    return False


_TREE_EDGE = re.compile(r"(?=[└├┌┐│]{1,2}\s)")


def _split_inline_tree(line: str) -> list:
    """Re-break a file tree that was flattened onto a single line.

    Word processors often collapse a pasted `tree` listing into one paragraph,
    leaving every edge on one run: `└── src/ ├── App.jsx ├── main.jsx`. Shown on
    one line the hierarchy the tree exists to convey is gone, so it is split back
    out at each tree edge.
    """
    if sum(1 for ch in line if ch in _TREE_CHARS) < 2:
        return [line]
    parts = [p for p in _TREE_EDGE.split(line) if p and p.strip()]
    return parts if len(parts) >= 2 else [line]


def _is_punct_only(line: str) -> bool:
    """True for a line with no word characters at all: `}`, `/>`, `));`."""
    return len(re.sub(r"[^\w]", "", line or "")) < 2


_TAG_ONLY = re.compile(r"^</?[A-Za-z][\w.-]*\s*/?>$")


def _is_orphan_code_line(line: str) -> bool:
    """True for a line that is a code fragment with no meaning on its own.

    Covers bare punctuation (`}`, `/>`, `));`) and lone markup tags (`</div>`).
    Left as prose these stranded closing brackets on slides of their own - one
    slide reading just `</div>`.
    """
    text = (line or "").strip()
    return _is_punct_only(text) or bool(_TAG_ONLY.match(text))


def _segment_lines(lines: list) -> list:
    """Group consecutive lines into alternating ('prose'|'code', [lines]) runs.

    A single code-looking line between prose does not earn a slide of its own -
    it is folded back into the prose. Only runs of two or more lines are treated
    as a real snippet, which is what keeps a JSX component together while still
    lifting a genuine multi-line command or file tree out of the bullet list.

    Punctuation-only lines (`}`, `/>`, `));`) carry no meaning alone, so when
    they sit next to a snippet they are absorbed into it. Left as prose they
    stranded closing brackets on slides of their own, two bullets reading `}`
    and `let data = null;` with nothing else.
    """
    segments = []
    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        for piece in _split_inline_tree(text):
            kind = "code" if _looks_like_code(piece) else "prose"
            if segments and segments[-1][0] == kind:
                segments[-1][1].append(piece)
            else:
                segments.append((kind, [piece]))

    # Fold too-thin code runs back into the prose first. This has to happen
    # before orphan absorption: a lone `</div>` classifies as code, and while it
    # is still labelled code the orphan pass (which only rescues prose) skips it
    # and it ends up as a slide containing just `</div>`.
    merged = []
    for kind, chunk in segments:
        if kind == "code" and len(chunk) < 2:
            if merged and merged[-1][0] == "prose":
                merged[-1][1].extend(chunk)
            else:
                merged.append(("prose", list(chunk)))
            continue
        merged.append((kind, list(chunk)))

    # Absorb orphan code fragments into the nearest snippet, looking both ways.
    # An earlier version only checked immediate neighbours, so a lone `</div>`
    # sitting between two prose runs still got a slide to itself.
    for idx in range(len(merged)):
        kind, chunk = merged[idx]
        if kind != "prose" or not all(_is_orphan_code_line(l) for l in chunk):
            continue
        target = None
        for offset in range(1, len(merged)):
            for cand in (idx - offset, idx + offset):
                if 0 <= cand < len(merged) and merged[cand][0] == "code":
                    target = cand
                    break
            if target is not None:
                break
        if target is None:
            continue
        if target > idx:
            merged[target][1][:0] = chunk
        else:
            merged[target][1].extend(chunk)
        merged[idx] = ("code", [])

    return [s for s in merged if s[1]]


def _split_long_bullet(text: str) -> list:
    """Break an over-long bullet into sentence-sized pieces.

    A single 1,400-character bullet cannot be shrunk to fit a slide - at 11pt it
    still runs off the bottom, and the font sizer bottoms out. Splitting on
    sentence boundaries keeps each piece readable and lets the outline spill the
    remainder onto a continuation slide.
    """
    text = _clean(text)
    if not text or len(text) <= MAX_BULLET_CHARS:
        return [text] if text else []

    # Prefer sentence breaks; fall back to clause, then word boundaries.
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= MAX_BULLET_CHARS:
            out.append(part)
            continue
        for clause in re.split(r"(?<=[,;:])\s+", part):
            clause = clause.strip()
            if not clause:
                continue
            while len(clause) > MAX_BULLET_CHARS:
                cut = clause.rfind(" ", 0, MAX_BULLET_CHARS)
                if cut <= 0:
                    cut = MAX_BULLET_CHARS
                out.append(clause[:cut].strip())
                clause = clause[cut:].strip()
            if clause:
                out.append(clause)
    return [p for p in out if p]


def _font_size_for(length: int, base: float, minimum: float = 11.0) -> float:
    """Shrink the font as the text grows so long content still fits the frame."""
    if length <= 80:
        return base
    if length <= 160:
        return max(minimum, base - 2)
    if length <= 280:
        return max(minimum, base - 4)
    return minimum


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
#
# A theme is the colour set every template draws from. Adding one here makes it
# selectable from the export API without touching any renderer.

THEMES = {
    "modern": {
        "title":         {"accent": "#1D4ED8", "background": "#0F172A", "title_color": "#F8FAFC", "body_color": "#CBD5E1"},
        "section":       {"accent": "#4F46E5", "background": "#EEF2FF", "title_color": "#1E1B4B", "body_color": "#3730A3"},
        "bullets":       {"accent": "#2563EB", "background": "#FFFFFF", "title_color": "#0F172A", "body_color": "#1E293B"},
        "code":          {"accent": "#0F172A", "background": "#0F172A", "title_color": "#F8FAFC", "body_color": "#E2E8F0"},
        "table":         {"accent": "#7C3AED", "background": "#F8FAFC", "title_color": "#0F172A", "body_color": "#1E293B"},
        "image":         {"accent": "#EA580C", "background": "#FFFFFF", "title_color": "#0F172A", "body_color": "#1E293B"},
        "metrics":       {"accent": "#2563EB", "background": "#F8FAFC", "title_color": "#0F172A", "body_color": "#475569", "card_bg": "#FFFFFF", "card_border": "#E2E8F0"},
        "summary_cards": {"accent": "#3B82F6", "background": "#FFFFFF", "title_color": "#0F172A", "body_color": "#334155", "card_bg": "#F8FAFC", "card_border": "#E2E8F0"},
        "two_column":    {"accent": "#2563EB", "background": "#FFFFFF", "title_color": "#0F172A", "body_color": "#1E293B", "card_bg": "#F8FAFC", "card_border": "#CBD5E1"},
        "steps":         {"accent": "#4F46E5", "background": "#F8FAFC", "title_color": "#0F172A", "body_color": "#334155", "card_bg": "#FFFFFF", "card_border": "#E2E8F0"},
        "takeaways":     {"accent": "#10B981", "background": "#FFFFFF", "title_color": "#0F172A", "body_color": "#1E293B", "card_bg": "#F0FDF4", "card_border": "#BBF7D0"},
    },
    "corporate": {
        "title":         {"accent": "#0F766E", "background": "#0B2B26", "title_color": "#F0FDFA", "body_color": "#99F6E4"},
        "section":       {"accent": "#0F766E", "background": "#ECFDF5", "title_color": "#134E4A", "body_color": "#115E59"},
        "bullets":       {"accent": "#0F766E", "background": "#FFFFFF", "title_color": "#0B2B26", "body_color": "#1F2937"},
        "code":          {"accent": "#0B2B26", "background": "#0B2B26", "title_color": "#F0FDFA", "body_color": "#99F6E4"},
        "table":         {"accent": "#115E59", "background": "#F8FAFC", "title_color": "#0B2B26", "body_color": "#1F2937"},
        "image":         {"accent": "#B45309", "background": "#FFFFFF", "title_color": "#0B2B26", "body_color": "#1F2937"},
        "metrics":       {"accent": "#0F766E", "background": "#F0FDFA", "title_color": "#0B2B26", "body_color": "#134E4A", "card_bg": "#FFFFFF", "card_border": "#CCFBF1"},
        "summary_cards": {"accent": "#0F766E", "background": "#FFFFFF", "title_color": "#0B2B26", "body_color": "#1F2937", "card_bg": "#F0FDFA", "card_border": "#CCFBF1"},
        "two_column":    {"accent": "#0F766E", "background": "#FFFFFF", "title_color": "#0B2B26", "body_color": "#1F2937", "card_bg": "#F8FAFC", "card_border": "#E2E8F0"},
        "steps":         {"accent": "#0D9488", "background": "#F8FAFC", "title_color": "#0B2B26", "body_color": "#1F2937", "card_bg": "#FFFFFF", "card_border": "#E2E8F0"},
        "takeaways":     {"accent": "#059669", "background": "#FFFFFF", "title_color": "#0B2B26", "body_color": "#1F2937", "card_bg": "#ECFDF5", "card_border": "#A7F3D0"},
    },
    "minimal": {
        "title":         {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#6B7280"},
        "section":       {"accent": "#9CA3AF", "background": "#F9FAFB", "title_color": "#111827", "body_color": "#6B7280"},
        "bullets":       {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#374151"},
        "code":          {"accent": "#111827", "background": "#111827", "title_color": "#F9FAFB", "body_color": "#D1D5DB"},
        "table":         {"accent": "#4B5563", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#374151"},
        "image":         {"accent": "#6B7280", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#374151"},
        "metrics":       {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#4B5563", "card_bg": "#F9FAFB", "card_border": "#E5E7EB"},
        "summary_cards": {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#4B5563", "card_bg": "#F9FAFB", "card_border": "#E5E7EB"},
        "two_column":    {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#374151", "card_bg": "#F9FAFB", "card_border": "#E5E7EB"},
        "steps":         {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#4B5563", "card_bg": "#F9FAFB", "card_border": "#E5E7EB"},
        "takeaways":     {"accent": "#111827", "background": "#FFFFFF", "title_color": "#111827", "body_color": "#374151", "card_bg": "#F9FAFB", "card_border": "#E5E7EB"},
    },
}

DEFAULT_THEME = "modern"
DEFAULT_TEMPLATE = "bullets"


def resolve_theme(name: str) -> dict:
    """Look up a theme by name, falling back to the default for unknown input."""
    if not name:
        return THEMES[DEFAULT_THEME]
    return THEMES.get(str(name).strip().lower(), THEMES[DEFAULT_THEME])


def available_themes() -> list:
    return sorted(THEMES)


# ---------------------------------------------------------------------------
# Outline construction
# ---------------------------------------------------------------------------

def _looks_like_label(text: str) -> bool:
    """True for short Title Case / ALLCAPS labels used as table row headers."""
    text = _clean(text)
    if not text or len(text) > 60:
        return False
    words = _WORD_RE.findall(text)
    if not words or len(words) > _LABEL_MAX_WORDS:
        return False
    if text.isupper():
        return True
    # "Problem Statement", "Aim", "Theory" - every word capitalised and no
    # sentence punctuation, which is how report tables label their rows.
    if text.endswith((".", "!", "?")):
        return False
    return all(word[:1].isupper() for word in words if word[:1].isalpha())


def _row_value(row: list) -> str:
    """The non-label half of a two-column row, as clean lines."""
    value = (row[1] if len(row) > 1 else "") or ""
    return "\n".join(ln.strip() for ln in value.split("\n") if ln.strip())


def _is_label_value_table(rows: list) -> bool:
    """A two-column table whose left column is mostly labels.

    This is the shape of essentially every lab-report "Objective | ..." table,
    and treating it as a definition list (label becomes the slide title) is far
    more faithful than rendering it as a 2-column grid of tiny text.
    """
    if not rows or len(rows[0]) != 2:
        return False
    labelled = sum(1 for r in rows if r and _looks_like_label(r[0]))
    return labelled >= max(2, len(rows) // 2)


def _derive_title_from_table(table: dict) -> str:
    """Best-guess deck title from a table's header row.

    Label cells ("Objective", "Aim") are skipped: they are row headers, not the
    document's title, and promoting one produced a title slide that simply
    repeated the first section's heading.
    """
    rows = table.get("rows") or []
    if not rows:
        return ""
    for cell in rows[0]:
        candidate = _clean(cell)
        if not candidate or len(candidate) > 80:
            continue
        if _looks_like_label(candidate):
            continue
        return _truncate(candidate, 80)
    return ""


def _slide(layout, title, bullets=None, table=None, picture=None,
           source_page=None, source_paragraphs=None, code=None,
           caption=None) -> dict:
    return {"layout": layout, "title": title or "", "bullets": bullets or [],
            "table": table, "picture": picture, "source_page": source_page,
            "source_paragraphs": source_paragraphs or frozenset(),
            "code": code or [], "caption": caption or ""}


def assess_suitability(items: list) -> dict:
    """Decide whether a document can make a presentable deck.

    A deck needs a title, a few distinct sections, and enough prose to fill
    slides. Source code dumps, scanned pages with no text, and one-page notes
    produce a slideshow of near-empty or code-fragment slides, so they are
    reported as unsuitable instead of being rendered into a broken deck.

    Returns a dict with `suitable`, `score`, `reasons` and `stats` so the client
    can explain the decision instead of showing a generic failure.
    """
    reasons = []
    text_items = []
    image_items = []

    def _item_text(item):
        """Content of an item, whether it is a paragraph or a table row set."""
        raw = item.get("text")
        if raw:
            return raw
        rows = item.get("rows")
        if rows:
            return "\n".join(
                "\n".join(str(c or "") for c in row) for row in rows
            )
        return ""

    chars = 0
    lines = 0
    headings = 0
    code_segments = 0
    prose_segments = 0
    for item in items:
        raw = _item_text(item)
        if raw.strip():
            text_items.append(item)
        if item.get("kind") == "image_page":
            image_items.append(item)
        chars += len(raw)
        body = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        lines += len(body)
        if item.get("kind") == "heading" or (len(body) == 1 and len(body[0]) <= 90):
            headings += 1
        for line in body:
            if _looks_like_code(line):
                code_segments += 1
            else:
                prose_segments += 1

    total_segments = code_segments + prose_segments
    code_ratio = (code_segments / total_segments) if total_segments else 0.0

    if chars < 400:
        reasons.append(
            f"Only {chars} characters of text were found - there is not enough "
            "content to fill slides."
        )
    # Block count is deliberately not a gate: a practical report often packs
    # everything into one paragraph plus one table, and those make good decks.
    if total_segments and code_ratio > 0.85:
        reasons.append(
            f"About {int(code_ratio * 100)}% of the content is source code. Code "
            "reads better in an editor than on slides."
        )
    if not text_items and image_items:
        reasons.append(
            "The document contains only scanned page images with no extractable "
            "text, so no slides can be written."
        )
    if lines and lines < 8:
        reasons.append(
            f"Only {lines} line(s) of content - this is closer to a note than a "
            "document."
        )

    score = 100
    score -= min(40, code_ratio * 50)
    score -= 30 if chars < 400 else 0
    score -= 20 if (not text_items and image_items) else 0
    score -= 15 if (lines and lines < 8) else 0
    score = max(0, int(score))

    return {
        "suitable": not reasons,
        "score": score,
        "reasons": reasons,
        "stats": {
            "characters": chars,
            "lines": lines,
            "blocks": len(text_items),
            "headings": headings,
            "code_ratio": round(code_ratio, 3),
        },
    }


def build_outline(items: list) -> list:
    """Turn an ordered block stream into a list of slide specs.
    First analyzes document structure, narrative, metrics, workflows, and comparisons,
    producing purposeful slide types. Falls back to structural heuristics if needed.
    """
    try:
        from RapidDoc.backend.app.services.ppt_analyzer import analyze_and_build_outline
        analyzed = analyze_and_build_outline(items)
        if analyzed and len(analyzed) >= 2:
            return analyzed
    except Exception as exc:
        logger.warning("Intelligent document presentation analyzer failed: %s; falling back to legacy outline", exc)

    has_real_headings = any(
        item.get("kind") == "paragraph" and (item.get("heading_level") or 0) > 0
        for item in items
    )

    doc_title = _infer_doc_title(items)
    slides = []
    if doc_title:
        slides.append(_slide("title", doc_title))

    slides.extend(_build_from_headings(items) if has_real_headings
                  else _build_from_flat_items(items))

    # A deck with nothing but a title slide is not a deck.
    if not any(s["layout"] != "title" for s in slides):
        slides.append(_slide("bullets", doc_title or "Document"))

    slides = _drop_redundant_lead(slides, doc_title)
    return slides


def _drop_redundant_lead(slides: list, doc_title: str) -> list:
    """Remove a leading slide that just restates the title slide.

    A document whose first content is its own title produced "Practical 1:
    Introduction to React" as slide 1 and then an "Overview" slide whose only
    bullet was that identical sentence. Two slides saying the same thing is the
    clearest sign of a machine-made deck, so a lead slide is dropped when its
    content adds nothing beyond the title.
    """
    if len(slides) < 2 or not doc_title:
        return slides

    head = slides[0]
    if head.get("layout") != "title":
        return slides

    nxt = slides[1]
    target = _normalize_title(doc_title)
    if nxt.get("layout") != "bullets":
        return slides

    bullets = [b for b in (nxt.get("bullets") or []) if (b.get("text") or "").strip()]
    if not bullets:
        return slides[1:] if nxt.get("layout") in ("bullets", "section") else slides

    # Drop the lead only when every bullet is already covered by the title.
    if all(_normalize_title(b.get("text")) in target or target in _normalize_title(b.get("text"))
           for b in bullets):
        return [slides[0]] + slides[2:]
    return slides


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _infer_doc_title(items: list) -> str:
    """Document title: first Heading 1, else a table header, else a short lead."""
    for item in items:
        if item.get("kind") == "paragraph" and (item.get("heading_level") or 0) == 1:
            title = _clean(item.get("text"))
            if title:
                return _truncate(title, 80)

    for item in items:
        if item.get("kind") != "table":
            continue
        candidate = _derive_title_from_table(item)
        if candidate and len(candidate) > 3:
            return candidate

    for item in items:
        if item.get("kind") != "paragraph":
            continue
        text = _clean(item.get("text"))
        if text and len(text) <= 90 and not text.endswith((".", ",", ";")):
            return _truncate(text, 80)
    return ""


def _chunk_bullets(bullets: list) -> list:
    """Split an over-long bullet list into per-slide chunks."""
    if len(bullets) <= MAX_BULLETS_PER_SLIDE:
        return [bullets]
    return [bullets[i:i + MAX_BULLETS_PER_SLIDE]
            for i in range(0, len(bullets), MAX_BULLETS_PER_SLIDE)]


def _label_value_slides(rows: list) -> list:
    """One section per "label | value" row, the label becoming the slide title.

    The value half of these rows is frequently enormous - the "Implementation"
    row of a lab report is the entire body of the practical - so this does *not*
    put the cell on a single slide. Each row's content is split into readable
    bullets, code and file trees are pulled out into monospace blocks, and the
    remainder spills onto "(cont.)" slides. Before, one such cell produced a
    single slide holding ~14,000 characters of text.
    """
    slides = []
    for row in rows:
        label = _clean(row[0]) if row else ""
        value = _row_value(row)
        if not label and not value:
            continue
        if not value:
            slides.append(_slide("section", label))
            continue

        title = label or "Details"
        lines = [ln for ln in value.split("\n") if ln.strip()]

        # Walk the lines, accumulating bullets and code runs separately so a
        # snippet keeps its own slide instead of being interleaved with prose.
        prose = []
        code_run = []
        slide_specs = []

        def flush_prose(chunk_title):
            if not prose:
                return
            bullets = []
            for b in prose:
                for piece in _split_long_bullet(b):
                    bullets.append({"text": piece, "level": 0})
            for part in _chunk_bullets(bullets):
                slide_specs.append(_slide("bullets", chunk_title, part))
            prose.clear()

        def flush_code(chunk_title, caption=""):
            if not code_run:
                return
            # A heading that is already "Code" must not become "Code - code".
            label = chunk_title.strip()
            if re.search(r"\bcode\b", label, re.IGNORECASE):
                base = label
            else:
                base = label or "Code"

            # Split into full slides, then fold a tiny remainder back into the
            # previous slide. A trailing block of one line produced a slide whose
            # only content was `└── Footer.jsx`.
            blocks = []
            for start in range(0, len(code_run), MAX_CODE_LINES_PER_SLIDE):
                blocks.append(code_run[start:start + MAX_CODE_LINES_PER_SLIDE])
            if len(blocks) > 1 and len(blocks[-1]) < 2:
                blocks[-2].extend(blocks[-1])
                blocks.pop()

            for i, block in enumerate(blocks):
                cont = i > 0
                slide_specs.append(_slide(
                    "code", f"{base} (cont.)" if cont else base,
                    code=block,
                    caption=caption if not cont else "",
                ))
            code_run.clear()

        # A short line immediately before a snippet is a label for it
        # ("Server.js:", "Config.js:"), not a bullet and not a slide of its own.
        # Giving it its own slide turned one 13,800-character "Implementation"
        # cell into 170-odd one-line slides; as the first line of the monospace
        # block it reads exactly as it does in the source document.
        segments = _segment_lines(lines)
        for idx, (seg_kind, chunk) in enumerate(segments):
            nxt = segments[idx + 1][0] if idx + 1 < len(segments) else None
            if seg_kind == "code":
                flush_prose(title)
                code_run.extend(
                    _clean_code_line(ln)[:MAX_CODE_CHARS_PER_LINE] for ln in chunk
                )
                continue

            text = " ".join(ln.strip() for ln in chunk).strip()
            is_label = (nxt == "code"
                        and len(text) <= SHORT_CAPTION_CHARS
                        and not text.endswith((".", "!", "?")))
            if is_label:
                code_run.append(text[:MAX_CODE_CHARS_PER_LINE])
                continue

            flush_code(title)
            prose.extend(chunk)

        flush_prose(title)
        flush_code(title)

        slides.extend(slide_specs or [_slide("section", label)])

    return slides


def _table_slide(rows: list) -> dict:
    header = next((_clean(c) for c in rows[0] if _clean(c)), "Table")
    return _slide("table", _truncate(header, 90), table={"rows": rows})


def _table_slides(rows: list) -> list:
    """Split a long table across slides, repeating the header row.

    A 40-row table used to be cut off at 14 rows with a "Showing 14 of 40" note,
    which silently threw away two thirds of the data. Repeating the header on
    each part keeps every row present and each slide readable.
    """
    if not rows:
        return []
    if len(rows) <= MAX_TABLE_ROWS:
        return [_table_slide(rows)]

    header = rows[0]
    body = rows[1:]
    slides = []
    for start in range(0, len(body), MAX_TABLE_ROWS - 1):
        part = body[start:start + MAX_TABLE_ROWS - 1]
        if not part:
            break
        label = _clean(header[0]) if header else "Table"
        cont = f"{label} (cont. {start // (MAX_TABLE_ROWS - 1) + 1})" if start else label
        slides.append(_slide("table", _truncate(cont, 90),
                             table={"rows": [header] + part}))
    return slides


def _build_from_headings(items: list) -> list:
    """Outline driven by real heading levels.

    A heading that has body text under it becomes a content slide titled with
    that heading. A heading with nothing under it becomes a section divider.
    Emitting both a divider *and* a content slide per heading produced two
    slides saying the same thing back to back.
    """
    slides = []
    current_title = "Overview"
    current_page = None
    emitted_titles = set()
    pending_divider = False
    bullets = []
    # Paragraph indices behind the buffered bullets, so a DOCX picture anchored
    # after paragraph N lands on the slide built from paragraph N rather than on
    # whichever slide happened to be first.
    bullet_sources = set()

    def flush():
        """Close the current section: content slides if it has any, else a divider."""
        nonlocal bullets, bullet_sources, pending_divider
        if bullets:
            pending_divider = False
            for chunk in _chunk_bullets(bullets):
                slides.append(_slide("bullets", current_title, chunk,
                                     source_page=current_page,
                                     source_paragraphs=frozenset(bullet_sources)))
        elif pending_divider:
            slides.append(_slide("section", current_title,
                                 source_page=current_page,
                                 source_paragraphs=frozenset({current_title})))
        pending_divider = False
        bullets = []
        bullet_sources = set()

    for item in items:
        kind = item.get("kind")

        if kind == "image_page":
            # A report page with no text of its own is a screenshot; keep it in
            # document order as an image slide rather than dropping the page.
            flush()
            slides.append(_slide(
                "image", _truncate(_clean(item.get("text")) or "Page", 90),
                source_page=item.get("source_page"),
            ))
            continue

        if kind == "paragraph":
            level = item.get("heading_level") or 0
            text = _clean(item.get("text"))
            if text and 1 <= level <= MAX_HEADING_DEPTH:
                title = _truncate(text, 90)
                # A running header repeated on every page of a PDF reads as the
                # same heading over and over; keep the first and let the content
                # accumulate under it instead of duplicating the section.
                if title == current_title or title in emitted_titles:
                    current_page = item.get("source_page")
                    continue
                flush()
                current_title = title
                current_page = item.get("source_page")
                emitted_titles.add(title)
                pending_divider = True
            elif text:
                # Sub-headings deeper than MAX_HEADING_DEPTH stay as bullets, but
                # keep their indent so the hierarchy survives. Anything too long
                # to be a readable bullet is split on sentence boundaries first.
                for piece in _split_long_bullet(text):
                    bullets.append({"text": piece,
                                    "level": 1 if level > MAX_HEADING_DEPTH else 0})
                bullet_sources.add(item.get("index"))
                if len(bullets) >= MAX_BULLETS_PER_SLIDE:
                    flush()
                    pending_divider = False

        elif kind == "table":
            rows = item.get("rows") or []
            if not rows:
                continue
            if _is_label_value_table(rows):
                flush()
                slides.extend(_label_value_slides(rows))
            else:
                # A table is itself the section's content, so the divider would
                # be an empty slide. Long tables spill over several slides rather
                # than being truncated.
                flush()
                slides.extend(_table_slides(rows))

    flush()
    return slides


def _build_from_flat_items(items: list) -> list:
    """No headings anywhere: infer structure from tables and paragraph rhythm."""
    slides = []
    bullets = []
    bullet_sources = set()
    title = "Overview"

    def flush():
        nonlocal bullets, bullet_sources
        if bullets:
            for chunk in _chunk_bullets(bullets):
                slides.append(_slide("bullets", title, chunk,
                                     source_paragraphs=frozenset(bullet_sources)))
        bullets = []
        bullet_sources = set()

    for item in items:
        kind = item.get("kind")

        if kind == "image_page":
            flush()
            slides.append(_slide(
                "image", _truncate(_clean(item.get("text")) or "Page", 90),
                source_page=item.get("source_page"),
            ))
            continue

        if kind == "paragraph":
            text = _clean(item.get("text"))
            if not text:
                continue
            lines = [ln for ln in text.split("\n") if ln.strip()]
            for seg_kind, chunk in _segment_lines(lines):
                if seg_kind == "code":
                    flush()
                    slides.append(_slide(
                        "code", title,
                        code=[ln[:MAX_CODE_CHARS_PER_LINE] for ln in chunk],
                    ))
                    continue
                for line in chunk:
                    for piece in _split_long_bullet(line.strip()):
                        bullets.append({"text": piece, "level": 0})
                bullet_sources.add(item.get("index"))
                # Break the run periodically; otherwise an unstructured document
                # collapses into a couple of unreadably dense slides.
                if len(bullets) >= MAX_BULLETS_PER_SLIDE:
                    flush()

        elif kind == "table":
            rows = item.get("rows") or []
            if not rows:
                continue
            flush()
            if _is_label_value_table(rows):
                slides.extend(_label_value_slides(rows))
            else:
                slides.extend(_table_slides(rows))

    flush()
    return slides


# ---------------------------------------------------------------------------
# Low-level drawing helpers
# ---------------------------------------------------------------------------

def _rgb(color_hex: str):
    from pptx.dml.color import RGBColor

    value = (color_hex or "#FFFFFF").lstrip("#")
    if len(value) != 6:
        value = "FFFFFF"
    try:
        return RGBColor.from_string(value.upper())
    except Exception:
        return RGBColor.from_string("FFFFFF")


def _add_rect(slide, left_in, top_in, width_in, height_in, color_hex: str):
    """A plain filled rectangle, used for backgrounds and accent bars."""
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left_in), Inches(top_in),
        Inches(width_in), Inches(height_in),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color_hex)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _add_card(slide, left_in, top_in, width_in, height_in, bg_hex="#F8FAFC", border_hex="#E2E8F0"):
    """A rounded rectangle container with subtle background and border for cards."""
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches, Pt

    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left_in), Inches(top_in),
        Inches(width_in), Inches(height_in),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(bg_hex)
    if border_hex:
        shape.line.color.rgb = _rgb(border_hex)
        shape.line.width = Pt(1.2)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _add_background(slide, color_hex: str) -> None:
    """Fill the slide, keeping the rectangle behind everything added later."""
    shape = _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, SLIDE_HEIGHT_IN, color_hex)
    tree = shape._element.getparent()
    tree.remove(shape._element)
    # Index 2 is after <p:nvGrpSpPr> and <p:grpSpPr>, i.e. the back of the
    # z-order.
    tree.insert(2, shape._element)


def _add_text(slide, text, left_in, top_in, width_in, height_in, *,
              size=18, bold=False, color="#1E293B", align=None,
              font="Calibri", line_spacing=None):
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(left_in), Inches(top_in),
                                   Inches(width_in), Inches(height_in))
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text or ""
    paragraph = tf.paragraphs[0]
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = _rgb(color)
    paragraph.font.name = font
    if align is not None:
        paragraph.alignment = align
    if line_spacing is not None:
        paragraph.line_spacing = line_spacing
    return box


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _render_title_slide(prs, blank, spec, theme):
    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    # Accent bar down the left edge so the title slide is recognisable even in
    # a thumbnail grid.
    _add_rect(slide, 0, 0, 0.28, SLIDE_HEIGHT_IN, theme["accent"])
    _add_rect(slide, 1.1, 3.05, 2.2, 0.06, theme["accent"])

    title = spec.get("title") or "Document"
    _add_text(slide, _truncate(title, 120), 1.1, 1.9, 10.9, 2.0,
              size=_font_size_for(len(title), 44, 26), bold=True,
              color=theme["title_color"])

    bullets = [b.get("text") for b in spec.get("bullets") or [] if b.get("text")]
    if bullets:
        _add_text(slide, "\n".join(f"•  {b}" for b in bullets[:3]),
                  1.1, 3.35, 10.9, 2.4, size=18,
                  color=theme["body_color"], line_spacing=1.25)
    return slide


def _render_section_slide(prs, blank, spec, theme):
    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.22, theme["accent"])

    title = spec.get("title") or ""
    picture = spec.get("picture")
    # A PDF page image sits under a shorter title block so both fit the slide.
    title_width = 5.6 if picture else 11.3
    title_size = _font_size_for(len(title), 32 if picture else 38, 20)

    _add_text(slide, _truncate(title, 110), 1.0, 2.6 if picture else 2.85,
              title_width, 1.9, size=title_size, bold=True,
              color=theme["title_color"])
    _add_rect(slide, 1.0, 4.6, 1.8, 0.05, theme["accent"])

    if picture:
        try:
            stream, _ext = picture
            _add_picture_fit(slide, stream, 7.3, 1.2, 5.4, 5.2)
        except Exception as exc:
            logger.warning("Could not embed source image on a section slide: %s", exc)
    return slide


def _render_bullets_slide(prs, blank, spec, theme, continuation=False):
    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or ""
    heading = f"{title} (cont.)" if continuation and title else (title or "Details")
    _add_text(slide, _truncate(heading, 100), 0.65, 0.45, 9.6, 0.95,
              size=_font_size_for(len(heading), 30, 20), bold=True,
              color=theme["title_color"])

    picture = spec.get("picture")
    body_width = 8.1 if picture else 12.0
    if picture:
        try:
            stream, _ext = picture
            _add_picture_fit(slide, stream, 9.05, 1.5, 3.6, 4.6)
        except Exception as exc:
            logger.warning("Could not embed source image on a bullet slide: %s", exc)

    bullets = [b for b in spec.get("bullets") or [] if (b.get("text") or "").strip()]
    if not bullets:
        _add_text(slide, "No content on this slide.", 0.75, 1.6, body_width, 1.0,
                  size=16, color=theme["body_color"])
        return slide

    # Size the text to the content volume rather than a fixed 18pt, so a dense
    # slide shrinks instead of spilling past the bottom of the frame.
    total_chars = sum(len(b.get("text") or "") for b in bullets)
    base = 20 if len(bullets) <= 4 else 17 if len(bullets) <= 6 else 15
    size = _font_size_for(total_chars, base, 11)

    from pptx.util import Inches, Pt
    box = slide.shapes.add_textbox(Inches(0.75), Inches(1.55),
                                   Inches(body_width), Inches(5.3))
    tf = box.text_frame
    tf.word_wrap = True

    for i, bullet in enumerate(bullets):
        paragraph = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        indent = "    " * int(bullet.get("level") or 0)
        paragraph.text = f"{indent}•  {bullet.get('text')}"
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = _rgb(theme["body_color"])
        paragraph.font.name = "Calibri"
        paragraph.space_after = Pt(6)
        paragraph.line_spacing = 1.1
    return slide


def _render_table_slide(prs, blank, spec, theme):
    """A real PowerPoint table, so the result stays editable in PowerPoint."""
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Table"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.9,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    raw_rows = (spec.get("table") or {}).get("rows") or []
    rows = [[_clean(cell).replace("\n", " ") for cell in row]
            for row in raw_rows if row]
    if not rows:
        _add_text(slide, "This table is empty.", 0.75, 1.6, 12.0, 1.0, size=16,
                  color=theme["body_color"])
        return slide

    n_cols = max(len(row) for row in rows)
    visible = rows[:MAX_TABLE_ROWS]
    truncated_note = None
    if len(rows) > MAX_TABLE_ROWS:
        visible = visible + [["..."] * n_cols]
        truncated_note = f"Showing {MAX_TABLE_ROWS} of {len(rows)} rows."

    row_height = min(0.55, max(0.28, 5.4 / len(visible)))
    shape = slide.shapes.add_table(
        len(visible), n_cols, Inches(0.6), Inches(1.5),
        Inches(12.1), Inches(row_height * len(visible)),
    )
    table = shape.table

    font_size = 13 if len(visible) <= 8 else 11 if len(visible) <= 12 else 9

    for r, row in enumerate(visible):
        for c in range(n_cols):
            cell = table.cell(r, c)
            value = row[c] if c < len(row) else ""
            # One cell can still hold a paragraph; cap it so a single cell
            # cannot blow out the row height.
            cell.text = _truncate(value, MAX_CELL_CHARS)
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.font.size = Pt(font_size)
            paragraph.font.name = "Calibri"
            paragraph.font.bold = (r == 0)
            paragraph.font.color.rgb = _rgb(
                "#FFFFFF" if r == 0 else theme["body_color"]
            )
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(
                theme["accent"] if r == 0 else ("#F1F5F9" if r % 2 else "#FFFFFF")
            )

    if truncated_note:
        _add_text(slide, truncated_note, 0.65, 6.9, 12.0, 0.4, size=11,
                  color=theme["body_color"])
    return slide


def _render_image_slide(prs, blank, spec, theme):
    from pptx.util import Inches

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Figure"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.9,
              size=26, bold=True, color=theme["title_color"])

    picture = spec.get("picture")
    if not picture:
        _add_text(slide, "No image available for this slide.", 0.75, 1.6,
                  12.0, 1.0, size=16, color=theme["body_color"])
        return slide
    try:
        stream, _ext = picture
        _add_picture_fit(slide, stream, 0.75, 1.5, 11.8, 5.4)
    except Exception as exc:
        logger.warning("Could not embed source image: %s", exc)
        _add_text(slide, "The source image could not be embedded.", 0.75, 1.6,
                  12.0, 1.0, size=16, color=theme["body_color"])
    return slide


def _render_code_slide(prs, blank, spec, theme):
    """A monospace block for shell commands, snippets and file trees.

    Rendering these as bullets destroyed exactly the thing that made them
    readable: a file tree only means anything with its indentation and its
    tree-drawing characters intact.
    """
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme["background"])
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Code"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 26, 20), bold=True,
              color=theme["title_color"])

    # Applied here as well as at collection time so a snippet that reached the
    # block through the caption/label path is cleaned too.
    lines = [_clean_code_line(ln) for ln in (spec.get("code") or [])]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return slide

    # A caption names the snippet ("Server.js:") and doubles as the slide's
    # subject, so the title does not have to be repeated on every slide of a
    # long implementation section.
    caption = (spec.get("caption") or "").strip()
    top = 1.5

    if caption:
        _add_text(slide, _truncate(caption, 110), 0.75, 1.18, 11.8, 0.34,
                  size=13, bold=True, color="#93C5FD")
        top = 1.62

    # Consolas keeps the tree glyphs aligned; shrink only as far as 9pt.
    size = 14 if len(lines) <= 8 else 12 if len(lines) <= 11 else 10
    line_h = size / 72.0 * 1.25
    box_h = min(5.0, max(1.0, line_h * len(lines) + 0.3))

    # The tinted panel must be added *before* the text box: python-pptx stacks
    # shapes in insertion order, so drawing the rectangle afterwards painted it
    # straight over the code and every code slide came out as a blank rectangle.
    _add_rect(slide, 0.65, top - 0.1, 12.0, box_h + 0.25, "#0F172A")

    box = slide.shapes.add_textbox(Inches(0.75), Inches(top),
                                   Inches(11.8), Inches(box_h))
    tf = box.text_frame
    tf.word_wrap = False
    try:
        from pptx.enum.text import MSO_AUTO_SIZE
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass

    for i, line in enumerate(lines):
        paragraph = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        # XML has no concept of a leading space, so indent with non-breaking
        # spaces - a normal space would be collapsed and flatten the tree.
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        paragraph.text = ("\u00a0" * indent) + stripped
        paragraph.font.size = Pt(size)
        paragraph.font.name = "Consolas"
        paragraph.font.color.rgb = _rgb("#E2E8F0")
        paragraph.space_after = Pt(0)
        paragraph.line_spacing = 1.0
    return slide


def _render_summary_cards_slide(prs, blank, spec, theme):
    """Executive summary with 2 or 3 structured cards side by side."""
    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme.get("background", "#FFFFFF"))
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Executive Summary & Core Objectives"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    cards = spec.get("cards") or []
    if not cards:
        _add_text(slide, "No summary cards available.", 0.75, 1.6, 12.0, 1.0, size=16, color=theme["body_color"])
        return slide

    card_bg = theme.get("card_bg", "#F8FAFC")
    card_border = theme.get("card_border", "#E2E8F0")

    num_cards = min(3, len(cards))
    total_w = 12.0
    spacing = 0.35
    card_w = (total_w - (num_cards - 1) * spacing) / num_cards
    card_h = 4.7
    top = 1.6

    for i in range(num_cards):
        c_left = 0.65 + i * (card_w + spacing)
        c = cards[i]
        _add_card(slide, c_left, top, card_w, card_h, card_bg, card_border)
        _add_rect(slide, c_left, top, card_w, 0.08, theme["accent"])

        c_title = c.get("title") or f"Pillar {i + 1}"
        _add_text(slide, _truncate(c_title, 40), c_left + 0.25, top + 0.25, card_w - 0.5, 0.65,
                  size=16, bold=True, color=theme["title_color"])

        c_text = c.get("text") or ""
        _add_text(slide, c_text, c_left + 0.25, top + 0.95, card_w - 0.5, card_h - 1.2,
                  size=13, color=theme["body_color"], line_spacing=1.2)

    return slide


def _render_metrics_slide(prs, blank, spec, theme):
    """Quantitative results and key metrics callout cards."""
    from pptx.enum.text import PP_ALIGN

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme.get("background", "#FFFFFF"))
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Key Metrics & Quantifiable Results"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    metrics = spec.get("metrics") or []
    if not metrics:
        _add_text(slide, "No metrics available.", 0.75, 1.6, 12.0, 1.0, size=16, color=theme["body_color"])
        return slide

    card_bg = theme.get("card_bg", "#FFFFFF")
    card_border = theme.get("card_border", "#E2E8F0")

    num = min(4, max(1, len(metrics)))
    total_w = 12.0
    spacing = 0.3
    card_w = (total_w - (num - 1) * spacing) / num
    card_h = 4.6
    top = 1.65

    for i in range(num):
        m_left = 0.65 + i * (card_w + spacing)
        m = metrics[i]
        _add_card(slide, m_left, top, card_w, card_h, card_bg, card_border)
        _add_rect(slide, m_left + (card_w - 1.2) / 2, top + 0.2, 1.2, 0.05, theme["accent"])

        num_str = str(m.get("number") or "100%")
        _add_text(slide, num_str, m_left + 0.15, top + 0.55, card_w - 0.3, 1.3,
                  size=36 if len(num_str) <= 7 else 28, bold=True, color=theme["accent"], align=PP_ALIGN.CENTER)

        m_label = m.get("label") or "Metric"
        _add_text(slide, _truncate(m_label, 32), m_left + 0.2, top + 1.95, card_w - 0.4, 0.7,
                  size=15, bold=True, color=theme["title_color"], align=PP_ALIGN.CENTER)

        m_desc = m.get("desc") or ""
        _add_text(slide, _truncate(m_desc, 120), m_left + 0.2, top + 2.75, card_w - 0.4, 1.6,
                  size=12, color=theme["body_color"], align=PP_ALIGN.CENTER, line_spacing=1.15)

    return slide


def _render_two_column_slide(prs, blank, spec, theme):
    """Comparative analysis or two-pillar strategy slide."""
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme.get("background", "#FFFFFF"))
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Comparative Analysis"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    col1_title = spec.get("col1_title") or "Current State / Challenges"
    col1_bullets = spec.get("col1_bullets") or []
    col2_title = spec.get("col2_title") or "Target Solution / Impact"
    col2_bullets = spec.get("col2_bullets") or []

    columns = spec.get("columns")
    if columns and len(columns) >= 2:
        col1_title = columns[0].get("title") or col1_title
        col1_bullets = columns[0].get("bullets") or col1_bullets
        col2_title = columns[1].get("title") or col2_title
        col2_bullets = columns[1].get("bullets") or col2_bullets

    col_w = 5.8
    col_h = 4.8
    top = 1.55

    for idx, (c_left, c_title, c_bullets, c_accent) in enumerate([
        (0.65, col1_title, col1_bullets, "#64748B"),
        (6.85, col2_title, col2_bullets, theme["accent"]),
    ]):
        _add_card(slide, c_left, top, col_w, col_h, theme.get("card_bg", "#F8FAFC"), theme.get("card_border", "#CBD5E1"))
        _add_rect(slide, c_left, top, col_w, 0.48, c_accent)
        _add_text(slide, _truncate(c_title, 40), c_left + 0.25, top + 0.08, col_w - 0.5, 0.35,
                  size=14, bold=True, color="#FFFFFF")

        bullet_box = slide.shapes.add_textbox(Inches(c_left + 0.25), Inches(top + 0.65), Inches(col_w - 0.5), Inches(col_h - 0.85))
        tf = bullet_box.text_frame
        tf.word_wrap = True

        clean_bullets = [b if isinstance(b, str) else b.get("text", "") for b in c_bullets if b]
        if not clean_bullets:
            clean_bullets = ["No specific items recorded."]
        for b_i, b_text in enumerate(clean_bullets[:5]):
            p = tf.paragraphs[0] if b_i == 0 else tf.add_paragraph()
            p.text = f"•  {b_text}"
            p.font.size = Pt(13)
            p.font.color.rgb = _rgb(theme["body_color"])
            p.font.name = "Calibri"
            p.space_after = Pt(8)
            p.line_spacing = 1.15

    return slide


def _render_steps_slide(prs, blank, spec, theme):
    """Workflow, methodology, or sequential execution pipeline."""
    from pptx.enum.text import PP_ALIGN

    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme.get("background", "#FFFFFF"))
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Execution Pipeline & Methodology"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    steps = spec.get("steps") or []
    if not steps:
        _add_text(slide, "No steps defined.", 0.75, 1.6, 12.0, 1.0, size=16, color=theme["body_color"])
        return slide

    card_bg = theme.get("card_bg", "#FFFFFF")
    card_border = theme.get("card_border", "#E2E8F0")

    num = min(4, max(1, len(steps)))
    total_w = 12.0
    spacing = 0.3
    card_w = (total_w - (num - 1) * spacing) / num
    card_h = 4.6
    top = 1.65

    for i in range(num):
        s_left = 0.65 + i * (card_w + spacing)
        s = steps[i]
        _add_card(slide, s_left, top, card_w, card_h, card_bg, card_border)

        step_num = str(s.get("step") or f"0{i + 1}")
        _add_rect(slide, s_left + 0.3, top + 0.3, 0.7, 0.35, theme["accent"])
        _add_text(slide, step_num, s_left + 0.3, top + 0.32, 0.7, 0.32,
                  size=12, bold=True, color="#FFFFFF", align=PP_ALIGN.CENTER)

        s_title = s.get("title") or f"Phase {i + 1}"
        _add_text(slide, _truncate(s_title, 35), s_left + 0.25, top + 0.85, card_w - 0.5, 0.75,
                  size=15, bold=True, color=theme["title_color"])

        s_desc = s.get("desc") or ""
        _add_text(slide, _truncate(s_desc, 140), s_left + 0.25, top + 1.65, card_w - 0.5, card_h - 1.85,
                  size=12, color=theme["body_color"], line_spacing=1.2)

    return slide


def _render_takeaways_slide(prs, blank, spec, theme):
    """Strategic conclusion and key takeaways rows."""
    slide = prs.slides.add_slide(blank)
    _add_background(slide, theme.get("background", "#FFFFFF"))
    _add_rect(slide, 0, 0, SLIDE_WIDTH_IN, 0.16, theme["accent"])

    title = spec.get("title") or "Key Takeaways & Strategic Conclusion"
    _add_text(slide, _truncate(title, 100), 0.65, 0.45, 12.0, 0.85,
              size=_font_size_for(len(title), 28, 20), bold=True,
              color=theme["title_color"])

    takeaways = spec.get("takeaways") or []
    if not takeaways:
        bullets = spec.get("bullets") or []
        takeaways = [{"title": f"Takeaway {idx + 1}", "desc": b.get("text", "") if isinstance(b, dict) else str(b)} for idx, b in enumerate(bullets[:4])]

    if not takeaways:
        _add_text(slide, "No takeaways recorded.", 0.75, 1.6, 12.0, 1.0, size=16, color=theme["body_color"])
        return slide

    card_bg = theme.get("card_bg", "#F0FDF4")
    card_border = theme.get("card_border", "#BBF7D0")

    num = min(4, len(takeaways))
    row_h = 1.05
    spacing = 0.22
    top = 1.6

    for i in range(num):
        t_top = top + i * (row_h + spacing)
        t = takeaways[i]
        _add_card(slide, 0.65, t_top, 12.0, row_h, card_bg, card_border)
        _add_rect(slide, 0.65, t_top, 0.12, row_h, theme["accent"])

        t_title = t.get("title") or f"Takeaway {i + 1}"
        t_desc = t.get("desc") or ""

        _add_text(slide, _truncate(t_title, 36), 0.95, t_top + 0.12, 11.5, 0.32,
                  size=14, bold=True, color=theme["title_color"])
        _add_text(slide, _truncate(t_desc, 150), 0.95, t_top + 0.45, 11.5, 0.52,
                  size=12, color=theme["body_color"])

    return slide


_RENDERERS = {
    "title": _render_title_slide,
    "section": _render_section_slide,
    "bullets": _render_bullets_slide,
    "table": _render_table_slide,
    "image": _render_image_slide,
    "code": _render_code_slide,
    "summary_cards": _render_summary_cards_slide,
    "cards": _render_summary_cards_slide,
    "metrics": _render_metrics_slide,
    "stats": _render_metrics_slide,
    "two_column": _render_two_column_slide,
    "comparison": _render_two_column_slide,
    "steps": _render_steps_slide,
    "timeline": _render_steps_slide,
    "takeaways": _render_takeaways_slide,
    "conclusion": _render_takeaways_slide,
}


def _add_footer(slide, theme, deck_title, number, total):
    """Running footer: deck title on the left, slide number on the right.

    A deck with no footer or page numbers reads as a raw dump of the document
    rather than a finished presentation. The title slide keeps a clean edge, and
    the rule is drawn only once per slide.
    """
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    y = SLIDE_HEIGHT_IN - 0.42
    _add_rect(slide, 0.65, y - 0.06, 12.0, 0.012,
              theme.get("rule", "#CBD5E1"))
    if deck_title:
        _add_text(slide, _truncate(deck_title, 90), 0.65, y, 9.6, 0.3,
                  size=9, color="#94A3B8")
    _add_text(slide, f"{number} / {total}", 10.5, y, 2.15, 0.3,
              size=9, color="#94A3B8", align=PP_ALIGN.RIGHT)


def render_deck(slides: list, theme: str = DEFAULT_THEME):
    """Build a ``Presentation`` from an outline produced by :func:`build_outline`."""
    from pptx import Presentation
    from pptx.util import Inches

    palette = resolve_theme(theme)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_IN)
    prs.slide_height = Inches(SLIDE_HEIGHT_IN)
    # Layout 6 is the blank layout. Every template draws its own geometry, which
    # avoids inheriting the default master's placeholder positions - the reason
    # exported text used to sit off-centre and overflow.
    blank = prs.slide_layouts[6]

    deck_title = next(
        (s.get("title") for s in slides
         if s.get("layout") == "title" and s.get("title")),
        "",
    )
    total = len(slides)

    previous_title = None
    for position, spec in enumerate(slides, start=1):
        layout = spec.get("layout") or DEFAULT_TEMPLATE
        rendered = None
        if layout not in _RENDERERS:
            rendered = _render_bullets_slide(prs, blank, spec, palette[DEFAULT_TEMPLATE])
        elif layout == "bullets":
            # Consecutive slides sharing a title read better marked "(cont.)".
            rendered = _render_bullets_slide(
                prs, blank, spec, palette["bullets"],
                continuation=spec.get("title") == previous_title)
        elif layout == "code":
            rendered = _render_code_slide(
                prs, blank, spec, palette.get("code") or palette["bullets"])
        else:
            rendered = _RENDERERS[layout](prs, blank, spec, palette[layout])

        if rendered is not None and layout != "title":
            try:
                _add_footer(rendered, palette.get(layout) or palette["bullets"],
                            deck_title, position, total)
            except Exception as exc:
                logger.warning("Could not add slide footer: %s", exc)
        previous_title = spec.get("title")

    try:
        prs.core_properties.title = next(
            (s.get("title") for s in slides
             if s.get("layout") == "title" and s.get("title")),
            "RapidDoc Export",
        )
        prs.core_properties.author = "RapidDoc"
    except Exception as exc:
        logger.debug("Could not set PPTX core properties: %s", exc)

    return prs
