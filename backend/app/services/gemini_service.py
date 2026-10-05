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
    r"\b(?:rewrite|rephrase|paraphrase|proofread|correct|fix\s+grammar|improve\s+writing|make\s+it\s+(?:formal|casual|concise|professional|clearer)|shorten|expand)\b",
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


def _clean_find_text(value: str) -> str:
    """Drop filler words and syntax markers that accidentally get captured as the find text.

    e.g. "Replace the word Program with Project" -> find_text is "Program".
    "replace all apple with orange" -> find_text is "apple".
    "change from apple to orange" -> find_text is "apple".
    """
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
    v = v.strip(_STRIP_CHARS)
    return v.rstrip(" ,;:.").strip()


def _clean_replace_text(value: str) -> str:
    """Drop filler words and trailing document scopes that get captured as replace text.

    e.g. "replace cat with dog in document" -> replace_text is "dog".
    "replace cat with dog across the document" -> replace_text is "dog".
    """
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
    v = v.strip(_STRIP_CHARS)
    return v.rstrip(" ,;:.").strip()


def _fallback_intent(prompt: str, has_image_upload: bool = False) -> dict:
    m = FALLBACK_HEADER_RE.search(prompt)
    if m:
        val = m.group(1) or m.group(2)
        if val:
            return {"action": "header", "new_text": val.strip()}
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
    if FALLBACK_REWRITE_RE.search(prompt) or GRAMMAR_INTENT_RE.search(prompt):
        return {
            "action": "rewrite",
            "instruction": prompt.strip(),
            "scope": "document",
        }
    return {"action": "unknown"}


# ---------------------------------------------------------------------------
# Gemini layer
# ---------------------------------------------------------------------------
INTENT_PROMPT = """You are the command understanding engine for RapidDoc, a document editing app.

A user typed a natural-language instruction about editing their document. Parse it and return JSON only.

Supported actions:
1. "replace" — replace an exact piece of text with another text anywhere in the document.
   Example: "Change print to not print" -> {"action": "replace", "find_text": "print", "replace_text": "not print"}
2. "header" — change ONLY the page header. Example: "Change the header to RapidDoc Report" -> {"action": "header", "new_text": "RapidDoc Report"}
3. "footer" — change ONLY the page footer. Example: "Change the footer to CHARUSAT University" -> {"action": "footer", "new_text": "CHARUSAT University"}
4. "replace_image" — the user wants to swap an embedded picture for a newly uploaded file.
   Example: "Replace the image on page 2 with this" -> {"action": "replace_image"}
   Example: "Change the logo" (an image is attached) -> {"action": "replace_image"}

Rules:
- For "replace", extract the exact literal substring to find and the exact replacement. Do not paraphrase.
- If the instruction references a header/footer, return action "header" or "footer" and put the desired new text in "new_text". Never treat it as a body replace.
- Use "replace_image" ONLY when the user is asking to change a picture. If an image file is attached to the message, that alone is enough signal.
- Do NOT extract an image index, page number, or filename for "replace_image". The target is resolved separately against the document's actual image list, and a number you invent could silently replace the wrong picture. Return just {"action": "replace_image"}.
- Distinguish carefully: "replace the image on page 2" is replace_image; "replace the word print with don't print" is a text replace.
- If you cannot determine an action, return {"action": "unknown"}.

Return strictly valid JSON with no markdown fences."""

REWRITE_PROMPT = """You are the text rewriting engine for RapidDoc, a document editing app.
Rewrite the given text following the user's instruction. Keep the meaning identical.
Return ONLY the rewritten text. Do not include explanations, quotes, or prefixes."""

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


def _understand_with_gemini(prompt: str, has_image_upload: bool = False):
    model = _gemini_client()
    if model is None:
        return None
    try:
        hint = (
            "\n\nNote: the user has attached an image file with this instruction."
            if has_image_upload
            else ""
        )
        m = model.generate_content(
            f"{INTENT_PROMPT}{hint}\n\nUser instruction: {prompt}",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
        )
        intent = _parse_intent_from_json(m.text)
        if intent.get("action") in ("replace", "header", "footer", "replace_image"):
            logger.info("Gemini parsed command '%s' as %s", prompt, intent)
            intent["engine"] = "gemini"
            return intent
        logger.warning("Gemini returned unexpected intent for '%s': %s", prompt, intent)
    except Exception as exc:
        logger.error("Gemini command understanding failed, falling back to regex: %s", exc)
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


def understand_command(prompt: str, has_image_upload: bool = False) -> dict:
    """Understand a natural-language command.

    Tries the local DistilBERT intent brain first, then Gemini, then the
    regex rule engine. Returns a dict with the action schema.

    ``has_image_upload`` tells the cascade that the user attached a picture.
    An image swap is only meaningful with a file to swap in, so this flag is
    what lets the regex tier recognise the intent - the local DistilBERT label
    set has no image class, and Gemini is not guaranteed to be configured.
    Without it, "replace the image" falls through to the text-replace tier,
    which searches the document body for the literal phrase "the image".
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"action": "unknown"}

    if re.match(r"^/?images?\b", prompt.strip(), re.I) or re.search(r"\b(?:list|show|detect|inspect|view)\s+(?:all\s+)?images\b", prompt, re.I):
        return {"action": "image_module", "engine": "rule"}

    # An attached image plus any image-ish wording is unambiguous, so answer it
    # from the rules without consulting the local brain: it has no image class
    # and would otherwise steer the request toward a text replace.
    if has_image_upload and (FALLBACK_REPLACE_IMAGE_RE.search(prompt) or re.search(r"\b(?:repl[a-z]*|swap|put|change)\b.*?\b\d+\b", prompt, re.I)):
        logger.info("Image upload + image wording '%s' -> replace_image (regex)", prompt)
        return {"action": "replace_image", "engine": "regex"}

    # 1) Local fine-tuned intent brain -------------------------------------
    local = classify_intent(prompt)
    threshold = intent_confidence_threshold()
    if local and local.get("confidence", 0.0) >= threshold:
        response = _local_intent_to_response(prompt, local["intent"])
        if response:
            response["confidence"] = round(local["confidence"], 4)
            logger.info(
                "Local intent brain: '%s' -> %s (conf=%.3f)",
                prompt, response["action"], local["confidence"],
            )
            return response
        logger.info(
            "Local intent brain classified '%s' as '%s' (conf=%.3f) but "
            "slots were unsupported/incomplete; falling back.",
            prompt, local["intent"], local.get("confidence", 0.0),
        )
    elif local is not None:
        logger.info(
            "Local intent brain confidence %.3f below threshold %.2f for "
            "'%s'; falling back.",
            local.get("confidence", 0.0), threshold, prompt,
        )

    # 2) High-precision rule engine (instant, deterministic, offline) --------
    rule_intent = _fallback_intent(prompt, has_image_upload)
    if rule_intent.get("action") != "unknown":
        rule_intent.setdefault("engine", "regex")
        logger.info("Rule engine resolved command '%s' -> %s", prompt, rule_intent["action"])
        return rule_intent

    # 3) Gemini fallback ----------------------------------------------------
    gemini_intent = _understand_with_gemini(prompt, has_image_upload)
    if gemini_intent:
        return gemini_intent

    rule_intent.setdefault("engine", "regex")
    return rule_intent


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

