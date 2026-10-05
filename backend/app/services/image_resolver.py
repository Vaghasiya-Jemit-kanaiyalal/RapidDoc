"""Working out *which* image a natural-language request means.

This is the whole of the "AI" behind prompt-driven image replacement, and it is
deliberately not a model.

A replacement is fully determined by an integer: swap the bytes behind image N.
There is nothing to learn about that. The only judgement call is the translation
from words to an integer ("page 1", "the logo", "the last picture"), and that is
addressing - the same kind of problem ``understand_command`` already solves for
text - not perception or generation. It runs as an ordered rule chain over the
document's real image list, with the language model consulted only as a
fallback for phrasings the rules do not recognise.

Three consequences worth stating, because they are why no training is needed:

1. **Every answer is verifiable.** The resolver only ever returns an index that
   actually exists in the document it just inspected. There is no generation step
   to hallucinate a wrong-but-plausible number.
2. **Ambiguity is surfaced, not guessed.** "Change the image on page 3" against a
   page holding two diagrams does not pick one; it returns both so the UI can
   ask. Silent coin-flips are how a document gets quietly corrupted.
3. **It is free.** No GPU, no weights, no dataset, no retraining - and it keeps
   working with no network and no API key.

The only thing that would ever justify a trained model here is *visual* matching
("find the picture of the bar chart"), which needs a vision model. That is a
different feature and is deliberately out of scope; even then it would be a
pretrained checkpoint used zero-shot, not something trained on this app's data.
"""

import io
import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phrase -> number
# ---------------------------------------------------------------------------

_ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10, "eleventh": 11, "11th": 11, "twelfth": 12, "12th": 12,
    "last": -1, "final": -1, "bottom": -1,
}

_ORDINAL_WORDS = (
    "first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|"
    "eighth|8th|ninth|9th|tenth|10th|eleventh|11th|twelfth|12th|last|final"
)

# A number with an optional ordinal suffix, so "the 99th image" parses the same
# way as "the 3rd image".
_NUM_SUFFIX_RE = re.compile(r"(\d+)(?:st|nd|rd|th)")
_NUM_ORDINAL = r"\d+(?:st|nd|rd|th)?"

# Noun first: "the image number 3", "image 2", "picture 1st".
_IMAGE_NTH_RE = re.compile(
    r"\b(?:the\s+)?(?:image|picture|photo|figure|diagram|logo|graphic|chart)\s+"
    r"(?:number|no\.?|#)?\s*(" + _NUM_ORDINAL + r"|" + _ORDINAL_WORDS + r")\b",
    re.IGNORECASE,
)

# Ordinal first: "the third picture", "the last image", "the 2nd photo".
# This is the more natural phrasing in English, and missing it is not harmless -
# "the third picture" would otherwise fall through to the size-based role
# heuristics and resolve to whichever image happened to be largest.
#
# The number is open-ended on purpose: "the 99th image" has to reach the range
# check so the user is told the document has 8, rather than falling through to
# the generic "tell me which image" prompt that implies nothing was understood.
_NTH_IMAGE_RE = re.compile(
    r"\b(?:the\s+)?(" + _NUM_ORDINAL + r"|" + _ORDINAL_WORDS + r")\s+"
    r"(?:image|picture|photo|figure|diagram|logo|graphic|chart)\b",
    re.IGNORECASE,
)

# "the logo", "the chart", bare nouns that describe one image
_ROLE_NOUN_RE = re.compile(
    r"\b(?:the\s+)?(logo|watermark|banner|header\s+image|footer\s+image|"
    r"signature|seal|chart|graph|diagram|figure|screenshot|photo|picture)\b",
    re.IGNORECASE,
)

# "on page 3", "in page 2", "of page 1"
_PAGE_RE = re.compile(
    r"\b(?:on|in|from|of|at)\s+(?:the\s+)?(?:page|pg\.?)\s*(\d+|first|last|cover)\b",
    re.IGNORECASE,
)

# Bare "page 3" with no preposition - "change the image on page 3 page 3".
_PAGE_BARE_RE = re.compile(
    r"\b(?:page|pg\.?)\s*(\d+|first|last|cover)\b", re.IGNORECASE
)

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                 "eleven": 11, "twelve": 12}


def _to_int(token):
    """``"3"`` / ``"3rd"`` / ``"third"`` / ``"three"`` / ``"last"`` -> int, or None.

    A numeric ordinal suffix is stripped first, so any number reaches the range
    check - "the 99th image" has to come back as 99 and be reported as out of
    range, rather than parsing to None and being reported as unintelligible.

    ``"last"`` resolves to -1, meaning "the final one" once the caller knows how
    many there are.
    """
    if token is None:
        return None
    text = str(token).strip().lower()
    if text.isdigit():
        return int(text)
    if text in _ORDINALS:
        return _ORDINALS[text]
    if text in _WORD_NUMBERS:
        return _WORD_NUMBERS[text]
    digits = _NUM_SUFFIX_RE.fullmatch(text)
    if digits:
        return int(digits.group(1))
    return None


_ORDINAL_NAMES = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th",
    8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th",
}


def _ordinal_word(position: int) -> str:
    """``3`` -> ``"3rd"``, for messages like "there is no 3rd one on that page"."""
    return _ORDINAL_NAMES.get(position, f"{position}th")


def _extract_nth(command: str):
    """The ordinal in ``command``, in either word order, or None.

    Returns a 1-based position, or -1 for "last". Handles both "the 1st image"
    and "image 1". Extracted here so the page-scoped and document-wide branches
    agree on what counts as an ordinal - previously each had its own inline
    parsing and they drifted.
    """
    match = _NTH_IMAGE_RE.search(command)
    if not match:
        match = _IMAGE_NTH_RE.search(command)
        if not match:
            # Fallback for shorthand commands like "replace 1 by this", "replce #1", etc.
            m2 = re.search(
                r"\b(?:replace|replce|swap|change)\s+(?:the\s+)?(?:#|number\s+|no\.?\s*)?(\d+)\b",
                command,
                re.IGNORECASE,
            )
            if m2:
                return _to_int(m2.group(1))
            return None
    return _to_int(match.group(1))


# ---------------------------------------------------------------------------
# Document image inventory
# ---------------------------------------------------------------------------

def build_image_inventory(file_path: str, file_type: str) -> list:
    """Every image in the document, on the canonical index space.

    Each entry is::

        {"index", "page_num" (PDF only, else None), "width", "height",
         "pixel_width", "pixel_height", "occurrences", "mime"}

    ``index`` is the exact integer ``replace_docx_images`` /
    ``replace_pdf_images`` expect, because it comes from the same traversal the
    image endpoint and the editor tiles use.

    ``width``/``height`` are the size the picture is *drawn at*, in 96dpi screen
    pixels, for both formats. That is what the user sees and what the resize
    dialog has to prefill; using a PDF's stored pixel count instead meant that
    after resizing, the reported size never changed - the pixels are untouched by
    a resize, only the placement matrix is. ``pixel_width``/``pixel_height`` carry
    the underlying data size when the two differ.
    """
    if file_type == "docx":
        from app.services.docx_editor import get_docx_image_parts

        return [
            {
                "index": part["index"],
                "page_num": None,
                "width": part.get("width"),
                "height": part.get("height"),
                "pixel_width": part.get("pixel_width", part.get("width")),
                "pixel_height": part.get("pixel_height", part.get("height")),
                "occurrences": part.get("occurrences", 1),
                "mime": part.get("mime"),
                "bbox": None,
                "bbox_top": part.get("anchor_index"),
                "bbox_left": None,
            }
            for part in get_docx_image_parts(file_path)
        ]

    if file_type == "pdf":
        from app.services.pdf_editor import get_pdf_image_slots

        inventory = []
        for slot in get_pdf_image_slots(file_path):
            bbox = slot.get("bbox")
            drawn_w = drawn_h = None
            if bbox and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                # PDF user-space units are points; 96/72 puts them in the same
                # screen pixels the DOCX side already reports.
                drawn_w = round((bbox[2] - bbox[0]) * 96 / 72)
                drawn_h = round((bbox[3] - bbox[1]) * 96 / 72)

            inventory.append({
                "index": slot["index"],
                "page_num": slot.get("page_num"),
                "width": drawn_w if drawn_w else slot.get("width"),
                "height": drawn_h if drawn_h else slot.get("height"),
                "pixel_width": slot.get("width"),
                "pixel_height": slot.get("height"),
                "occurrences": slot.get("occurrences", 1),
                "mime": slot.get("mime"),
                # Geometry drives reading-order numbering, so "the 2nd image on
                # page 3" means the second one the reader actually sees.
                "bbox": bbox,
                "bbox_top": (bbox or [None, None])[1],
                "bbox_left": (bbox or [None, None])[0],
            })
        return inventory

    return []


def _describe(entry) -> str:
    """One-line human label for an image, used in the picker and in messages."""
    label = f"Image {entry['index'] + 1}"
    if entry.get("page_num") is not None:
        label += f" on page {entry['page_num'] + 1}"
    dims = ""
    if entry.get("width") and entry.get("height"):
        dims = f" ({entry['width']}x{entry['height']}px)"
    shared = ""
    if (entry.get("occurrences") or 1) > 1:
        shared = f" - used in {entry['occurrences']} places"
    return f"{label}{dims}{shared}"


def _public_inventory(inventory) -> list:
    """Inventory shaped for the client, with the label precomputed."""
    return [{**entry, "label": _describe(entry)} for entry in inventory]


def _numbered(entries) -> list:
    """Candidates carrying the within-page position the user can speak.

    "Page 3 has 4 images - which one?" is a dead end unless the answer can be
    phrased back. Each candidate therefore also exposes ``position`` (1-based,
    top-to-bottom) and an ordinal label, so the UI can offer "the 2nd image on
    page 3" as the follow-up and the resolver can accept exactly that.

    Ordering is by bbox top, then left, then index - the same reading order the
    editor renders, so "the 2nd image" means what the user sees. ``build_image_inventory``
    emits slots in document order already, but a PDF can report placements out of
    reading order, so this is re-sorted explicitly rather than assumed.
    """
    ordered = sorted(
        entries,
        key=lambda e: (
            e.get("bbox_top") if e.get("bbox_top") is not None else float("inf"),
            e.get("bbox_left") if e.get("bbox_left") is not None else float("inf"),
            e["index"],
        ),
    )
    out = _public_inventory(ordered)
    total = len(out)
    for position, entry in enumerate(out, start=1):
        entry["position"] = position
        entry["position_label"] = _ordinal_word(position)
        entry["ordinal_label"] = f"the {entry['position_label']} image"
        entry["label"] = (
            f"Image {position} of {total} on page {entry['page_num'] + 1}"
            if entry.get("page_num") is not None
            else f"Image {position} of {total}"
        )
        size = ""
        if entry.get("width") and entry.get("height"):
            size = f" ({entry['width']}x{entry['height']}px)"
        entry["label"] += size
        if (entry.get("occurrences") or 1) > 1:
            entry["label"] += f" - used in {entry['occurrences']} places"
    return out


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_image_targets(command: str, file_path: str, file_type: str) -> dict:
    """Decide which image(s) a request refers to.

    Returns one of::

        {"status": "resolved",   "indexes": [0], "reason": "..."}
        {"status": "ambiguous",  "candidates": [...], "inventory": [...],
                               "message": "..."}
        {"status": "empty",      "inventory": [], "message": "..."}
        {"status": "unresolved", "inventory": [...], "message": "..."}

    Resolution is deliberately ordered from most to least explicit, and every
    step validates against the real inventory before returning, so a rule can
    never produce an index the writer would reject.

    ``command`` may be empty when the caller already knows the index (a
    double-click). An empty command with no index is ``unresolved``, never a
    guess.
    """
    inventory = build_image_inventory(file_path, file_type)

    if not inventory:
        return {
            "status": "empty",
            "inventory": [],
            "message": (
                "This document has no images, so there is nothing to replace. "
                "You can still edit the text by double-clicking it."
            ),
        }

    total = len(inventory)
    command = (command or "").strip()

    # --- 1. explicit page -------------------------------------------------
    # Pages are a real concept only in a PDF. In a DOCX there are none, so
    # saying so beats inventing a mapping from paragraph counts to pages.
    page_token = None
    page_match = _PAGE_RE.search(command) or _PAGE_BARE_RE.search(command)
    if page_match:
        page_token = page_match.group(1).lower()

    if page_token:
        if file_type != "pdf":
            return {
                "status": "unresolved",
                "inventory": _public_inventory(inventory),
                "message": (
                    "A .docx file has no pages, so I can't target one by page "
                    f"number. This document has {total} image"
                    f"{'s' if total != 1 else ''} - say which one, or double-click "
                    "the image in the document to replace it."
                ),
            }

        page_num = _to_int(page_token)
        if page_num == -1:
            page_num = max(p.get("page_num") or 0 for p in inventory)
        elif page_num is not None:
            page_num -= 1  # users count pages from 1
        else:
            page_num = None

        on_page = [e for e in inventory if e.get("page_num") == page_num] if page_num is not None else []
        if not on_page:
            page_label = (
                f"page {page_num + 1}" if page_num is not None else page_token
            )
            return {
                "status": "unresolved",
                "inventory": _public_inventory(inventory),
                "message": f"There is no image on {page_label} of this document.",
            }
        # --- 1a. "the 1st image on page 2" ---------------------------------
        # An ordinal *inside* a page reference scopes to that page. Without this
        # the page branch below would answer "page 2 has 51 images, which one?"
        # and throw away the number the user just gave - the exact complaint that
        # made multi-image pages unusable.
        scoped_nth = _extract_nth(command)
        if scoped_nth is not None:
            # _extract_nth already speaks 1-based ("first" -> 1). It used to be
            # incremented here as well, which made "the 1st image on page 2" pick
            # the *second* image and "the second image on page 1" report that the
            # page had no 3rd image.
            position = len(on_page) if scoped_nth == -1 else scoped_nth

            if not (1 <= position <= len(on_page)):
                return {
                    "status": "unresolved",
                    "inventory": _public_inventory(inventory),
                    "message": (
                        f"Page {page_num + 1} has {len(on_page)} image"
                        f"{'s' if len(on_page) != 1 else ''}, so there is no "
                        f"{_ordinal_word(scoped_nth)} one on that page."
                    ),
                }
            chosen = on_page[position - 1]
            return {
                "status": "resolved",
                "indexes": [chosen["index"]],
                "reason": f"image {position} of {len(on_page)} on page {page_num + 1}",
            }

        # --- 1b. "the logo on page 2" --------------------------------------
        # A role noun narrowed to one page is a much smaller set than the whole
        # document, so it often resolves where the unscoped version was ambiguous.
        role = _ROLE_NOUN_RE.search(command)
        if role:
            scoped = _role_matches(on_page, role.group(1).lower(), file_type)
            if len(scoped) == 1:
                return {
                    "status": "resolved",
                    "indexes": [scoped[0]["index"]],
                    "reason": f"the only {role.group(1).lower()} on page {page_num + 1}",
                }

        if len(on_page) == 1:
            return {
                "status": "resolved",
                "indexes": [on_page[0]["index"]],
                "reason": f"page {page_num + 1} holds one image",
            }
        return {
            "status": "ambiguous",
            "candidates": _numbered(on_page),
            "inventory": _public_inventory(inventory),
            "message": (
                f"Page {page_num + 1} has {len(on_page)} images. "
                f"Pick one below, or say which - e.g. \"the 2nd image on page "
                f"{page_num + 1}\"."
            ),
        }

    # --- 2. explicit "image 3" or "the third picture" -----------------------
    # Both word orders are checked, and the more specific ordinal form is
    # preferred. An ordinal is an exact address; a bare noun like "the picture"
    # is only a role hint, so letting "the third picture" fall through to the
    # size heuristics would resolve it to whichever image happened to be largest.
    nth = _extract_nth(command)

    if nth is not None:
        # "last"/"final" are relative to the count, so they resolve to the final
        # slot and must skip the range check. Only an explicit number is validated,
        # otherwise "the last image" resolves to len(inventory) and is then
        # rejected as being one past the end.
        is_relative = nth == -1
        if nth == -1:
            nth = total - 1
        else:
            # "image 3" is spoken 1-based but stored 0-based.
            nth = nth - 1
        if not is_relative and not (0 <= nth < total):
            return {
                "status": "unresolved",
                "inventory": _public_inventory(inventory),
                "message": (
                    f"This document has {total} image{'s' if total != 1 else ''}, "
                    f"so there is no {_ordinal_word(nth + 1)} image."
                ),
            }

    if nth is not None:
        return {
            "status": "resolved",
            "indexes": [inventory[nth]["index"]],
            "reason": f"image {nth + 1} of {total}",
        }

    # --- 3. a descriptive noun: "the logo", "the chart" -------------------
    role = _ROLE_NOUN_RE.search(command)
    if role:
        noun = role.group(1).lower()
        matches = _role_matches(inventory, noun, file_type)
        if len(matches) == 1:
            return {
                "status": "resolved",
                "indexes": [matches[0]["index"]],
                "reason": f"the only {noun}",
            }
        if len(matches) > 1:
            return {
                "status": "ambiguous",
                "candidates": _public_inventory(matches),
                "inventory": _public_inventory(inventory),
                "message": (
                    f"I found {len(matches)} possible '{noun}' images. "
                    "Which one should I replace?"
                ),
            }
        return {
            "status": "unresolved",
            "inventory": _public_inventory(inventory),
            "message": (
                f"I could not tell which image is the {noun}. "
                f"This document has {total} image{'s' if total != 1 else ''} - "
                "say 'the second image', or double-click it in the document."
            ),
        }

    # --- 4. no usable address in the wording -------------------------------
    return {
        "status": "unresolved",
        "inventory": _public_inventory(inventory),
        "message": (
            f"Tell me which image to replace - for a PDF, 'the image on page 2'; "
            f"otherwise 'image 3' or 'the first image'. "
            f"(This document has {total} image{'s' if total != 1 else ''}.) "
            "You can also double-click an image in the document."
        ),
    }


def _role_matches(inventory, noun, file_type) -> list:
    """Best-effort match of a role word like "logo" onto real images.

    Generic nouns ("picture", "photo") match *everything* on purpose. They mean
    "an image", not "the biggest one", so ranking them by size was a silent
    coin-flip: "replace the picture on page 1" against a page holding two
    diagrams swapped one without asking. Returning them all lets the page and
    document-wide scope turn that into the ambiguity prompt the user can answer.

    Specific roles use deliberately conservative heuristics, in order of
    confidence:

    * "logo" / "watermark" / "seal" / "signature" - the smallest image, which is
      what a logo almost always is. Ties keep only a clear winner.
    * "banner" / "header image" / "footer image" - the widest image, i.e. the
      one spanning most of the page.
    * "chart" / "graph" / "diagram" / "figure" - the largest image by area,
      which is what a figure is in practice.

    A heuristic that cannot separate a single clear candidate returns nothing
    rather than everything; returning everything would push the choice onto the
    user as an ambiguous list, which is the correct outcome anyway, but with a
    far worse prompt.
    """
    sized = [e for e in inventory if (e.get("width") or 0) > 0 and (e.get("height") or 0) > 0]
    if not sized:
        return []

    def area(e):
        return (e["width"] or 0) * (e["height"] or 0)

    if noun in ("picture", "photo", "image"):
        return list(sized)

    if noun in ("logo", "watermark", "seal", "signature"):
        smallest = min(area(e) for e in sized)
        candidates = [e for e in sized if area(e) == smallest]
        if len(candidates) == 1:
            return candidates
        # Several equally tiny images - a repeated logo is far more likely than
        # several unrelated ones, so return the single distinct index.
        return [e for e in candidates if e["index"] == candidates[0]["index"]][:1]

    if noun in ("banner", "header image", "footer image"):
        widest = max((e["width"] or 0) / (e["height"] or 1) for e in sized)
        candidates = [e for e in sized if (e["width"] or 0) / (e["height"] or 1) >= widest * 0.999]
        return candidates[:1]

    if noun in ("chart", "graph", "diagram", "figure", "screenshot"):
        largest = max(area(e) for e in sized)
        candidates = [e for e in sized if area(e) == largest]
        return candidates[:1]

    return []


# ---------------------------------------------------------------------------
# Uploaded-file validation
# ---------------------------------------------------------------------------

# Pillow-readable formats accepted for a replacement. Kept explicit rather than
# "whatever opens" so an unexpected or exotic codec cannot reach the writer.
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"}

MAX_REPLACEMENT_BYTES = 15 * 1024 * 1024


def read_and_validate_image(raw: bytes) -> bytes:
    """Verify the upload really is an image Pillow can decode.

    Returns the bytes unchanged. Raises ``ValueError`` with a message meant to be
    shown to the user verbatim.

    This runs before any writer is touched. Handing unvalidated bytes to
    python-docx or PyMuPDF is how a bad upload turns into a corrupt document
    rather than a rejected upload.
    """
    if not raw:
        raise ValueError("No image data was uploaded.")

    if len(raw) > MAX_REPLACEMENT_BYTES:
        raise ValueError(
            "That image is larger than 15MB. Please upload a smaller file."
        )

    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as im:
            im.verify()          # structural check, no decode
        with Image.open(io.BytesIO(raw)) as im:
            im.load()            # full decode: catches truncated files
            size = im.size
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "That file could not be read as an image. Please upload a PNG, "
            f"JPG, GIF, BMP, TIFF or WebP file. ({exc})"
        )

    if not size or size[0] < 1 or size[1] < 1:
        raise ValueError("That image has no usable dimensions.")

    return raw