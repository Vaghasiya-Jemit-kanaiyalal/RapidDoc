import json
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

FALLBACK_HEADER_RE = re.compile(
    r"change\s+(?:the\s+)?header\s+(?:to|into|as)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
    re.IGNORECASE,
)
FALLBACK_FOOTER_RE = re.compile(
    r"change\s+(?:the\s+)?footer\s+(?:to|into|as)\s+[\"'“”]?(.+?)['\"“”]?\.?\s*$",
    re.IGNORECASE,
)
FALLBACK_REPLACE_RE = re.compile(
    r"^(?:change|replace|edit)\s+(?:the\s+)?[\"'“”]?([^'\"“”]+?)['\"“”]?\s+(?:to|with|by)\s+[\"'“”]?([^'\"“”]+?)['\"“”]?\.?\s*$",
    re.IGNORECASE,
)

INTENT_PROMPT = """You are the command understanding engine for RapidDoc, a document editing app.

A user typed a natural-language instruction about editing their document. Parse it and return JSON only.

Supported actions:
1. "replace" — replace an exact piece of text with another text anywhere in the document.
   Example: "Change print to not print" -> {"action": "replace", "find_text": "print", "replace_text": "not print"}
2. "header" — change ONLY the page header. Example: "Change the header to RapidDoc Report" -> {"action": "header", "new_text": "RapidDoc Report"}
3. "footer" — change ONLY the page footer. Example: "Change the footer to CHARUSAT University" -> {"action": "footer", "new_text": "CHARUSAT University"}

Rules:
- For "replace", extract the exact literal substring to find and the exact replacement. Do not paraphrase.
- If the instruction references a header/footer, return action "header" or "footer" and put the desired new text in "new_text". Never treat it as a body replace.
- If you cannot determine an action, return {"action": "unknown"}.

Return strictly valid JSON with no markdown fences."""


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


def _fallback_intent(prompt: str) -> dict:
    m = FALLBACK_HEADER_RE.search(prompt)
    if m:
        return {"action": "header", "new_text": m.group(1).strip()}
    m = FALLBACK_FOOTER_RE.search(prompt)
    if m:
        return {"action": "footer", "new_text": m.group(1).strip()}
    m = FALLBACK_REPLACE_RE.match(prompt)
    if m:
        return {
            "action": "replace",
            "find_text": m.group(1).strip(),
            "replace_text": m.group(2).strip(),
        }
    return {"action": "unknown"}


def understand_command(prompt: str) -> dict:
    """Understand a natural-language command via Gemini, falling back to regex.

    Returns a dict with keys action/find_text/replace_text/new_text.
    """
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if api_key and api_key != "YOUR_GEMINI_API_KEY":
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                settings.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
            response = model.generate_content(f"{INTENT_PROMPT}\n\nUser instruction: {prompt}")
            intent = _parse_intent_from_json(response.text)
            if intent.get("action") in ("replace", "header", "footer"):
                logger.info("Gemini parsed command '%s' as %s", prompt, intent)
                return intent
            logger.warning("Gemini returned unexpected intent for '%s': %s", prompt, intent)
        except Exception as e:
            logger.error("Gemini command understanding failed, falling back to regex: %s", e)
    return _fallback_intent(prompt)