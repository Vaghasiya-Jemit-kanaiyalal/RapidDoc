"""Rule-based slot extractor that pairs with the local DistilBERT intent brain.

The intent model only predicts the *intent* (e.g. "replace_text",
"change_header"). These deterministic rules extract the slot *values*
(old_text/new_text, header/footer text, fonts, sizes, alignment, page...)
using the known-phrasing patterns used to generate the training set.

Returns {} when a slot value cannot be determined — callers should then fall
back to the Gemini layer or the regex engine instead of guessing.
"""

import re

FONTS = ["Times New Roman", "Arial", "Calibri", "Georgia", "Verdana",
         "Roboto", "Courier New", "Garamond"]
LANGUAGES = ["Spanish", "French", "German", "Hindi", "Japanese", "Chinese",
             "Gujarati", "Arabic", "Portuguese", "Russian"]
ALIGNMENTS = ["left", "right", "center", "justified"]
POSITIONS = ["beginning", "end", "top", "bottom"]
COLORS = ["white", "light blue", "light gray", "cream", "pale yellow",
          "soft green", "sky blue", "lavender"]
STYLES = ["bold and italic", "bold", "italic", "underlined"]  # longest first

# --- header/footer new-text patterns ---------------------------------------
HEADER_NEW_TEXT_RES = [
    re.compile(
        r"\bheader\b[\s\S]{0,30}?\b(?:to\s+say|to|as|into|be|should be)\s*[\"'“”]?(.+?)['\"“”]?\.?\s*$",
        re.IGNORECASE),
    re.compile(
        r"\b(?:set|put|make)\b[\s\S]{0,20}?\bheader\b[\s\S]{0,20}?\b(?:to|as|into)\s*[\"'“”]?(.+?)['\"“”]?\.?\s*$",
        re.IGNORECASE),
    re.compile(r"\b(?:change|edit|update|replace)\s+(?:the\s+)?header\s+(?:text\s+)?\b(?:to|with|to be|as)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
               re.IGNORECASE),
    re.compile(r"\bheader\b[\s\S]{0,25}?\bshould\s+(?:read|be|say)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
               re.IGNORECASE),
]

FOOTER_NEW_TEXT_RES = [
    re.compile(
        r"\bfooter\b[\s\S]{0,30}?\b(?:to\s+say|to|as|into|be|should be)\s*[\"'“”]?(.+?)['\"“”]?\.?\s*$",
        re.IGNORECASE),
    re.compile(
        r"\b(?:set|put|make)\b[\s\S]{0,20}?\bfooter\b[\s\S]{0,20}?\b(?:to|as|into)\s*[\"'“”]?(.+?)['\"“”]?\.?\s*$",
        re.IGNORECASE),
    re.compile(r"\b(?:change|edit|update|replace)\s+(?:the\s+)?footer\s+(?:text\s+)?\b(?:to|with|to be|as)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
               re.IGNORECASE),
    re.compile(r"\bfooter\b[\s\S]{0,25}?\bshould\s+(?:read|be|say)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
               re.IGNORECASE),
]

# --- "replace X with Y" patterns --------------------------------------------
REPLACE_WITH_RES = [
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


def _match_first(patterns, text):
    for pat in patterns:
        m = pat.search(text)
        if m and m.group(1) and m.group(1).strip():
            return m.group(1).strip()
    return None


_STRIP_CHARS = " \t\r\n'\"“”`"
_NEW_TEXT_FILLER = re.compile(r"^\s*(?:say|read|be|to|is|as|should|please|kindly)\s+", re.IGNORECASE)


def _clean_new_text(value):
    if not value:
        return value
    v = value.strip(_STRIP_CHARS)
    v = _NEW_TEXT_FILLER.sub("", v)
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
    v = v.strip(_STRIP_CHARS)
    return v.rstrip(" ,;:.").strip()


def _clean_old_text(value):
    if not value:
        return value
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
    v = v.strip(_STRIP_CHARS)
    return v.rstrip(" ,;:.").strip() or value.strip()


def extract_slots(prompt: str, intent: str) -> dict:
    slots = {}
    text = prompt or ""
    text_lower = text.lower()

    # --- quoted phrases: old/new for replace, else target text ---------------
    quotes = re.findall(r"['\"“”`]([^'\"“”`]+)['\"“”`]", text)
    if quotes:
        if intent == "replace_text" and len(quotes) >= 2:
            slots["old_text"] = _clean_old_text(quotes[0].strip())
            slots["new_text"] = _clean_new_text(quotes[1].strip())
        else:
            slots["target_text"] = quotes[0].strip()

    # --- replace_text: old/new via "X (to|with) Y" phrasing ------------------
    if intent == "replace_text":
        if "old_text" not in slots or "new_text" not in slots:
            for pat in REPLACE_WITH_RES:
                m = pat.search(text)
                if m and m.group(1).strip() and m.group(2).strip():
                    slots["old_text"] = _clean_old_text(m.group(1))
                    slots["new_text"] = _clean_new_text(m.group(2))
                    break

    # --- header / footer: extract the desired new text -----------------------
    if intent == "change_header":
        new_text = _match_first(HEADER_NEW_TEXT_RES, text)
        if new_text:
            slots["new_text"] = _clean_new_text(new_text)
    elif intent == "change_footer":
        new_text = _match_first(FOOTER_NEW_TEXT_RES, text)
        if new_text:
            slots["new_text"] = _clean_new_text(new_text)

    # --- page number (digit or first/last/cover) -----------------------------
    m = re.search(r"\bpage\s+(\d+)\b", text, re.I)
    if m:
        slots["page"] = int(m.group(1))
    elif re.search(r"\b(first|last|cover)\s+page\b|\bpage\s+(first|last|cover)\b", text, re.I):
        m2 = re.search(r"\b(first|last|cover)\b", text, re.I)
        if m2:
            slots["page"] = m2.group(1).lower()

    # --- font ----------------------------------------------------------------
    for f in FONTS:
        if f.lower() in text_lower:
            slots["font_name"] = f
            break

    # --- font size -----------------------------------------------------------
    m = re.search(r"\b(\d{1,2})\s*(?:pt|points?)\b", text, re.I)
    if m:
        slots["size"] = int(m.group(1))

    # --- language ------------------------------------------------------------
    for l in LANGUAGES:
        if l.lower() in text_lower:
            slots["target_language"] = l
            break

    # --- alignment -----------------------------------------------------------
    for a in ALIGNMENTS:
        if a in text_lower:
            slots["alignment"] = a
            break

    # --- position ------------------------------------------------------------
    for p in POSITIONS:
        if p in text_lower:
            slots["position"] = p
            break

    # --- color ---------------------------------------------------------------
    for c in COLORS:
        if c in text_lower:
            slots["color"] = c
            break

    # --- text style ----------------------------------------------------------
    for s in STYLES:
        if s in text_lower:
            slots["style"] = s
            break

    # --- counts (MCQs / flashcards / viva questions) -------------------------
    m = re.search(r"\b(\d+)\s*(mcqs?|flashcards?|viva questions?|questions?)\b", text, re.I)
    if m:
        count = int(m.group(1))
        if intent == "generate_mcq":
            slots["num_questions"] = count
        elif intent == "generate_flashcards":
            slots["num_cards"] = count
        elif intent == "generate_viva_questions":
            slots["num_questions"] = count

    # --- summary length ------------------------------------------------------
    for length in ["one-paragraph", "detailed", "medium", "brief", "short"]:
        if length in text_lower:
            slots["length"] = length
            break

    return slots