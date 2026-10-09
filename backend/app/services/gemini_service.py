"""RapidDoc AI orchestration layer.

The AI stack is a 3-tier cascade so the app keeps working even when a
component fails:

  1. Local fine-tuned brain models
     (DistilBERT intent + T5 rewriter + BART MCQ generator + BART summarizer)
  2. Google Gemini API                     (fallback when a model is unsure/fails)
  3. Deterministic regex rule engine       (final fallback)

Command understanding:
    understand_command()  -> {"action": "replace", "find_text", "replace_text"}
                           or {"action": "header"|"footer", "new_text"}
                           or {"action": "replace_image"}   (swap a picture for an upload)
                           or {"action": "summarize"|"generate_mcq", ...}
                           or {"action": "unknown"}

    "replace_image" carries no index or filename by design. The target is
    resolved by image_resolver.resolve_image_targets against the document's real
    image list, which validates every number before anything is written.

Generation:
    rewrite_text()        -> {"rewritten_text", "engine", "message"}
    summarize_document()  -> {"summary", "engine", "message"}
    generate_mcqs()       -> {"questions", "engine", "message"}
"""

import json
import logging
import re

from RapidDoc.backend.app.config import settings
from RapidDoc.backend.app.services.local_models import (
    brain_status,
    chunk_text_for_mcq,
    classify_intent,
    generate_mcq,
    intent_confidence_threshold,
    rewrite_text_locally,
    summarize,
)
from RapidDoc.backend.app.services.document_text import clean_prose, split_prose_sentences
from RapidDoc.backend.app.services.mcq_generator import build_mcq_set
from RapidDoc.backend.app.services.slot_extractor import extract_slots
from RapidDoc.backend.app.services.text_polish import (
    ensure_sentence,
    polish_sentences,
    polish_text,
    split_sentences,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex rule engine (final fallback)
# ---------------------------------------------------------------------------
FALLBACK_HEADER_RE = re.compile(
    r'''(?:^(?:change|set|update|make|add|put)\s+(?:the\s+)?header\s+(?:to|into|as|:)\s+["'“”]?(.+?)['"“”]?\.?$|^header\s*:\s*["'“”]?(.+?)['"“”]?\.?$)''',
    re.IGNORECASE,
)
FALLBACK_FOOTER_RE = re.compile(
    r'''(?:^(?:change|set|update|make|add|put)\s+(?:the\s+)?footer\s+(?:to|into|as|:)\s+["'“”]?(.+?)['"“”]?\.?$|^footer\s*:\s*["'“”]?(.+?)['"“”]?\.?$)''',
    re.IGNORECASE,
)
FALLBACK_REPLACE_PATTERNS = [
    # 1. "find X and replace with Y" / "search for X and replace with Y" / "find X replace with Y"
    re.compile(
        r'''^\s*(?:please\s+|kindly\s+)?(?:find|search(?:\s+for)?)\s+[\"'“”`]?(.+?)[\"'“”`]?\s+(?:and\s+)?(?:replace|repalce|relpace|change|c?hange|chnage|cahnge|swap|substitute)(?:\s+it)?\s+(?:with|to|by|for|into|as)\s+[\"'“”`]?(.+?)[\"'“”`]?\.?\s*$''',
        re.IGNORECASE,
    ),
    # 2. "swap X for Y" / "swap X with Y" / "substitute X for/with Y"
    re.compile(
        r'''^\s*(?:please\s+|kindly\s+)?(?:swap|substitute)\s+(?:the\s+)?[\"'“”`]?(.+?)[\"'“”`]?\s+(?:with|for|to|by|into|as)\s+[\"'“”`]?(.+?)[\"'“”`]?\.?\s*$''',
        re.IGNORECASE,
    ),
    # 3. Arrow replacement: "replace X -> Y" / "change X -> Y" / "X -> Y"
    re.compile(
        r'''^\s*(?:(?:change|c?hange|chnage|cahnge|replace|repalce|relpace|edit|update|swap)\s+)?[\"'“”`]?([^'\"“”`\n\r\->]+?)[\"'“”`]?\s*(?:->|=>)\s*[\"'“”`]?([^'\"“”`\n\r]+?)[\"'“”`]?\.?\s*$''',
        re.IGNORECASE,
    ),
    # 4. Standard "change/replace/edit X to/with/by/into/for Y" (handles typos like 'hange', colons, 'from X to Y')
    re.compile(
        r'''^\s*(?:please\s+|kindly\s+)?(?:change|c?hange|chnage|cahnge|replace|repalce|relpace|edit|update|switch|turn|modify|convert)(?:\s*:|\s+from)?\s+(?:the\s+)?(?:word|phrase|text|number|value)?\s*[\"'“”`]?(.+?)[\"'“”`]?\s+(?:to|with|by|into|for|as)\s+[\"'“”`]?(.+?)[\"'“”`]?\.?\s*$''',
        re.IGNORECASE,
    ),
]
FALLBACK_REPLACE_RE = FALLBACK_REPLACE_PATTERNS[3]

# Robust tier-3 patterns for generative intents: summarize, quiz, rewrite
FALLBACK_SUMMARIZE_RE = re.compile(
    r"\b(?:summar(?:y|ies|i[sz]e|i[sz]ation|i[sz]ing)|abstract|overview|tl;?dr|recap|briefing)\b",
    re.IGNORECASE,
)
FALLBACK_SUMMARIZE_PAGE_RE = re.compile(
    r"\bpage\s+(\d+|first|last|cover)\b", re.IGNORECASE
)
FALLBACK_MCQ_RE = re.compile(
    r"\b(?:mcqs?|multiple[\s-]choice(?:\s+questions?)?|questions?|quiz(?:zes)?|test\s+questions?|assessment)\b",
    re.IGNORECASE,
)
FALLBACK_REWRITE_RE = re.compile(
    r"\b(?:rewrite|rephrase|paraphrase|proofread|correct|fix\s+grammar|improve\s+writing|make\s+(?:it|this|that)?\s*(?:more\s+)?(?:formal|casual|concise|professional|clearer|shorter|better)|shorten|expand|make\s+(?:it|this)\s+(?:shorter|longer))\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"\b(\d+)\b")

# "replace the logo", "swap the image on page 2", "change the picture".
FALLBACK_REPLACE_IMAGE_RE = re.compile(
    r"\b(?:image|picture|photo|figure|diagram|logo|graphic|chart|icon|"
    r"watermark|banner|thumbnail)\b",
    re.IGNORECASE,
)

_STRIP_CHARS = " \t\r\n'\"“”`"


COLOR_NAME_TO_RGB = {
    "dark blue": (0, 32, 96),
    "navy": (0, 0, 128),
    "blue": (0, 102, 204),
    "royal blue": (65, 105, 225),
    "light blue": (173, 216, 230),
    "red": (192, 0, 0),
    "dark red": (128, 0, 0),
    "crimson": (220, 20, 60),
    "green": (0, 128, 0),
    "dark green": (0, 80, 0),
    "emerald": (46, 139, 87),
    "black": (0, 0, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "dark gray": (64, 64, 64),
    "purple": (112, 48, 160),
    "orange": (237, 125, 49),
    "teal": (0, 128, 128),
    "gold": (218, 165, 32),
}

_ORDINALS_MAP = {
    "first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
    "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "sixth": 5, "6th": 5,
    "seventh": 6, "7th": 6, "eighth": 7, "8th": 7, "ninth": 8, "9th": 8, "tenth": 9, "10th": 9,
    "last": -1, "final": -1,
}

UNIVERSAL_ACTIONS = {
    "replace", "header", "footer", "replace_image", "image_module",
    "style_headings", "style_document", "delete_column", "delete_row", "delete_table",
    "delete_image", "resize_image", "describe_image", "add_caption",
    "summarize", "generate_mcq", "rewrite", "qa_extract", "composite",
    "generate_presentation"
}


def _extract_exact_replacement(prompt: str) -> dict | None:
    """Exact quoted direct replacement extractor.
    Guarantees 100% exact character preservation: no paraphrasing,
    no punctuation dropping, no case alteration.
    e.g. Replace 'ABC Corporation' with 'ABC Corp.' -> find: 'ABC Corporation', repl: 'ABC Corp.'
    """
    p = prompt.strip()
    quotes = re.findall(r'''['"“”`]([^'"“”`]+)['"“”`]''', p)
    if len(quotes) >= 2 and re.search(r"\b(?:replace|repalce|relpace|change|swap|substitute|switch|find)\b", p, re.I):
        replace_all = bool(re.search(r"\b(?:all|every|each)\b", p, re.I))
        return {
            "action": "replace",
            "find_text": quotes[0],
            "replace_text": quotes[1],
            "replace_all": replace_all,
            "engine": "exact_quoted_rule",
        }
    return None


def _clean_find_text(value: str) -> str:
    """Drop filler words and syntax markers that accidentally get captured as the find text."""
    if not value:
        return ""
    v = value.strip(_STRIP_CHARS)
    v = re.sub(
        r"^(?:(?:all|every|any)\s+(?:instances?|occurrences?)\s+of\s+|"
        r"(?:all|every|any)\s+(?:the\s+)?(?:word|words|phrase|phrases|text|string|terms?|value|values|number|numbers)?\s*|"
        r"from\s+|"
        r"(?:the\s+)?(?:word|words|phrase|phrases|text|string|term|terms|value|values|number|numbers)\s+(?:of\s+)?|"
        r"the\s+)",
        "",
        v,
        flags=re.I,
    )
    return v.strip(_STRIP_CHARS)


def _clean_replace_text(value: str) -> str:
    """Drop filler words and trailing document scopes that get captured as replace text."""
    if not value:
        return ""
    v = value.strip(_STRIP_CHARS)
    v = re.sub(
        r"\s+(?:in\s+(?:the\s+|all\s+|this\s+)?(?:document|doc|file|text|page)|everywhere|across\s+(?:the\s+)?(?:document|doc|file|whole\s+document)|throughout\s+(?:the\s+)?(?:document|doc|file))\s*$",
        "",
        v,
        flags=re.I,
    )
    v = re.sub(
        r"^(?:(?:to|with|into|by|as|for)\s+)?(?:the\s+)?(?:word|words|phrase|phrases|text|string|term|terms|value|values|number|numbers)\s+(?:of\s+)?",
        "",
        v,
        flags=re.I,
    )
    return v.strip(_STRIP_CHARS)


def _fallback_table_action(prompt: str) -> dict | None:
    p = prompt.strip()
    # 1. Delete/remove column
    m_col = re.search(r"\b(?:delete|remove|drop)\s+(?:the\s+)?(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|last)\s+col(?:umn)?(?:\s+(?:from|in)\s+(?:all\s+tables|every\s+table|(?:the\s+)?(\d+|first|1st|second|2nd|third|3rd)\s+table|table\s+(\d+)))?\b", p, re.I)
    if m_col:
        raw_idx = m_col.group(1).lower()
        col_idx = _ORDINALS_MAP.get(raw_idx)
        if col_idx is None:
            col_idx = int(raw_idx) - 1 if raw_idx.isdigit() else 0
        tbl_match = m_col.group(2) or m_col.group(3)
        if tbl_match:
            tbl_idx = _ORDINALS_MAP.get(tbl_match.lower())
            if tbl_idx is None:
                tbl_idx = int(tbl_match) - 1 if tbl_match.isdigit() else 0
        else:
            tbl_idx = "all"
        return {
            "action": "delete_column",
            "column_index": col_idx,
            "col_index": col_idx,
            "table_index": tbl_idx,
            "engine": "rule",
        }

    # 2. Delete/remove row
    m_row = re.search(r"\b(?:delete|remove|drop)\s+(?:the\s+)?(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\s+row(?:\s+(?:from|in)\s+(?:all\s+tables|every\s+table|(?:the\s+)?(\d+|first|1st|second|2nd|third|3rd)\s+table|table\s+(\d+)))?\b", p, re.I)
    if m_row:
        raw_idx = m_row.group(1).lower()
        row_idx = _ORDINALS_MAP.get(raw_idx)
        if row_idx is None:
            row_idx = int(raw_idx) - 1 if raw_idx.isdigit() else 0
        tbl_match = m_row.group(2) or m_row.group(3)
        if tbl_match:
            tbl_idx = _ORDINALS_MAP.get(tbl_match.lower())
            if tbl_idx is None:
                tbl_idx = int(tbl_match) - 1 if tbl_match.isdigit() else 0
        else:
            tbl_idx = "all"
        return {
            "action": "delete_row",
            "row_index": row_idx,
            "table_index": tbl_idx,
            "engine": "rule",
        }

    # 3. Delete table
    m_tbl = re.search(r"\b(?:delete|remove|drop)\s+(?:all\s+)?tables?(?:\s+(\d+))?\b", p, re.I)
    if m_tbl:
        tbl_idx = int(m_tbl.group(1)) - 1 if m_tbl.group(1) else "all"
        return {
            "action": "delete_table",
            "table_index": tbl_idx,
            "engine": "rule",
        }
    return None


def _fallback_heading_action(prompt: str) -> dict | None:
    p = prompt.strip()
    # Support headings, headers, titles, subheadings, and typos like 'ahange' for 'change'
    has_heading_target = bool(re.search(r"\b(?:headings?|headers?|titles?|subheadings?)\b", p, re.I))
    if not has_heading_target:
        return None

    # Detect color
    color = None
    color_rgb = None
    for cname, rgb in COLOR_NAME_TO_RGB.items():
        if re.search(rf"\b{re.escape(cname)}\b", p, re.I):
            color = cname
            color_rgb = rgb
            break

    bold = True if re.search(r"\bbold\b", p, re.I) else None
    italic = True if re.search(r"\bitalic\b", p, re.I) else None

    size = None
    m_size = re.search(r"\b(?:font[\s-]size|size)\s*(?:to\s*|:\s*)?(\d+(?:\.\d+)?)\s*(?:pt|px)?\b", p, re.I)
    if not m_size:
        m_size = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:pt|px)\b", p, re.I)
    if m_size:
        size = float(m_size.group(1))

    font_name = None
    for fn in ("Arial", "Times New Roman", "Calibri", "Courier New", "Georgia", "Inter", "Verdana", "Roboto", "Helvetica"):
        if re.search(rf"\b{re.escape(fn)}\b", p, re.I):
            font_name = fn
            break

    # If any styling attribute is recognized or styling verbs are used
    if color or bold or italic or size or font_name:
        level = None
        m_lvl = re.search(r"\b(?:heading|header|h)\s*([1-6])\b", p, re.I)
        if m_lvl:
            level = int(m_lvl.group(1))

        return {
            "action": "style_headings",
            "color": color,
            "color_rgb": color_rgb,
            "bold": bold,
            "italic": italic,
            "font_size": size,
            "font_name": font_name,
            "level": level,
            "engine": "rule",
        }
    return None


def _fallback_document_styling_action(prompt: str) -> dict | None:
    p = prompt.strip()
    # If the user specifically targeted headings or headers, let _fallback_heading_action handle it
    if re.search(r"\b(?:headings?|headers?|titles?|subheadings?)\b", p, re.I):
        return None

    font_name = None
    for fn in ("Arial", "Times New Roman", "Calibri", "Courier New", "Georgia", "Inter", "Verdana", "Roboto", "Helvetica"):
        if re.search(rf"\b{re.escape(fn)}\b", p, re.I):
            font_name = fn
            break

    size = None
    m_size = re.search(r"\b(?:font[\s-]size|size)\s*(?:to\s*|:\s*)?(\d+(?:\.\d+)?)\s*(?:pt|px)?\b", p, re.I)
    if not m_size:
        m_size = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:pt|px)\b", p, re.I)
    if m_size:
        size = float(m_size.group(1))

    spacing = None
    m_spacing = re.search(r"\bline[\s-]spacing\s*(?:to\s*|:\s*)?(\d+(?:\.\d+)?)\b", p, re.I)
    if m_spacing:
        spacing = float(m_spacing.group(1))

    has_style_indicator = bool(re.search(r"\b(?:font|text|style|format|size|spacing|document)\b", p, re.I))
    if (font_name or size or spacing) and (has_style_indicator or re.search(r"\b(?:change|ahange|chagne|make|set)\b", p, re.I)):
        return {
            "action": "style_document",
            "font_name": font_name,
            "font_size": size,
            "line_spacing": spacing,
            "engine": "rule",
        }
    return None


def _fallback_image_action(prompt: str, has_image_upload: bool = False) -> dict | None:
    p = prompt.strip()
    if re.search(r"\b(?:delete|remove|clear)\s+(?:all\s+)?(?:images?|pictures?|photos?)\b", p, re.I):
        return {"action": "delete_image", "image_index": "all", "image_indexes": None, "engine": "rule"}
    if re.search(r"\b(?:describe|explain|what\s+is\s+in|read)\s+(?:this\s+)?(?:image|picture|photo|diagram|chart)\b", p, re.I):
        return {"action": "describe_image", "query": p, "engine": "rule"}

    # Image resize commands: "resize image 1 to 4 in", "make image 1 original size", "resize image"
    if re.search(r"\b(?:resize|scale|enlarge|shrink|make\s+(?:the\s+)?image\s+(?:bigger|smaller|original(?:\s+size)?)|image\s+size|adjust\s+image)\b", p, re.I):
        img_idx = 0
        m_idx = re.search(r"\b(?:image|picture|photo)\s*(?:#|number\s*)?(\d+)\b", p, re.I)
        if m_idx:
            img_idx = max(0, int(m_idx.group(1)) - 1)
        elif re.search(r"\bfirst\s+(?:image|picture|photo)\b", p, re.I):
            img_idx = 0
        elif re.search(r"\bsecond\s+(?:image|picture|photo)\b", p, re.I):
            img_idx = 1
        elif re.search(r"\bthird\s+(?:image|picture|photo)\b", p, re.I):
            img_idx = 2

        # Check unit
        unit = "px"
        if re.search(r"\b(?:in|inch|inches)\b", p, re.I):
            unit = "in"
        elif re.search(r"\bcm\b", p, re.I):
            unit = "cm"
        elif re.search(r"\bpt\b", p, re.I):
            unit = "pt"
        elif re.search(r"\bmm\b", p, re.I):
            unit = "mm"

        # Check width / height
        width = None
        height = None
        m_w = re.search(r"\bwidth\s*(?:to\s*|:\s*)?(\d+(?:\.\d+)?)(?:\s*(?:in|inch|inches|px|cm|pt|mm))?", p, re.I)
        if m_w:
            width = float(m_w.group(1))
        m_h = re.search(r"\bheight\s*(?:to\s*|:\s*)?(\d+(?:\.\d+)?)(?:\s*(?:in|inch|inches|px|cm|pt|mm))?", p, re.I)
        if m_h:
            height = float(m_h.group(1))

        if width is None and height is None:
            # Check for general size like "to 4 inches" or "to 400px" or "width 350"
            m_size = re.search(r"\b(?:to|by|size)\s*(\d+(?:\.\d+)?)(?:\s*(?:in|inch|inches|px|cm|pt|mm))?", p, re.I)
            if not m_size:
                m_size = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:in|inch|inches|px|cm|pt|mm)\b", p, re.I)
            if m_size:
                width = float(m_size.group(1))

        new_page = bool(re.search(r"\b(?:new\s+page|page\s*break|next\s+page)\b", p, re.I))

        return {
            "action": "resize_image",
            "image_index": img_idx,
            "width": width,
            "height": height,
            "unit": unit,
            "new_page": new_page,
            "engine": "rule",
        }

    # Move image to new page
    if re.search(r"\b(?:move|put|push)\s+(?:the\s+)?(?:image|picture|photo)(?:\s*#?\s*\d+)?\s*(?:to\s+)?(?:new\s+page|next\s+page)\b", p, re.I):
        img_idx = 0
        m_idx = re.search(r"\b(?:image|picture|photo)\s*(?:#|number\s*)?(\d+)\b", p, re.I)
        if m_idx:
            img_idx = max(0, int(m_idx.group(1)) - 1)
        return {
            "action": "resize_image",
            "image_index": img_idx,
            "new_page": True,
            "engine": "rule",
        }


def _fallback_qa_action(prompt: str) -> dict | None:
    p = prompt.strip()
    if re.search(r"\b(?:what\s+is\s+this\s+document\s+about|tell\s+me\s+what\s+this\s+document\s+is\s+about|find\s+(?:the\s+)?important\s+points|create\s+study\s+notes|key\s+takeaways?|main\s+points?|compare\s+(?:these|the)\s+two\s+sections)\b", p, re.I):
        return {"action": "qa_extract", "query": p, "engine": "rule"}
    return None


FALLBACK_PPT_RE = re.compile(
    r"\b(?:generate|create|make|export|convert|build|produce|design)\s+(?:to\s+|into\s+)?(?:a\s+|an\s+)?(?:presentation|ppt|pptx|slide\s*deck|slides|deck)\b|"
    r"\b(?:presentation|ppt|pptx|slide\s*deck|slides)\s+(?:generation|generator|builder|maker)\b|"
    r"\b(?:turn|transform)\s+(?:this\s+)?(?:doc|document|it)?\s*(?:in)?to\s+(?:a\s+)?(?:ppt|pptx|presentation|slides|deck)\b",
    re.I
)


def _fallback_presentation_action(prompt: str) -> dict | None:
    p = prompt.strip()
    if FALLBACK_PPT_RE.search(p):
        theme = "modern"
        p_lower = p.lower()
        if "corporate" in p_lower:
            theme = "corporate"
        elif "minimal" in p_lower or "clean" in p_lower:
            theme = "minimal"
        return {
            "action": "generate_presentation",
            "theme": theme,
            "engine": "rule",
        }
    return None


def _fallback_intent(prompt: str, has_image_upload: bool = False, selection: dict = None) -> dict:
    # 0. Direct exact replacement
    exact_repl = _extract_exact_replacement(prompt)
    if exact_repl:
        return exact_repl

    # Presentation generation
    ppt_act = _fallback_presentation_action(prompt)
    if ppt_act:
        return ppt_act

    # Table manipulation
    table_act = _fallback_table_action(prompt)
    if table_act:
        return table_act

    # Heading styling (handles "change all header to blue", "make headings bold", etc.)
    heading_act = _fallback_heading_action(prompt)
    if heading_act:
        return heading_act

    # Document styling (handles "change font to Arial", "font size 12", etc.)
    doc_style_act = _fallback_document_styling_action(prompt)
    if doc_style_act:
        return doc_style_act

    # Image actions
    img_act = _fallback_image_action(prompt, has_image_upload)
    if img_act:
        return img_act

    # QA / Key points
    qa_act = _fallback_qa_action(prompt)
    if qa_act:
        return qa_act

    m = FALLBACK_HEADER_RE.search(prompt)
    if m:
        val = (m.group(1) or m.group(2) or "").strip()
        val_clean = val.lower().rstrip(".")
        if val_clean in COLOR_NAME_TO_RGB:
            return {
                "action": "style_headings",
                "color": val_clean,
                "color_rgb": COLOR_NAME_TO_RGB[val_clean],
                "engine": "rule",
            }
        if val:
            return {"action": "header", "new_text": val}
    m = FALLBACK_FOOTER_RE.search(prompt)
    if m:
        val = m.group(1) or m.group(2)
        if val:
            return {"action": "footer", "new_text": val.strip()}

    if re.match(r"^/?images?\b", prompt.strip(), re.I) or re.search(r"\b(?:list|show|detect|inspect|view)\s+(?:all\s+)?images\b", prompt, re.I):
        return {"action": "image_module"}

    if has_image_upload and (FALLBACK_REPLACE_IMAGE_RE.search(prompt) or re.search(r"\b(?:repl[a-z]*|swap|put|change)\b.*?\b\d+\b", prompt, re.I)):
        return {"action": "replace_image"}

    for r in FALLBACK_REPLACE_PATTERNS:
        m = r.match(prompt.strip())
        if m:
            find_txt = _clean_find_text(m.group(1))
            repl_txt = _clean_replace_text(m.group(2))
            if find_txt and repl_txt:
                return {
                    "action": "replace",
                    "find_text": find_txt,
                    "replace_text": repl_txt,
                }

    if FALLBACK_MCQ_RE.search(prompt):
        count = 5
        cm = _COUNT_RE.search(prompt)
        if cm:
            try:
                count = int(cm.group(1))
            except ValueError:
                count = 5
        return {
            "action": "generate_mcq",
            "num_questions": max(1, min(count, int(settings.MCQ_MAX_QUESTIONS))),
        }
    if FALLBACK_SUMMARIZE_RE.search(prompt):
        pm = FALLBACK_SUMMARIZE_PAGE_RE.search(prompt)
        page = None
        if pm:
            raw = pm.group(1).lower()
            page = int(raw) if raw.isdigit() else raw
        return {
            "action": "summarize",
            "scope": "page" if page is not None else "document",
            "page": page,
            "length": next(
                (key for key, _ in SUMMARY_LENGTH_HINTS if key in prompt.lower()), None
            ),
        }
    if FALLBACK_REWRITE_RE.search(prompt) or GRAMMAR_INTENT_RE.search(prompt) or (selection and selection.get("text") and re.search(r"\b(?:make|turn|change|convert|transform|improve|shorten|expand|translate|rewrite)\b", prompt, re.I)):
        return {
            "action": "rewrite",
            "instruction": prompt.strip(),
            "scope": "selection" if (selection and selection.get("text")) else "document",
            "source_text": selection.get("text") if selection else None,
        }
    return {"action": "unknown"}


# ---------------------------------------------------------------------------
# Gemini Universal Orchestrator Layer
# ---------------------------------------------------------------------------
UNIVERSAL_INTENT_PROMPT = """You are the Universal Command Engine for RapidDoc, an AI document editing platform.
Analyze the user's natural language command, conversational context, and active document selection. Return strictly valid JSON only.

Supported Universal Actions:

1. Direct text replacement:
   {"action": "replace", "find_text": "...", "replace_text": "..."}
   CRITICAL: Extract find_text and replace_text EXACTLY character-for-character. Do NOT paraphrase, do NOT alter capitalization, do NOT remove punctuation.

2. Header and Footer:
   {"action": "header", "new_text": "..."}
   {"action": "footer", "new_text": "..."}

3. Heading styling:
   {"action": "style_headings", "font_size": 20, "bold": true, "italic": false, "color": "dark blue", "font_name": "Calibri", "level": null}
   (Only include fields mentioned or implied; e.g. "make headings bold" -> {"action": "style_headings", "bold": true}; "change all header to blue" or "headers to red" -> {"action": "style_headings", "color": "blue"}. NOTE: "change header(s) to blue/red/green", "headers font 16" refers to HEADING styling, NOT page running header text).

4. Document styling:
   {"action": "style_document", "font_name": "Times New Roman", "font_size": 12}

5. Table manipulation:
   {"action": "delete_column", "col_index": 1, "table_index": null}  # 0-based col_index: 0=1st, 1=2nd, 2=3rd, -1=last column. table_index=null means all tables.
   {"action": "delete_row", "row_index": 0, "table_index": null}     # 0-based row_index: 0=1st, -1=last row.
   {"action": "delete_table", "table_index": null}                   # table_index=null means all tables.

6. Image operations:
   {"action": "replace_image"}
   {"action": "delete_image", "image_indexes": null}                 # null means all images.
   {"action": "resize_image", "width": 3.0, "unit": "in", "image_index": 0}
   {"action": "describe_image", "query": "..."}

7. Document comprehension & generative:
   {"action": "summarize", "scope": "document"|"page", "length": "5 points"|"brief"|"detailed", "page": null}
   {"action": "generate_mcq", "num_questions": 10, "topic": null}
   {"action": "rewrite", "instruction": "...", "scope": "selection"|"paragraph"|"document"}
   {"action": "qa_extract", "query": "..."}  # for "What is this about?", "Find important points", "Create study notes"

8. Mixed / Composite Multi-Step Commands:
   If the user asks for multiple distinct operations in one instruction (e.g. "Replace X with Y, make headings bold, and summarize in 5 points"):
   {"action": "composite", "actions": [
       {"action": "replace", "find_text": "...", "replace_text": "..."},
       {"action": "style_headings", "bold": true},
       {"action": "summarize", "length": "5 points"}
   ]}

9. Presentation & Slide Deck Generation:
   {"action": "generate_presentation", "theme": "modern"|"corporate"|"minimal"}
   (Use for commands requesting a presentation or slides, e.g. "generate a presentation", "make a ppt", "turn this document into slides", "create ppt in corporate theme")

Rules:
- Resolve references ("this", "it", "that", "the previous section") using the conversation history and current selection.
- If selected text is present and user says "make this professional", set action="rewrite" and target="selection".
- Strictly valid JSON only, no markdown formatting fences.
"""
INTENT_PROMPT = UNIVERSAL_INTENT_PROMPT


REWRITE_PROMPT = """You are the text rewriting engine for RapidDoc, a document editing app.
Rewrite ONLY the single provided text block following the user's instruction.
CRITICAL CONSTRAINTS:
1. Rewrite ONLY the exact text given below. Do NOT import, mention, or combine any content from other paragraphs, sections, or the rest of the document.
2. Maintain the exact same paragraph structure. Do NOT combine multiple paragraphs, split into bullet points, or add section headings unless explicitly instructed.
3. Keep core meaning, numbers, named entities, dates, and factual details intact while executing the requested transformation (e.g. simplifying, polishing, or changing tone).
4. The output length should be similar to the input length. Responses more than 3x longer than the input are REJECTED as hallucinations.
5. Return strictly the rewritten text and nothing else. No preamble, no labels like "Rewritten:", no markdown fences."""

# Requests that mean "fix the grammar", not "rewrite this". The local T5 brain
# paraphrases for CoEdIT-style prefixes, which is wrong for proofreading: it
# changes wording the user never asked to change. These are handled by the
# deterministic polisher instead, which only repairs surface errors.
GRAMMAR_INTENT_RE = re.compile(
    r"\b(gramma\w*|spell\w*|typos?|proofread\w*|punctuat\w*|"
    r"correct\s+(?:the\s+|this\s+|my\s+|these\s+)?(?:sentence|grammar|text|writing|errors?)|"
    r"fix\s+(?:the\s+|this\s+|my\s+)?(?:sentence|grammar|text|writing|errors?|typos?)|"
    r"sentence\s+casing|capitali[sz]ation)\b",
    re.IGNORECASE,
)

TEXT_REWRITE_STYLE_MAP = [
    (re.compile(r"\b(gramma|grammatical|grammatically|spelling|typos?)\b", re.I),
     "Remove all grammatical errors from this text"),
    (re.compile(r"\bformal|professional|academic\b", re.I),
     "Make this more formal"),
    (re.compile(r"\b(simpl|easier|easy-to-read|plain)\b", re.I),
     "Simplify this text"),
    (re.compile(r"\b(concis|shorter|short|brief)\b", re.I),
     "Make this more concise"),
    (re.compile(r"\b(casual|friendly|informal|conversation)\b", re.I),
     "Make this more casual"),
    (re.compile(r"\b(vivid|engaging|interesting|descriptive)\b", re.I),
     "Make this more vivid"),
]


def _normalize_instruction(instruction: str) -> str:
    """Map a free-form user instruction onto the CoEdIT-style prefixes the
    local T5 brain was fine-tuned with."""
    instruction = (instruction or "").strip()
    lowered = instruction.lower()
    for regex, mapped in TEXT_REWRITE_STYLE_MAP:
        if regex.search(lowered):
            return mapped
    return instruction or "Improve the text"


def _gemini_client():
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key or api_key in ("YOUR_GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE"):
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(
            settings.GEMINI_MODEL,
            generation_config={"temperature": 0.0},
        )
    except Exception as exc:
        logger.error("Gemini client setup failed: %s", exc)
        return None


def _understand_with_gemini(
    prompt: str,
    has_image_upload: bool = False,
    history: list = None,
    selection: dict = None,
    image_base64: str = None,
):
    model = _gemini_client()
    if model is None:
        return None
    try:
        context_parts = []
        if has_image_upload or image_base64:
            context_parts.append("Note: The user has attached or pasted an image with this command.")
        if selection:
            context_parts.append(f"Active User Selection: {json.dumps(selection)}")
        if history:
            recent_turns = history[-5:]
            context_parts.append(f"Recent Conversation History (for resolving references like 'it', 'this', 'that'): {json.dumps(recent_turns)}")

        context_str = ("\n\nContext:\n" + "\n".join(context_parts)) if context_parts else ""
        full_prompt = f"{UNIVERSAL_INTENT_PROMPT}{context_str}\n\nUser command: {prompt}"

        m = model.generate_content(
            full_prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
        )
        intent = _parse_intent_from_json(m.text)
        action = intent.get("action")
        if action in UNIVERSAL_ACTIONS or action == "composite":
            logger.info("Gemini parsed command '%s' as %s", prompt, intent)
            intent["engine"] = "gemini"
            return intent
        logger.warning("Gemini returned unexpected intent for '%s': %s", prompt, intent)
    except Exception as exc:
        logger.error("Gemini command understanding failed, falling back to rules: %s", exc)
    return None



def _rewrite_with_gemini(instruction: str, text: str):
    model = _gemini_client()
    if model is None:
        return None
    try:
        m = model.generate_content(
            f"{REWRITE_PROMPT}\n\nInstruction: {instruction}\n\nText: {text}"
        )
        rewritten = (m.text or "").strip()
        return rewritten or None
    except Exception as exc:
        logger.error("Gemini text rewrite failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Intent <-> backend action mapping
# ---------------------------------------------------------------------------
# Intents the document engine can act on right now.
ACTIONABLE_INTENTS = {
    "replace_text": "replace",
    "change_header": "header",
    "change_footer": "footer",
    "summarize_document": "summarize",
    "summarize_page": "summarize",
    "generate_mcq": "generate_mcq",
}

# Intents that mean "summarise", and whether a specific page was named.
SUMMARIZE_INTENTS = {"summarize_document": "document", "summarize_page": "page"}

# User phrasing -> how many generated tokens the summary may use.
SUMMARY_LENGTH_HINTS = [
    ("one-paragraph", None),
    ("detailed", 160),
    ("medium", 128),
    ("brief", 64),
    ("short", 48),
]


def _parse_intent_from_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"action": "unknown"}


def _local_intent_to_response(prompt: str, intent: str) -> dict:
    """Convert a local-model intent (+ extracted slots) into the action schema.
    Returns None when the intent is not actionable or required slots are
    missing (so the caller can fall back to Gemini / regex)."""
    action = ACTIONABLE_INTENTS.get(intent)
    if not action:
        return None
    slots = extract_slots(prompt, intent)
    if action == "replace":
        find_text = _clean_find_text(slots.get("old_text") or slots.get("target_text") or "")
        replace_text = _clean_replace_text(slots.get("new_text") or "")
        if not find_text or not replace_text:
            return None
        return {
            "action": "replace",
            "intent": intent,
            "find_text": find_text,
            "replace_text": replace_text,
            "engine": "local",
        }
    if action in ("header", "footer"):
        new_text = (slots.get("new_text") or "").strip()
        if not new_text:
            return None
        return {
            "action": action,
            "intent": intent,
            "new_text": new_text,
            "engine": "local",
        }
    if action == "summarize":
        scope = SUMMARIZE_INTENTS[intent]
        return {
            "action": "summarize",
            "intent": intent,
            "scope": scope,
            "page": slots.get("page") if scope == "page" else None,
            "length": slots.get("length"),
            "engine": "local",
        }
    if action == "generate_mcq":
        count = slots.get("num_questions") or 5
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 5
        return {
            "action": "generate_mcq",
            "intent": intent,
            "num_questions": max(1, min(count, int(settings.MCQ_MAX_QUESTIONS))),
            "engine": "local",
        }
    return None


def understand_command(
    prompt: str,
    has_image_upload: bool = False,
    history: list = None,
    selection: dict = None,
    image_base64: str = None,
) -> dict:
    """Understand any natural-language command using the Universal Command Engine.

    Execution priority:
    1. Exact direct replacement (100% deterministic character-for-character preservation).
    2. Local intent classifier brain.
    3. Rule engine (table, heading, header/footer, image, MCQ, summary).
    4. Gemini Universal Orchestrator with context & multi-action planning.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"action": "unknown"}

    # 1. Exact quoted replacement takes absolute top priority for direct commands
    exact_repl = _extract_exact_replacement(prompt)
    if exact_repl:
        logger.info("Exact quoted direct replacement intercepted: %s -> %s", exact_repl["find_text"], exact_repl["replace_text"])
        return exact_repl

    if re.match(r"^/?images?\b", prompt.strip(), re.I) or re.search(r"\b(?:list|show|detect|inspect|view)\s+(?:all\s+)?images\b", prompt, re.I):
        return {"action": "image_module", "engine": "rule"}

    # 2. Attached image replacement wording
    if has_image_upload and (FALLBACK_REPLACE_IMAGE_RE.search(prompt) or re.search(r"\b(?:repl[a-z]*|swap|put|change)\b.*?\b\d+\b", prompt, re.I)):
        logger.info("Image upload + image wording '%s' -> replace_image (regex)", prompt)
        return {"action": "replace_image", "engine": "regex"}

    # 3. Local fine-tuned intent brain (if available)
    local = classify_intent(prompt)
    threshold = intent_confidence_threshold()
    if local and local.get("confidence", 0.0) >= threshold:
        response = _local_intent_to_response(prompt, local["intent"])
        if response:
            response["confidence"] = round(local["confidence"], 4)
            return response

    # 4. Universal Gemini Orchestrator (handles multi-action, context, coreference)
    gemini_intent = _understand_with_gemini(
        prompt, has_image_upload=has_image_upload, history=history, selection=selection, image_base64=image_base64
    )
    if gemini_intent and gemini_intent.get("action") != "unknown":
        return gemini_intent

    # 5. High-precision rule engine fallback
    rule_intent = _fallback_intent(prompt, has_image_upload, selection=selection)
    if rule_intent.get("action") != "unknown":
        rule_intent.setdefault("engine", "regex")
        return rule_intent

    rule_intent.setdefault("engine", "regex")
    return rule_intent


def describe_image_with_gemini(image_bytes: bytes, prompt: str = "Describe this image in detail and transcribe any text:") -> str:
    """Analyze, explain, or OCR text from an image using Gemini vision."""
    model = _gemini_client()
    if model is None:
        return "Image description engine unavailable (Gemini API key not configured)."
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        resp = model.generate_content([f"{prompt}\nIf this image contains diagrams, charts, tables or text, explain and transcribe them.", img])
        return (resp.text or "").strip() or "No description could be generated."
    except Exception as exc:
        logger.error("Error in describe_image_with_gemini: %s", exc)
        return f"Unable to analyze image: {str(exc)}"


def answer_or_extract_with_gemini(text: str, query: str) -> str:
    """Answer questions, extract key points, or generate study notes from document text."""
    model = _gemini_client()
    if model is None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(f"• {l}" for l in lines[:5])
    try:
        prompt = (
            f"You are the Document Intelligence Engine for RapidDoc.\n"
            f"Based on the following document text, answer the user's request accurately, clearly, and concisely.\n\n"
            f"User request: {query}\n\n"
            f"Document text:\n{text[:12000]}\n"
        )
        resp = model.generate_content(prompt)
        return (resp.text or "").strip() or "No information found."
    except Exception as exc:
        logger.error("Error in answer_or_extract_with_gemini: %s", exc)
        return f"Unable to analyze document: {str(exc)}"



def rewrite_text(instruction: str, text: str) -> dict:
    """Rewrite `text` following `instruction`.

    Tries the local T5 brain, then Gemini. Returns
    {"rewritten_text", "engine", "message"}.
    """
    text = (text or "").strip()
    if not text:
        return {
            "rewritten_text": "",
            "engine": "none",
            "message": "No text was provided to rewrite.",
        }

    normalized = _normalize_instruction(instruction)

    # 1) Deterministic grammar repair ----------------------------------------
    # A proofreading request must not change wording. The polisher only repairs
    # surface errors - doubled words, typos, articles, agreement, punctuation,
    # sentence endings - so the author's sentences survive intact.
    if GRAMMAR_INTENT_RE.search((instruction or "").strip()):
        polished = polish_text(text)
        if polished and polished != text:
            logger.info(
                "Deterministic grammar repair applied (%d -> %d chars).",
                len(text), len(polished),
            )
            return {
                "rewritten_text": polished,
                "engine": "grammar",
                "message": (
                    "Grammar, spelling and punctuation corrected. Your wording "
                    "was left unchanged."
                ),
            }
        # Nothing to repair: report it rather than paraphrasing needlessly.
        return {
            "rewritten_text": text,
            "engine": "grammar",
            "message": "No grammar, spelling or punctuation errors were found.",
        }

    # 2) Local T5 brain ------------------------------------------------------
    local_result = rewrite_text_locally(normalized, text)
    if local_result:
        logger.info("Local rewriter brain rewrote %d chars (input %d chars).",
                    len(local_result), len(text))
        return {"rewritten_text": local_result, "engine": "local", "message": "Rewritten by the local T5 brain (with Gemini available as fallback)."}

    # 3) Gemini fallback -----------------------------------------------------
    gemini_result = _rewrite_with_gemini(normalized, text)
    if gemini_result:
        logger.info("Gemini rewrote %d chars (local brain unavailable).", len(gemini_result))
        return {"rewritten_text": gemini_result, "engine": "gemini", "message": "Rewritten by Gemini (local brain unavailable)."}

    # 3) Nothing available ---------------------------------------------------
    logger.warning("No rewrite engine available; returning original text.")
    return {
        "rewritten_text": text,
        "engine": "none",
        "message": "Neither the local brain nor Gemini were available, so the text was returned unchanged.",
    }


# ---------------------------------------------------------------------------
# Brain 4 - summarization
# ---------------------------------------------------------------------------

SUMMARIZE_PROMPT = """You are the summarization engine for RapidDoc, a document editing app.
Write a faithful summary of the given document text.
Return ONLY the summary text. No preamble, no bullet points, no markdown fences."""


def _summary_max_tokens(length_hint):
    """Map a user's length phrasing onto a generated-token budget."""
    if not length_hint:
        return None
    hint = str(length_hint).strip().lower()
    for key, tokens in SUMMARY_LENGTH_HINTS:
        if key in hint:
            return tokens
    return None


def _summarize_with_gemini(text: str, max_tokens=None):
    model = _gemini_client()
    if model is None:
        return None
    try:
        cfg = {"temperature": 0.2}
        if max_tokens:
            cfg["max_output_tokens"] = int(max_tokens)
        m = model.generate_content(
            f"{SUMMARIZE_PROMPT}\n\nDocument:\n{text}", generation_config=cfg
        )
        summary = (m.text or "").strip()
        return summary or None
    except Exception as exc:
        logger.error("Gemini summarization failed: %s", exc)
        return None


# Words that carry no evidence about grounding: they appear in almost any
# summary, so counting them would let an invented sentence pass validation.
_SUMMARY_GENERIC = frozenset("""
document text passage summary paper report section study student practical
content information describes described includes included states stated
following above below provided given used using based according overall
additionally furthermore moreover however therefore thus hence various
different several many most some such also well able need needs required
""".split())

_SUMMARY_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _summary_vocabulary(text: str) -> set:
    """The document's own words, used to stop the polisher rewriting vocabulary.

    Hyphens must separate tokens here. Keeping "hindu-based" as one entry meant
    "hindu" was never in the vocabulary, so the confusable repair could never
    fire - which is exactly the error that was reported.
    """
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z']*", text or "")}


_HEADING = re.compile(
    r"^\s*(?:practical\s*\d*|objective|problem statement|project structure|"
    r"implementation|conclusion|introduction|abstract|contents|references|"
    r"aim|synopsis|overview|note|notes|aims?)\b",
    re.IGNORECASE,
)


def _is_heading(sent: str) -> bool:
    """A section title is a label, not a summary sentence."""
    s = (sent or "").strip()
    if not s:
        return True
    if _HEADING.match(s):
        return True
    # "Practical 12: CI/CD Pipeline with GitHub Actions" - a colon, no closing
    # full stop, and short enough to be a title rather than a statement.
    if ":" in s and not s.rstrip().endswith((".", "!", "?")) and len(s.split()) <= 12:
        return True
    return False


def _extractive_summary(text: str, max_tokens: int) -> str:
    """Summarise by quoting the document's own most representative sentences.

    The local BART decoder is small enough to paraphrase wrongly and drop
    sentence fragments, which is worse than no summary at all. Selecting real
    sentences cannot invent a fact, so this is the floor every other engine has
    to beat.
    """
    # `_summary_max_tokens` returns None when the caller gave no length hint,
    # which the model reads as "use its default"; here it needs a real number.
    budget_chars = max(120, int(max_tokens or 160) * 4)
    # Split on line breaks before sentences: a DOCX table cell boundary is a real
    # content boundary, and flattening first welded a heading onto the sentence
    # after it ("Practical 12: CI/CD Pipeline ... Objective To automate ...").
    raw_sentences = []
    for line in re.split(r"[\r\n]+", text or ""):
        raw_sentences.extend(s for s in split_sentences(line) if s.strip())
    if not raw_sentences:
        return ""

    vocabulary = {w.lower() for w in re.findall(r"[A-Za-z][\w'-]{2,}", text)}
    scored = []
    for idx, sent in enumerate(raw_sentences):
        words = re.findall(r"[A-Za-z][\w'-]{2,}", sent)
        if len(words) < 5 or len(words) > 80:
            continue
        if _is_heading(sent):
            continue
        # Reward sentences that use the document's own vocabulary, and sit
        # early, where practical-style documents put the objective.
        distinct = {w.lower() for w in words} & vocabulary
        lead_bonus = 1.25 if idx < 3 else 1.0
        density = len(distinct) / max(1, len(words))
        length_fit = 1.0 if 8 <= len(words) <= 35 else 0.75
        scored.append((density * lead_bonus * length_fit, idx, sent))

    if not scored:
        return ""
    scored.sort(key=lambda r: (-r[0], r[1]))

    chosen, used = [], 0
    for _, idx, sent in scored:
        if used + len(sent) + 1 > budget_chars:
            continue
        chosen.append((idx, sent))
        used += len(sent) + 1
        if used >= budget_chars:
            break
    if not chosen:
        return ""

    chosen.sort(key=lambda r: r[0])
    polished = polish_sentences(" ".join(s for _, s in chosen), vocabulary)
    return " ".join(polished).strip()


def _validated_summary(summary: str, text: str):
    """Return a trustworthy cleaned summary, or None to reject the decode.

    The reported failure was a summary containing "Hindu-based" for a document
    about Hindi, sentences ending in a dangling clause, and a stray code
    fragment. This returns exactly the text that will be shown, so what was
    checked is what the user reads.
    """
    if not summary:
        return None
    summary = summary.strip()
    if len(summary) < 40:
        return None

    parts = [p for p in polish_sentences(summary) if p]
    if not parts:
        return None
    # Every unit must be a real sentence, not a noun phrase or a dangling clause.
    if any(len(p.split()) < 5 or not p.rstrip().endswith((".", "!", "?")) for p in parts):
        return None

    doc_words = {w.lower() for w in re.findall(r"[A-Za-z][\w'-]{2,}", text)}
    content = [w.lower() for w in re.findall(r"[A-Za-z][\w'-]{2,}", summary)]
    content = [w for w in content if w not in _SUMMARY_GENERIC]
    if not content:
        return None
    known = sum(1 for w in content if w in doc_words)
    if known / len(content) < 0.7:
        return None

    return ensure_sentence(" ".join(parts))


_CONCLUSION_HEADING = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(?:conclusions?|summary|key takeaways|takeaways|"
    r"results?\s*(?:and|&)\s*conclusions?|concluding remarks|final remarks|"
    r"conclusion\s*(?:and|&)\s*(?:future work|future scope|future improvements?)|"
    r"observations?\s*(?:and|&)\s*conclusions?)\b",
    re.IGNORECASE,
)

_SECTION_HEADING = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(?:practical\s*\d*|objective|problem statement|"
    r"project structure|implementation|introduction|abstract|contents|"
    r"references|aim|synopsis|overview|appendix|index|glossary|bibliography|"
    r"methodology|requirements?|design|problem definition)\b",
    re.IGNORECASE,
)


def _find_conclusion_section(text: str) -> str:
    """Return the body of the document's conclusion section, or "" if absent.

    A practical report states its own outcome in a `Conclusion` section, and
    that text is the most faithful summary available - it is what the author
    says was achieved. Anything after the heading and before the next section
    heading is the conclusion; a heading with nothing after it is not.
    """
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text or "")]
    start = None
    for idx, line in enumerate(lines):
        if len(line) <= 90 and _CONCLUSION_HEADING.match(line):
            start = idx + 1
            break
    if start is None:
        return ""

    body = []
    for line in lines[start:]:
        if not line:
            continue
        if len(line) <= 90 and _SECTION_HEADING.match(line):
            break
        body.append(line)
    return "\n".join(body).strip()


def _conclusion_sentences(body: str) -> list:
    """Real, complete sentences from a conclusion section, in document order."""
    vocabulary = {w.lower() for w in re.findall(r"[A-Za-z][\w'-]{2,}", body)}
    out = []
    for line in re.split(r"[\r\n]+", body or ""):
        for sent in split_sentences(line):
            sent = sent.strip()
            words = re.findall(r"[A-Za-z][\w'-]{2,}", sent)
            if len(words) < 6 or len(words) > 60:
                continue
            if _is_heading(sent):
                continue
            polished = polish_sentences(sent, vocabulary)
            cleaned = polished[0].strip() if polished else ""
            if cleaned and cleaned not in out:
                out.append(cleaned)
    return out


def _balanced(text: str) -> bool:
    """True when every bracket opened in `text` is also closed."""
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def _shorten_point(sentence: str, limit: int = 190) -> str:
    """Trim a long sentence to one complete, bracket-safe clause.

    Splitting on the first comma produced points that ended mid-phrase
    ("Correct HTTP status codes (200"), which is worse than a longer point.
    """
    if len(sentence) <= limit:
        return sentence
    head = sentence.split(". ")[0].rstrip(".")
    if len(head) >= 40 and _balanced(head):
        return head + "."
    for sep in ("; ", " — ", " - "):
        if sep in sentence[:limit]:
            candidate = sentence.split(sep)[0].rstrip(".,;:")
            if len(candidate) >= 40 and _balanced(candidate):
                return candidate + "."
    # No safe boundary: cut on a word and mark the elision.
    words = sentence[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return words + "..."


def _key_points(sentences: list, limit: int = 6) -> list:
    """Condense conclusion sentences into short, scannable points."""
    points = []
    for sent in sentences:
        if len(points) >= limit:
            break
        piece = _shorten_point(sent)
        if len(piece.split()) < 4:
            continue
        if piece.rstrip().endswith((".", "!", "?")):
            piece = piece.rstrip(".")
        if piece not in points:
            points.append(piece)
    return points


_BOILERPLATE_OPENERS = re.compile(
    r"^(?:in\s+this\s+(?:practical|lab\s*experiment|report|document|session)\s*,?\s*"
    r"|in\s+this\s+report\s*,?\s*|through\s+this\s+(?:practical|lab\s*experiment)\s*,?\s*"
    r"|we\s+have\s+learned\s+(?:about\s+)?(?:that\s+|how\s+to\s+)?)",
    re.IGNORECASE,
)


def _strip_opener(sent: str) -> str:
    """Drop "In this practical, " so the sentence starts with the substance.

    Every summary opened the same way, which read like a template rather than a
    summary of this particular document.
    """
    out = _BOILERPLATE_OPENERS.sub("", sent or "").lstrip()
    if not out:
        return sent
    out = out[0].upper() + out[1:] if out else out
    return out


def _rank_sentences(sentences: list, text: str) -> list:
    """Order sentences best-first, keeping the original order for ties.

    A conclusion often repeats its opening line and then adds detail. Scoring on
    how much of the document's own vocabulary a sentence uses, with a small
    bonus for being early, picks the substantive sentence over the throat-clearing
    one.
    """
    vocabulary = {w.lower() for w in re.findall(r"[A-Za-z][\w'-]{2,}", text)}
    ranked = []
    for idx, sent in enumerate(sentences):
        words = re.findall(r"[A-Za-z][\w'-]{2,}", sent)
        if not words:
            continue
        distinct = {w.lower() for w in words} & vocabulary
        density = len(distinct) / max(1, len(words))
        length_fit = 1.0 if 10 <= len(words) <= 32 else 0.85
        lead = 1.0 + max(0.0, (0.15 - idx * 0.03))
        ranked.append((density * length_fit * lead, idx, sent))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return ranked


def _sentence_key(sent: str) -> str:
    """Comparison key that ignores case, spacing and trailing punctuation."""
    return re.sub(r"[^a-z0-9 ]", "", (sent or "").lower()).strip()


def _topup_sentences(text: str, conclusion_sents: list) -> list:
    """Body sentences that may extend a conclusion-based summary.

    Prose only, headings removed, and nothing already in the conclusion - a
    top-up that repeats the conclusion is worse than a short summary.
    """
    seen = {_sentence_key(s) for s in conclusion_sents}
    pool = []
    for sent in split_prose_sentences(text, split_sentences):
        if _is_heading(sent):
            continue
        key = _sentence_key(sent)
        if not key or key in seen:
            continue
        seen.add(key)
        pool.append(sent)
    return pool


def _conclusion_summary(sentences: list, text: str, max_tokens, topup: list = None) -> str:
    """Fit the conclusion to the requested length instead of dumping all of it.

    A report's Conclusion section is often shorter than even the `detailed`
    budget. This helper can only ever drop sentences, never add them, so
    `medium` and `detailed` came back byte-identical (286 chars each) and the
    length control the UI exposes did nothing. When the conclusion alone leaves
    budget unused, `topup` sentences from the body of the report are appended in
    ranked order until the budget is met.
    """
    budget = max(120, int(max_tokens or 128) * 4)

    def _collect(pool, offset, out, used):
        # `offset` keeps the conclusion's own sentences ahead of any body top-up,
        # so the summary still leads with what the report concluded.
        chosen_keys = {_sentence_key(existing) for _, existing in out}
        for _, idx, sent in _rank_sentences(pool, text):
            candidate = _strip_opener(sent)
            key = _sentence_key(candidate)
            if not key or key in chosen_keys:
                continue
            chosen_keys.add(key)
            if used + len(candidate) + 1 > budget and out:
                continue
            out.append((offset + idx, candidate))
            used += len(candidate) + 1
            if used >= budget:
                break
        return used

    chosen: list = []
    used = _collect(sentences, 0, chosen, 0)
    if topup and used < budget:
        used = _collect(topup, len(sentences) + 1, chosen, used)

    # Sentence granularity can leave a gap the budget cannot straddle: the
    # longest summary that fits was 508 chars, and the next candidate sentence
    # was 138 chars, which overshoots a 640-char `detailed` budget by 7. Rather
    # than hand back a `detailed` summary identical to `medium`, spend the slack
    # on the shortest sentence still unused, but never by more than a quarter of
    # the budget.
    if topup and used < budget and budget >= 300:
        slack = budget + budget // 4
        chosen_keys = {_sentence_key(existing) for _, existing in chosen}
        spare = [(_strip_opener(s), i) for i, s in enumerate(topup)]
        spare = [(c, i) for c, i in spare
                 if _sentence_key(c) and _sentence_key(c) not in chosen_keys
                 and len(c) + used <= slack]
        if spare:
            candidate, i = min(spare, key=lambda pair: len(pair[0]))
            chosen.append((len(sentences) + 1 + i, candidate))
            used += len(candidate) + 1

    if not chosen:
        return ""
    chosen.sort(key=lambda pair: pair[0])
    return " ".join(candidate for _, candidate in chosen).strip()


def summarize_document(text: str, length_hint=None, title: str = "Document") -> dict:
    """Summarize `text` using hierarchical section-aware complete document understanding.

    Processes all sections of the document, preventing truncation and partial summaries,
    and returns a structured Markdown summary.
    """
    from RapidDoc.backend.app.services.document_summarizer import generate_complete_document_summary
    return generate_complete_document_summary(text, doc_title=title or "Document", length_hint=length_hint)


# ---------------------------------------------------------------------------
# Brain 3 - MCQ generation
# ---------------------------------------------------------------------------

MCQ_PROMPT = """You are the assessment engine for RapidDoc, a document editing app.
Write ONE multiple-choice question about the given passage.

Return strictly valid JSON with no markdown fences, in exactly this shape:
{"question": "<the question>", "options": ["<option A>", "<option B>", "<option C>", "<option D>"], "answer": "<A|B|C|D>"}

Rules:
- Exactly four options, all distinct, and only one correct.
- Options must be specific to the passage, not generic.
- "answer" is the letter of the correct option."""


def _questions_to_gemini(text: str, count: int):
    model = _gemini_client()
    if model is None:
        return None
    out = []
    for _ in range(count):
        try:
            m = model.generate_content(
                f"{MCQ_PROMPT}\n\nPassage:\n{text}",
                generation_config={"response_mime_type": "application/json", "temperature": 0.7},
            )
            parsed = _parse_mcq_from_json(m.text)
            if parsed and parsed.get("valid"):
                out.append(parsed)
        except Exception as exc:
            logger.error("Gemini MCQ generation failed: %s", exc)
            break
    return out or None


def _parse_mcq_from_json(text: str):
    """Parse Gemini's JSON MCQ into the same shape as the local brain."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    question = str(data.get("question") or "").strip()
    options = [str(o).strip() for o in (data.get("options") or [])][:4]
    answer = str(data.get("answer") or "").strip().upper()[:1]
    options = [o for o in options if o]
    return {
        "question": question,
        "options": options,
        "answer": answer,
        "valid": bool(
            question
            and len(options) == 4
            and len({o.lower() for o in options}) == 4
            and answer in ("A", "B", "C", "D")
        ),
    }


# The local BART brain is RACE-trained and answers almost exclusively with this
# form. The user rejected it outright, so it is never allowed into a set.
_NEGATIVE_STEM = re.compile(
    r"\b(?:not|except)\b[^?]{0,40}\b(?:true|false|mentioned|stated|described|"
    r"associated|related|correct|included|given|said|possible)\b"
    r"|\bwhich\b[^?]{0,40}\bnot\b",
    re.IGNORECASE,
)


def _valid_question(q) -> bool:
    """A question is only usable with four distinct, non-question options."""
    if not q or not q.get("question"):
        return False
    stem = str(q["question"])
    if _NEGATIVE_STEM.search(stem):
        return False
    options = q.get("options") or []
    if len(options) != 4 or len({str(o).strip().lower() for o in options}) != 4:
        return False
    if q.get("answer") not in ("A", "B", "C", "D"):
        return False
    # An option that reads as a question is a parsing accident, not a distractor.
    return not any(str(o).strip().endswith("?") for o in options)


def generate_mcqs(text: str, count: int = 5) -> dict:
    """Generate up to `count` multiple-choice questions from `text`.

    The deterministic document-grounded generator runs first. It builds every
    question from a sentence that is actually in the document, so the answer is
    verifiable and the distractors are drawn from the document's own vocabulary.
    The local BART brain is RACE-trained and answered almost exclusively with
    "which of the following is NOT ..." questions, so it is now only used to top
    up a short set; Gemini is the last resort.

    Returns {"questions": [...], "requested", "engine", "message"}.
    """
    # Question stems are built from document sentences; a stem made of source code
    # is unanswerable, so the code is removed before the builder sees the text.
    text = clean_prose((text or "").strip())
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(count, int(settings.MCQ_MAX_QUESTIONS)))

    if not text:
        return {
            "questions": [],
            "requested": count,
            "engine": "none",
            "message": "There is no readable text to build questions from in this document.",
        }

    questions = []
    seen = set()

    # 1. Deterministic, document-grounded questions. Widen the per-type cap on
    #    each retry so a large `count` asks the document for more rather than
    #    falling back to the model the user disliked.
    try:
        used = []
        for cap in (1, 2, 3, 4):
            if len(questions) >= count:
                break
            for q in build_mcq_set(text, count, skip_stems=used, max_per_type=cap):
                if len(questions) >= count:
                    break
                if not _valid_question(q):
                    continue
                key = q["question"].strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                used.append(q["question"])
                questions.append({
                    "question": q["question"],
                    "options": list(q["options"]),
                    "answer": q["answer"],
                    "type": q.get("type") or "recall",
                    "complete": True,
                })
    except Exception:
        logger.exception("Deterministic MCQ generation failed; falling back to models.")

    engine = "document"

    # 2. Top up a short set with the local BART brain.
    if len(questions) < count:
        chunks = chunk_text_for_mcq(text, count)
        for chunk in chunks[:count]:
            if len(questions) >= count:
                break
            try:
                result = generate_mcq(chunk)
            except Exception:
                result = None
            if not result:
                continue
            candidate = {
                "question": result["question"],
                "options": result["options"],
                "answer": result.get("answer") or None,
                "complete": bool(result.get("valid")),
            }
            if not _valid_question(candidate):
                continue
            key = candidate["question"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            candidate["type"] = "model"
            questions.append(candidate)
            engine = "document+bart" if engine == "document" else engine

    # 3. Still short: Gemini.
    if len(questions) < count:
        try:
            gemini_questions = _questions_to_gemini(text, count - len(questions)) or []
        except Exception:
            logger.exception("Gemini MCQ generation failed.")
            gemini_questions = []
        for q in gemini_questions:
            if len(questions) >= count:
                break
            candidate = {
                "question": q["question"],
                "options": q["options"],
                "answer": q.get("answer") or None,
                "complete": True,
                "type": "model",
            }
            if not _valid_question(candidate):
                continue
            key = candidate["question"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            questions.append(candidate)
            engine = "document+gemini" if engine == "document" else engine

    if questions:
        types = {}
        for q in questions:
            types[q.get("type", "model")] = types.get(q.get("type", "model"), 0) + 1
        message = (
            f"Generated {len(questions)} question(s) of {count} from the document."
        )
        if len(questions) < count:
            message += (
                " The document did not contain enough distinct content for the rest."
            )
        logger.info("MCQ engine=%s produced %d/%d types=%s",
                    engine, len(questions), count, types)
        return {
            "questions": questions,
            "requested": count,
            "engine": engine,
            "message": message,
        }

    logger.error("No MCQ engine available for %d chars of text.", len(text))
    return {
        "questions": [],
        "requested": count,
        "engine": "none",
        "message": "No question-generation engine is available right now. Please try again shortly.",
    }


def brains_health():
    """Which brains are loaded - surfaced by GET /api/ai/brains."""
    return brain_status()

