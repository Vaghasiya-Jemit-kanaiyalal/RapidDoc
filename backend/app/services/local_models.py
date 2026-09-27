"""Local fine-tuned RapidDoc brain models.

Four brains, all served locally on CPU (or GPU when one is available):

  1. rapiddoc_intent_model    - DistilBERT command-intent classifier (22 intents).
  2. rapiddoc_text_rewriter   - T5-small CoEdIT text rewriter.
  3. rapiddoc_mcq_generator   - BART-base MCQ generator (question + 4 options + answer).
  4. rapiddoc_summarizer      - BART-base abstractive document summarizer.

Models are loaded lazily on first use (keeps boot time fast) and guarded by
locks so concurrent requests cannot load duplicates. Each brain also takes an
inference lock: torch generation keeps mutable per-call state, and on CPU the
threads already saturate every core, so serialising per model is both safer and
no slower than letting two requests fight over the same weights.

Every public inference function returns None (or an empty result) on any
failure, so callers can transparently fall back to Gemini or the deterministic
rule engine instead of crashing the request.
"""

import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

from RapidDoc.backend.app.config import settings

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

# tag -> (settings attr holding the path, lock, cache dict)
_SEQ2SEQ_CACHE = {}
_SEQ2SEQ_LOCKS = {}
_CACHE_LOCK = threading.Lock()

# transformers 5.x builds a model on the meta device and materialises the
# weights as it reads them. Two from_pretrained() calls running concurrently
# interleave that and leave parameters on the meta device, which then makes
# model.to(...) raise "Cannot copy out of meta tensor". Loading is a one-off
# cost, so every load is funnelled through this single lock.
_LOAD_LOCK = threading.Lock()

_INTENT_LOCK = threading.Lock()
_INTENT_STATE = {
    "mode": None,        # "trained" | "zeroshot" | None
    "checked": False,    # True once a load attempt has been made
    "pipeline": None,    # zero-shot NLI pipeline
    "model": None,       # fine-tuned classifier
    "tokenizer": None,
    "labels": None,      # ordered label list for the loaded model
}

# Guards torch's mutable per-call generation state. A single lock is used for
# every brain: on CPU the inference threads already saturate all cores, so
# serialising avoids thrashing and removes any risk of two requests corrupting
# the same model's generation state.
_INFER_LOCK = threading.RLock()


def _cache_slot(tag: str):
    """Return (cache_dict, lock) for a seq2seq brain, creating them on demand."""
    with _CACHE_LOCK:
        if tag not in _SEQ2SEQ_CACHE:
            _SEQ2SEQ_CACHE[tag] = {"model": None, "tokenizer": None}
        if tag not in _SEQ2SEQ_LOCKS:
            _SEQ2SEQ_LOCKS[tag] = threading.Lock()
        return _SEQ2SEQ_CACHE[tag], _SEQ2SEQ_LOCKS[tag]


def _resolve_model_path(raw_path: str):
    """Validate a brain directory: exists, has a config and some weights.

    Returns the cleaned path, or None with a logged reason.
    """
    path = (raw_path or "").strip()
    if not path or not os.path.isdir(path):
        return None
    if not os.path.isfile(os.path.join(path, "config.json")):
        logger.warning("Brain dir '%s' has no config.json - skipping.", path)
        return None
    if not any(
        os.path.isfile(os.path.join(path, f))
        for f in ("model.safetensors", "pytorch_model.bin")
    ):
        logger.warning("Brain dir '%s' has no model weights - skipping.", path)
        return None
    return path


def _device():
    try:
        import torch
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    except Exception:
        return None


def _silence_transformers_noise():
    """Keep 'Loading weights' progress bars and tie-weight warnings out of logs."""
    try:
        import transformers
        transformers.logging.set_verbosity_error()
    except Exception:
        pass


def _get_seq2seq(tag: str, path_setting_value: str, display_name: str):
    """Load (and cache) a seq2seq brain. Returns (model, tokenizer) or (None, None).

    Failures are logged and swallowed: a missing brain must never take the API
    down, it just means the caller falls through to the next tier.
    """
    slot, lock = _cache_slot(tag)
    if slot["model"] is not None and slot["tokenizer"] is not None:
        return slot["model"], slot["tokenizer"]

    model_path = _resolve_model_path(path_setting_value)
    if model_path is None:
        logger.info("Brain '%s' unavailable or missing weights; skipping.", display_name)
        return None, None

    with lock:
        if slot["model"] is not None and slot["tokenizer"] is not None:
            return slot["model"], slot["tokenizer"]
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            _silence_transformers_noise()
            logger.info("Loading brain '%s' from %s ...", display_name, model_path)
            with _LOAD_LOCK:
                tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
                model = AutoModelForSeq2SeqLM.from_pretrained(model_path, local_files_only=True)
                dev = _device()
                if dev is not None:
                    model = model.to(dev)
                model.eval()
            slot["model"], slot["tokenizer"] = model, tokenizer
            logger.info("Brain '%s' ready on %s.", display_name, dev or "cpu")
        except Exception as exc:
            logger.error("Failed to load brain '%s': %s", display_name, exc)
            slot["model"], slot["tokenizer"] = None, None
    return slot["model"], slot["tokenizer"]


def _get_rewriter():
    """Returns (model, tokenizer) for the local T5 CoEdIT rewriter."""
    return _get_seq2seq(
        "rewriter",
        settings.TEXT_REWRITER_MODEL_PATH,
        "text_rewriter",
    )


def _get_summarizer():
    """Returns (model, tokenizer) for the local BART summarizer."""
    return _get_seq2seq(
        "summarizer",
        settings.SUMMARIZER_MODEL_PATH,
        "summarizer",
    )


def _get_mcq_generator():
    """Returns (model, tokenizer) for the local BART MCQ generator."""
    return _get_seq2seq(
        "mcq_generator",
        settings.MCQ_GENERATOR_MODEL_PATH,
        "mcq_generator",
    )


# ---------------------------------------------------------------------------
# Brain 1 - intent classification
# ---------------------------------------------------------------------------

# The label set the intent brain was fine-tuned on (22 classes). Read from the
# model's own config.json at load time; this list is the documented fallback.
TRAINED_INTENT_LABELS = [
    "change_alignment",
    "change_background",
    "change_font",
    "change_font_size",
    "change_footer",
    "change_header",
    "change_text_style",
    "delete_text",
    "extract_keywords",
    "generate_flashcards",
    "generate_mcq",
    "generate_notes",
    "generate_viva_questions",
    "insert_image",
    "insert_page_number",
    "insert_text",
    "remove_image",
    "replace_logo",
    "replace_text",
    "summarize_document",
    "summarize_page",
    "translate_section",
]

# Candidate labels used when the model on disk turns out to be the raw
# zero-shot NLI checkpoint (typeform/distilbert-mnli), which has no RapidDoc
# labels of its own and needs them supplied per call.
ZERO_SHOT_INTENT_LABELS = [
    "add_bullets",
    "change_font",
    "change_font_size",
    "change_footer",
    "change_header",
    "change_language",
    "change_title",
    "check_grammar",
    "delete_paragraph",
    "extract_keywords",
    "generate_flashcards",
    "generate_mcq",
    "generate_viva_questions",
    "insert_image",
    "insert_page_number",
    "insert_text",
    "justify_text",
    "remove_image",
    "remove_page_number",
    "replace_logo",
    "replace_text",
    "summarize_document",
    "summarize_page",
    "translate_section",
]

# Backwards-compatible alias.
INTENT_LABELS = ZERO_SHOT_INTENT_LABELS

# Labels that identify the raw MNLI entailment checkpoint.
_ENTAILMENT_LABELS = {"entailment", "neutral", "contradiction"}


def _labels_from_config(model_path):
    """Read the ordered label list out of a sequence-classification config.json."""
    try:
        cfg_path = os.path.join(model_path, "config.json")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception as exc:
        logger.warning("Could not read intent config at '%s': %s", cfg_path, exc)
        return None

    id2label = cfg.get("id2label") or {}
    if not id2label:
        return None

    # Keys are strings in JSON but ints in a live config object; normalise.
    normalised = {}
    for k, v in id2label.items():
        try:
            normalised[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    if not normalised:
        return None
    return [normalised[i] for i in sorted(normalised)]


def _load_intent_brain():
    """Detect and load the intent brain. Returns True when it is usable.

    Two checkpoints are supported:
      * fine-tuned classifier  -> 22 RapidDoc labels baked into config.json
      * raw MNLI entailment    -> labels supplied at call time (zero-shot)
    """
    if _INTENT_STATE["mode"] is not None:
        return True
    # One failed attempt is enough: don't re-stat and re-log on every request.
    if _INTENT_STATE["checked"]:
        return False

    with _INTENT_LOCK:
        if _INTENT_STATE["mode"] is not None:
            return True
        if _INTENT_STATE["checked"]:
            return False

        _INTENT_STATE["checked"] = True
        _INTENT_STATE.update(
            {"mode": None, "pipeline": None, "model": None, "tokenizer": None, "labels": None}
        )

        model_path = _resolve_model_path(settings.INTENT_MODEL_PATH)
        if model_path is None:
            logger.info("Intent brain unavailable or missing weights; skipping.")
            return False

        try:
            _silence_transformers_noise()
            labels = _labels_from_config(model_path)
            is_zero_shot = bool(labels) and set(
                lbl.lower() for lbl in labels
            ) & _ENTAILMENT_LABELS

            with _LOAD_LOCK:
                if is_zero_shot:
                    from transformers import pipeline
                    logger.info("Intent brain is a zero-shot NLI checkpoint; using it zero-shot.")
                    clf = pipeline(
                        "zero-shot-classification",
                        model=model_path,
                        tokenizer=model_path,
                    )
                    _INTENT_STATE["pipeline"] = clf
                    _INTENT_STATE["labels"] = ZERO_SHOT_INTENT_LABELS
                    _INTENT_STATE["mode"] = "zeroshot"
                else:
                    from transformers import (
                        AutoModelForSequenceClassification,
                        AutoTokenizer,
                    )
                    logger.info("Loading fine-tuned intent classifier from %s ...", model_path)
                    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
                    model = AutoModelForSequenceClassification.from_pretrained(
                        model_path, local_files_only=True
                    )
                    dev = _device()
                    if dev is not None:
                        model = model.to(dev)
                    model.eval()
                    _INTENT_STATE["tokenizer"] = tokenizer
                    _INTENT_STATE["model"] = model
                    _INTENT_STATE["labels"] = labels or TRAINED_INTENT_LABELS
                    _INTENT_STATE["mode"] = "trained"
            logger.info("Intent brain ready (%d labels).", len(_INTENT_STATE["labels"]))
        except Exception as exc:
            logger.error("Failed to load intent brain: %s", exc)
            _INTENT_STATE.update(
                {"mode": None, "pipeline": None, "model": None, "tokenizer": None, "labels": None}
            )
        return _INTENT_STATE["mode"] is not None


def intent_labels():
    """The label list the loaded intent brain actually predicts."""
    return list(_INTENT_STATE["labels"] or TRAINED_INTENT_LABELS)


def intent_is_zero_shot():
    return _INTENT_STATE["mode"] == "zeroshot"


def intent_confidence_threshold():
    """Threshold appropriate to the checkpoint actually in use."""
    if intent_is_zero_shot():
        return float(settings.INTENT_CONFIDENCE_THRESHOLD_ZERO_SHOT)
    return float(settings.INTENT_CONFIDENCE_THRESHOLD)


def classify_intent(prompt: str):
    """Classify a natural-language command with the local DistilBERT brain.

    Returns {"intent": str, "confidence": float, "mode": "trained"|"zeroshot"}
    or None if the brain is unavailable/errors.
    """
    text = (prompt or "").strip()
    if not text:
        return None
    if not _load_intent_brain():
        return None

    try:
        import torch

        with _INFER_LOCK:
            if _INTENT_STATE["mode"] == "trained":
                tokenizer = _INTENT_STATE["tokenizer"]
                model = _INTENT_STATE["model"]
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
                dev = _device()
                if dev is not None:
                    inputs = {k: v.to(dev) for k, v in inputs.items()}
                with torch.no_grad():
                    logits = model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0]
                best = int(torch.argmax(probs).item())
                labels = _INTENT_STATE["labels"]
                label = labels[best] if best < len(labels) else str(best)
                return {
                    "intent": label,
                    "confidence": float(probs[best].item()),
                    "mode": "trained",
                }

            clf = _INTENT_STATE["pipeline"]
            result = clf(text, candidate_labels=_INTENT_STATE["labels"], truncation=True)
            return {
                "intent": str(result["labels"][0]),
                "confidence": float(result["scores"][0]),
                "mode": "zeroshot",
            }
    except Exception as exc:
        logger.error("Intent brain inference failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Brain 2 - text rewriting (T5-small CoEdIT)
# ---------------------------------------------------------------------------

def build_rewriter_input(instruction: str, text: str) -> str:
    """Render the CoEdIT-style prompt the rewriter brain was trained on.

    coedit-small expects "<instruction>: <text>". Prefixing the instruction
    with an extra "rewrite:" token makes the model read the whole string as one
    instruction and ignore the actual task, so the template is configurable
    but defaults to the correct CoEdIT layout.
    """
    template = (settings.TEXT_REWRITER_TEMPLATE or "{instruction}: {text}")
    try:
        return template.format(instruction=(instruction or "").strip(), text=(text or "").strip())
    except (KeyError, IndexError, ValueError):
        return f"{instruction}: {text}"


def rewrite_text_locally(instruction: str, text: str):
    """Rewrite `text` following `instruction` with the local T5 brain.

    Returns the rewritten string, or None on failure/empty output.
    """
    text = (text or "").strip()
    if not text:
        return None
    model, tokenizer = _get_rewriter()
    if model is None or tokenizer is None:
        return None
    try:
        import torch
        model_input = build_rewriter_input(instruction, text)
        inputs = tokenizer(
            model_input,
            return_tensors="pt",
            max_length=512,
            truncation=True,
        )
        dev = _device()
        if dev is not None:
            inputs = {k: v.to(dev) for k, v in inputs.items()}
        with torch.no_grad(), _INFER_LOCK:
            outputs = model.generate(
                **inputs,
                max_length=int(settings.T5_MAX_GEN_LENGTH),
                num_beams=int(settings.T5_NUM_BEAMS),
                no_repeat_ngram_size=int(settings.T5_NO_REPEAT_NGRAM_SIZE),
                early_stopping=True,
            )
        rewritten = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # coedit-small is small and sometimes drops content outright. Returning
        # a mangled paragraph is worse than falling through to Gemini, so reject
        # output that lost most of the input or came back empty.
        if not rewritten:
            return None
        if len(rewritten) < max(1, int(len(text) * 0.25)):
            logger.warning(
                "Rewriter output collapsed (%d chars in -> %d out); rejecting.",
                len(text), len(rewritten),
            )
            return None
        return rewritten
    except Exception as exc:
        logger.error("Text rewriter brain inference failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Brain 3 - MCQ generation (BART-base)
# ---------------------------------------------------------------------------

_MCQ_QUESTION_RE = re.compile(r"question:\s*(.+?)\s*options:\s*(.*)", re.IGNORECASE | re.DOTALL)
_MCQ_ANSWER_RE = re.compile(r"answer:\s*([ABCD])\b", re.IGNORECASE)
_MCQ_OPTION_RE = re.compile(
    r"([ABCD])\)\s*(.*?)(?=\s+[ABCD]\)\s|\s*answer\s*:|$)", re.IGNORECASE | re.DOTALL
)


def parse_mcq(raw: str):
    """Parse one generated MCQ record.

    Returns a dict with question / options (ordered A-D) / answer plus a
    `valid` flag, or None when the record cannot be parsed at all.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    m = _MCQ_QUESTION_RE.search(raw)
    if not m:
        return None

    question = m.group(1).strip()
    remainder = m.group(2).strip()
    if not question:
        return None

    answer = ""
    am = _MCQ_ANSWER_RE.search(remainder)
    if am:
        answer = am.group(1).upper()
        remainder = remainder[: am.start()].strip()

    options = {}
    for letter, body in _MCQ_OPTION_RE.findall(remainder):
        body = body.strip().strip('"').rstrip(" ,;")
        if not body:
            continue
        options.setdefault(letter.upper(), body)

    ordered = [options.get(l) for l in ("A", "B", "C", "D")]
    complete = all(ordered)
    distinct = len({o.lower() for o in ordered if o}) == len([o for o in ordered if o])
    valid = bool(
        question
        and complete
        and distinct
        and answer in ("A", "B", "C", "D")
    )
    return {
        "question": question,
        "options": ordered,
        "answer": answer,
        "valid": valid,
    }


def _score_mcq(parsed):
    """Rank parsed candidates: complete+valid first, then more options."""
    if not parsed:
        return -1
    score = 0
    if parsed.get("valid"):
        score += 100
    score += sum(1 for o in parsed.get("options") or [] if o)
    if parsed.get("answer") in ("A", "B", "C", "D"):
        score += 10
    if parsed.get("question"):
        score += 5
    return score


def generate_mcq(passage: str):
    """Generate a single multiple-choice question from a passage.

    The brain is trained on RACE-style 4-option questions and sometimes emits a
    malformed record, so several beams are sampled from a single beam search
    (they share the search tree, which makes this nearly free) and the best
    fully-valid candidate wins.

    Returns {"question", "options", "answer", "valid", "raw"} or None.
    """
    passage = (passage or "").strip()
    if len(passage) < int(settings.MCQ_MIN_PASSAGE_CHARS):
        logger.info(
            "MCQ brain skipped: passage has %d chars, need >= %d.",
            len(passage), settings.MCQ_MIN_PASSAGE_CHARS,
        )
        return None

    model, tokenizer = _get_mcq_generator()
    if model is None or tokenizer is None:
        return None

    try:
        import torch

        n_candidates = max(1, int(settings.MCQ_NUM_CANDIDATES))
        num_beams = max(int(settings.MCQ_NUM_BEAMS), n_candidates)
        inputs = tokenizer(
            f"generate mcq: {passage}",
            return_tensors="pt",
            max_length=int(settings.MCQ_MAX_INPUT_TOKENS),
            truncation=True,
        )
        dev = _device()
        if dev is not None:
            inputs = {k: v.to(dev) for k, v in inputs.items()}

        with torch.no_grad(), _INFER_LOCK:
            outputs = model.generate(
                **inputs,
                max_length=int(settings.MCQ_MAX_GEN_TOKENS),
                num_beams=num_beams,
                num_return_sequences=n_candidates,
                no_repeat_ngram_size=int(settings.MCQ_NO_REPEAT_NGRAM_SIZE),
                early_stopping=True,
            )
        raws = tokenizer.batch_decode(outputs, skip_special_tokens=True)

        best = None
        best_score = -1
        for raw in raws:
            parsed = parse_mcq(raw)
            score = _score_mcq(parsed)
            if score > best_score:
                best, best_score = parsed, score

        if best is None:
            logger.warning("MCQ brain produced no parseable question for a %d-char passage.", len(passage))
            return None

        if not best.get("valid"):
            logger.warning(
                "MCQ brain produced an incomplete question (options=%d/4, answer=%r).",
                sum(1 for o in best["options"] if o), best.get("answer") or "",
            )

        best["raw"] = raws[0] if raws else ""
        return best
    except Exception as exc:
        logger.error("MCQ brain inference failed: %s", exc)
        return None


def chunk_text_for_mcq(text: str, max_chunks: int):
    """Split document text into overlapping-free passage-sized chunks.

    Prefers to break on blank lines, then sentence ends, then hard character
    cuts, so each chunk still reads as a coherent passage for the MCQ brain.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Size the window so a short document can still yield the requested number
    # of questions: without this, anything under MCQ_PASSAGE_CHARS always
    # collapsed into a single chunk regardless of how many were asked for.
    # The floor is deliberately above MCQ_MIN_PASSAGE_CHARS because pieces are
    # stripped after cutting, so a window equal to the minimum would drop every
    # chunk and report "not enough text" on a perfectly readable document.
    max_size = max(int(settings.MCQ_PASSAGE_CHARS), int(settings.MCQ_MIN_PASSAGE_CHARS) + 1)
    min_size = max(1, int(settings.MCQ_MIN_PASSAGE_CHARS))
    chunk_size = max_size
    if max_chunks > 1 and len(text) > min_size:
        chunk_size = min(max_size, max(min_size * 2, len(text) // max_chunks))

    chunks = []
    remaining = text
    while remaining and len(chunks) < max_chunks:
        if len(remaining) <= chunk_size:
            chunks.append(remaining.strip())
            break

        window = remaining[:chunk_size]
        cut = -1
        for marker in ("\n\n", ". ", ".\n", "\n"):
            idx = window.rfind(marker)
            # Require a reasonable amount of context on both sides.
            if idx > chunk_size * 0.4:
                cut = idx + len(marker)
                break
        if cut == -1:
            cut = chunk_size

        piece = remaining[:cut].strip()
        if piece:
            chunks.append(piece)
        remaining = remaining[cut:].strip()

    return [c for c in chunks if len(c) >= int(settings.MCQ_MIN_PASSAGE_CHARS)]


# ---------------------------------------------------------------------------
# Brain 4 - summarization (BART-base)
# ---------------------------------------------------------------------------

# BART's sentencepiece decode puts a space before sentence-final punctuation
# ("steady on Wednesday .") and keeps the newlines it was trained to emit.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")
_REPEATED_PUNCT_RE = re.compile(r"([.,;:!?]){2,}")


def tidy_summary(text: str) -> str:
    """Clean up a raw BART decode into presentable prose."""
    if not text:
        return ""
    out = text.replace("\r\n", "\n")
    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _REPEATED_PUNCT_RE.sub(r"\1", out)
    # Keep paragraph breaks, but drop runs of blank lines.
    out = re.sub(r"\n{3,}", "\n\n", out)
    lines = [ln.strip() for ln in out.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def summarize(text: str, max_new_tokens: int = None, min_new_tokens: int = 0):
    """Abstractively summarize `text` with the local BART summarizer brain.

    Returns the summary string, or None on failure/empty output.
    """
    text = (text or "").strip()
    if not text:
        return None

    max_chars = int(settings.SUMMARIZER_MAX_INPUT_CHARS)
    if len(text) > max_chars:
        text = text[:max_chars]
        logger.info("Summarizer input truncated to %d chars for the model window.", max_chars)

    model, tokenizer = _get_summarizer()
    if model is None or tokenizer is None:
        return None

    try:
        import torch

        gen_max = int(max_new_tokens or settings.SUMMARIZER_MAX_GEN_TOKENS)
        gen_max = max(8, gen_max)
        gen_min = max(0, int(min_new_tokens or 0))
        # min_length must stay below max_length or generate() raises.
        gen_min = min(gen_min, gen_max - 1)
        inputs = tokenizer(
            f"summarize: {text}",
            return_tensors="pt",
            max_length=int(settings.SUMMARIZER_MAX_INPUT_TOKENS),
            truncation=True,
        )
        dev = _device()
        if dev is not None:
            inputs = {k: v.to(dev) for k, v in inputs.items()}

        kwargs = {
            "max_length": gen_max,
            "num_beams": max(1, int(settings.SUMMARIZER_NUM_BEAMS)),
            "length_penalty": float(settings.SUMMARIZER_LENGTH_PENALTY),
            "no_repeat_ngram_size": int(settings.SUMMARIZER_NO_REPEAT_NGRAM_SIZE),
            "early_stopping": True,
        }
        if gen_min > 0:
            kwargs["min_length"] = gen_min

        with torch.no_grad(), _INFER_LOCK:
            outputs = model.generate(**inputs, **kwargs)
        summary = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        summary = tidy_summary(summary)
        return summary or None
    except Exception as exc:
        logger.error("Summarizer brain inference failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Health / warm start
# ---------------------------------------------------------------------------

def brain_status():
    """Report which brains are loaded (or loadable) - used by /api/ai/brains."""
    configured = {
        "intent": settings.INTENT_MODEL_PATH,
        "rewriter": settings.TEXT_REWRITER_MODEL_PATH,
        "mcq_generator": settings.MCQ_GENERATOR_MODEL_PATH,
        "summarizer": settings.SUMMARIZER_MODEL_PATH,
    }
    brains = {}
    for name, path in configured.items():
        resolved = _resolve_model_path(path)
        brains[name] = {
            "loaded": False,
            "path": path,
            "present": resolved is not None,
            "labels": None,
            "mode": None,
        }

    brains["intent"]["mode"] = _INTENT_STATE["mode"]
    brains["intent"]["loaded"] = _INTENT_STATE["mode"] is not None
    if brains["intent"]["loaded"]:
        brains["intent"]["labels"] = len(_INTENT_STATE["labels"] or [])

    for tag, name in (("rewriter", "rewriter"), ("mcq_generator", "mcq_generator"),
                      ("summarizer", "summarizer")):
        slot, _ = _cache_slot(tag)
        brains[name]["loaded"] = slot["model"] is not None

    return {
        "enabled": bool(settings.AI_USE_LOCAL_MODELS),
        "gemini_configured": bool(
            (settings.GEMINI_API_KEY or "").strip()
            and (settings.GEMINI_API_KEY or "").strip() not in
            ("YOUR_GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
        ),
        "device": str(_device() or "cpu"),
        "intent_confidence_threshold": intent_confidence_threshold(),
        "brains": brains,
    }


def warm_start_brains():
    """Preload all four local brains in background threads so the first user
    command doesn't pay the model-loading penalty (roughly 1.5 GB of weights
    and tens of seconds on CPU).

    Safe to call from a non-blocking startup thread - the loaders are guarded
    by locks and return immediately if already loaded. A brain that fails to
    load is logged and skipped; it never blocks startup.
    """
    if not settings.AI_USE_LOCAL_MODELS:
        logger.info("Local brains disabled; skipping warm start.")
        return

    def _load(name, fn):
        try:
            fn()
        except Exception as exc:
            logger.error("warm-start %s brain failed: %s", name, exc)

    logger.info("Warm-starting local AI brains in background...")
    jobs = [
        ("intent", _load_intent_brain),
        ("rewriter", lambda: _get_rewriter()),
        ("mcq_generator", lambda: _get_mcq_generator()),
        ("summarizer", lambda: _get_summarizer()),
    ]
    for name, fn in jobs:
        threading.Thread(target=_load, args=(name, fn), daemon=True).start()
