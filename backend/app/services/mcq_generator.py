"""Deterministic, varied MCQ generation from a document's own text.

The local MCQ brain is a BART model fine-tuned on RACE, a reading-comprehension
dataset whose questions are overwhelmingly of two forms: "which of the following
is NOT mentioned..." and "which statement is NOT true...". Asking it for a quiz
therefore produced five near-identical negative questions, distractors lifted
from other documents, and the occasional option that was itself a question
("What is the main purpose of the research paper?" as an answer choice).

A small fine-tuned model cannot be talked out of its training distribution with
a better prompt. This module sidesteps it: it reads the document, pulls real
facts out of it, and writes questions from templates, using the document's own
vocabulary to build plausible wrong answers. Nothing is invented, so every
question is answerable from the text and every distractor is at least topical.

The generators below each target a different cognitive level, which is what
makes the resulting quiz varied:

* ``recall``     - what does the document state? (direct fact retrieval)
* ``definition`` - what does the document call this thing? (terminology)
* ``purpose``    - why is X done? (reasoning about intent)
* ``cause``      - what follows from / because of X? (causal reasoning)
* ``numeric``    - what figure does the document give? (data recall)
* ``list``       - which of these is NOT part of X? (the negative form, used
                   sparingly because it was the only form being produced before)
* ``statement``  - which statement about the document is true? (verification)

:func:`build_mcq_set` interleaves the generators so a request for five questions
produces five different kinds rather than five of the easiest kind.
"""

import re

__all__ = ["build_mcq_set", "QUESTION_TYPES"]

QUESTION_TYPES = (
    "recall",
    "definition",
    "purpose",
    "cause",
    "numeric",
    "statement",
)

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][\w'-]*")

# Words too common to make a useful distractor: "the document states that the
# system was used" is not a plausible wrong answer to anything.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those there here it its it's
is are was were be been being am do does did done have has had having will
would shall should can could may might must of in on at to for from by with
without about into over under again further once all any both each few more
most other some such no nor not only own same so too very s t just don now
as also which who whom whose what when where why how between during before
after above below up down out off because while since until against
document documents paper papers study studies research section text passage
according mentioned states stated describes described says say says note notes
following given provides provided based used using one two three
four five six seven eight nine ten
""".split())

# Verbs, adverbs and vague words. These must never be an answer: "which is
# connected with Props - Pass or React?" is not a question worth asking.
_WEAK_WORDS = frozenset("""
create created creating adds added adding use used using uses run runs running
write writes writing written build builds building made make makes making
include includes including included require requires required requireing
pass passes passing passsed passsed sent send sends sent set sets setting
must should shall will would can could may might need needs needed
structure structured structuring compose composed composing duplicate
duplicated get gets getting got check checks checked checking run ran
bundle bundled successfully successfully successful success result results
resulting lead leads led cause causes caused follow follows followed
through above below between within without across during before after
well good better best first second third next last final finally
new old good also only just even still already always never often sometimes
like unlike same different various several many few more most less least
practical objective conclusion project structure implementation component
components page pages document text line lines word words time times
""".split())

# Verbs and structures that make a good "definition" cue.
_DEFINITION_PATTERNS = (
    re.compile(r"^(?P<term>[A-Z][\w \-]{2,40}?)\s+(?:is|are)\s+(?:defined|described|known|referred\s+to|called|termed)\s+as\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[A-Z][\w \-]{2,40}?)\s*[:\-–]\s*(?P<def>.+)$"),
    re.compile(r"^(?P<term>[\w \-]{3,40}?)\s+(?:refers\s+to|means|denotes)\s+(?P<def>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<term>[A-Z][\w \-]{2,40}?)\s+(?:stands\s+for|comprises|consists\s+of|includes)\s+(?P<def>.+)$", re.IGNORECASE),
)

_PURPOSE_RE = re.compile(
    r"^(?P<subj>.{10,160}?)\s+(?:is|are|was|were)\s+(?:used|designed|intended|employed|adopted|created|developed|performed|carried\s+out|conducted)\s+"
    r"(?:to|for|in\s+order\s+to|as\s+a\s+means\s+to)\s+(?P<purp>.+)$",
    re.IGNORECASE,
)

_CAUSE_RE = re.compile(
    r"^(?:because|since|as|due\s+to|owing\s+to|thanks\s+to|on\s+account\s+of)\s+(?P<cause>.+?)"
    r"(?:,|\.|;| which | that | so | leading\s+to | resulting\s+in )",
    re.IGNORECASE,
)
_EFFECT_RE = re.compile(
    r"^(?P<cause>.{10,140}?)\s*,?\s+(?:which\s+)?(?:leads?|led|results?|resulted|causes?|caused|gives?|gave|means?|makes?|made)\s+"
    r"(?:to\s+)?(?P<effect>.+)$",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(
    r"(?P<value>\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent|per\s+cent|students|people|items|rows|columns|"
    r"pages|years|days|hours|minutes|seconds|points|marks|units|files|lines|words|"
    r"times|lakh|crore|million|billion|thousand)?)\b",
    re.IGNORECASE,
)

# An option that is itself a question is never a valid answer choice; the BART
# brain produced these ("What is the main purpose of the research paper?").
_QUESTION_LIKE = re.compile(r"^(what|which|who|whom|whose|when|where|why|how|is|are|was|were|do|does|did|can|could|should|will|would)\b", re.IGNORECASE)
_ASKING = re.compile(r"\?\s*$")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


# Source lines that are code, shell commands or file trees. They are excellent
# material for a code slide and useless as quiz content, and left in the pool
# they produce questions like "Which is NOT a command: src/ or Vite?".
_CODE_LINE = re.compile(
    r"(^\s*[└├│]|^\s*\$|^\s*npm |^\s*npx |^\s*yarn |^\s*cd |^\s*git |"
    r"[\w-]+\.(?:jsx?|tsx?|py|json|html|css|md|csv|pdf|docx)\b|"
    r"^\s*[\)\]\}]|=>|;\s*$|\{\s*$)",
    re.IGNORECASE,
)


def _is_code_like(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if _CODE_LINE.search(text):
        return True
    # A line that is mostly punctuation is a code fragment, not a sentence.
    words = text.split()
    alpha = sum(1 for w in words if any(c.isalpha() for c in w))
    return bool(words) and alpha / len(words) < 0.7


def sentences_of(text: str, min_words: int = 6, max_words: int = 90) -> list:
    """Split a block of text into usable, quiz-worthy sentences in document order.

    Code, shell commands and file-tree lines are dropped: they make nonsense
    questions and distractors.
    """
    out = []
    for block in re.split(r"[\n\r]+", text or ""):
        for raw in _SENTENCE_SPLIT.split(block):
            s = _clean(raw)
            words = s.split()
            if not (min_words <= len(words) <= max_words):
                continue
            if _is_code_like(s):
                continue
            out.append(s)
    return out


def _content_words(sentence: str) -> list:
    """Distinctive words of a sentence, usable as answer candidates or distractors.

    Stopwords and generic verbs are dropped here rather than in each caller: a
    distractor like "Least" or "Include" is worse than no question at all.
    """
    out = []
    for m in _WORD.finditer(sentence):
        w = m.group(0).lower()
        if w in _STOPWORDS or w in _WEAK_WORDS or len(w) < 4 or w.isdigit():
            continue
        if _is_code_like(m.group(0)):
            continue
        if w not in out:
            out.append(w)
    return out


def _key_terms(text: str, limit: int = 40) -> list:
    """The document's characteristic vocabulary, most distinctive first.

    Frequency alone favours boilerplate, so terms are scored by frequency and
    boosted when they look like proper nouns or multi-word technical phrases -
    exactly the things worth asking about.
    """
    counts = {}
    for m in _WORD.finditer(text or ""):
        w = m.group(0)
        low = w.lower()
        if low in _STOPWORDS or low in _WEAK_WORDS or len(low) < 3 or low.isdigit():
            continue
        counts[low] = counts.get(low, 0) + 1

    phrases = {}
    # Only spaces join a multi-word phrase - letting \s match a newline welded
    # the end of one cell onto the start of the next ("Component Architecture\nObjective").
    for m in re.finditer(r"\b([A-Z][\w-]{2,}(?:[ ][A-Z][\w-]{2,}){0,2})\b", text or ""):
        p = m.group(1).strip()
        if p.lower() not in _STOPWORDS and not _is_code_like(p):
            # Key on the lowercase form so a phrase and the same word counted
            # individually do not both enter the pool as near-duplicate options.
            key = p.lower()
            phrases[key] = phrases.get(key, 0) + 1
            if key not in counts:
                counts[key] = 0

    scored = []
    for word, n in counts.items():
        if _is_code_like(word):
            continue
        bonus = 1.6 if word[:1].isupper() else 1.0
        scored.append((n * bonus, word.title(), word))
    for phrase, n in phrases.items():
        if n <= 0:
            continue
        display = " ".join(w.capitalize() if w.isupper() is False else w
                           for w in phrase.split())
        scored.append((n * 2.0, display, phrase))

    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    seen = set()
    for _s, display, key in scored:
        if key in seen:
            continue
        seen.add(key)
        out.append(display)
        if len(out) >= limit:
            break
    return out


def _plausible_option(text: str) -> bool:
    """Reject options that cannot serve as an answer choice."""
    text = _clean(text)
    if len(text) < 2 or len(text.split()) > 22:
        return False
    if _ASKING.search(text) or _QUESTION_LIKE.match(text):
        return False
    # Needs at least one real word.
    return any(w.lower() not in _STOPWORDS and len(w) > 1 for w in _WORD.findall(text))


def _pick_distractors(answer: str, pool: list, need: int, seed_terms: list) -> list:
    """Choose wrong options that are topical but not the answer.

    The answer's own words are excluded so an option cannot be accidentally
    correct as well, and an option already present is never repeated.
    """
    answer_words = {w.lower() for w in _WORD.findall(answer)}
    chosen = []
    seen = {_normalize_option(answer)}
    for candidate in pool:
        if len(chosen) >= need:
            break
        text = _clean(candidate)
        if not _plausible_option(text):
            continue
        norm = _normalize_option(text)
        if norm in seen:
            continue
        words = {w.lower() for w in _WORD.findall(text)}
        if not words:
            continue
        # Too much overlap with the answer means it could also be correct.
        if answer_words and len(words & answer_words) / len(words) > 0.8:
            continue
        seen.add(norm)
        chosen.append(text)
    return chosen


def _normalize_option(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _shuffle_with_answer(options: list, answer_text: str, rotate: int):
    """Place the answer at a rotating position.

    Always putting the correct answer in slot A is a real flaw in a generated
    quiz - a student can score full marks by answering "A" every time.
    """
    if not options or answer_text is None:
        return list(options), None
    try:
        idx = options.index(answer_text)
    except ValueError:
        return list(options), None

    target = rotate % len(options)
    if idx != target:
        options = list(options)
        options.insert(target, options.pop(idx))
    return options, chr(ord("A") + target)


# ---------------------------------------------------------------------------
# Question generators. Each returns a full question dict or None.
# ---------------------------------------------------------------------------

def _q(stem: str, answer: str, distractors: list, kind: str, source: str) -> dict:
    return {
        "question": stem,
        "answer_text": answer,
        "distractors": distractors,
        "type": kind,
        "source": source,
    }


_TITLE_LIKE = re.compile(r"^[^:]{1,60}[:\-–]\s*\S")


def _is_title_like(sent: str) -> bool:
    """A heading is not quiz material - blanking a word out of one is nonsense."""
    return bool(_TITLE_LIKE.match(sent))


def gen_recall(sentences, terms, vocabulary, rotate):
    """Direct fact retrieval: a blanked keyword, answered from the sentence.

    Distractors are taken from the *other* sentences where possible. Global
    keyword order tends to hand every question the same three words (Skills,
    Footer, Header), which makes the options recognisable rather than tempting.
    """
    key_set = {_normalize_option(t) for t in terms}
    for idx, sent in enumerate(sentences):
        if _is_title_like(sent):
            continue
        for m in re.finditer(r"\b([A-Za-z][\w-]{4,})\b", sent):
            term = m.group(1)
            low = term.lower()
            if low in _STOPWORDS or low in _WEAK_WORDS or low.isdigit() or _is_code_like(term):
                continue
            # Only blank a word that is a genuine key term of the document,
            # otherwise the answer is an arbitrary long word.
            is_proper = term[:1].isupper() and m.start(1) > 0
            if _normalize_option(term) not in key_set and not is_proper:
                continue
            blanked = _clean(sent[:m.start(1)] + "____" + sent[m.end(1):])
            if blanked.count("____") != 1:
                continue
            answer = term

            elsewhere = []
            for j, other in enumerate(sentences):
                if j == idx:
                    continue
                for w in _content_words(other):
                    if w != low:
                        elsewhere.append(w.title())
            pool = elsewhere + list(terms)
            distractors = _pick_distractors(answer, pool, 3, terms)
            if len(distractors) < 3:
                continue
            return _q(blanked, answer, distractors[:3], "recall", sent)
    return None


def gen_association(sentences, terms, vocabulary, rotate):
    """"Which of these does the document connect with <phrase>?"

    The answer is a term that genuinely appears in the named sentence; the three
    distractors come from elsewhere in the document, so only one is defensible.
    """
    key_set = {_normalize_option(t) for t in terms}
    for idx, sent in enumerate(sentences):
        if _is_title_like(sent):
            continue
        cue = None
        for m in re.finditer(r"\b([A-Z][\w-]{3,}(?:[ ][A-Z][\w-]{3,}){0,2})\b", sent):
            candidate = m.group(1)
            if _normalize_option(candidate) in vocabulary and not _is_code_like(candidate):
                cue = candidate
                break
        if not cue:
            continue

        local = [
            w for w in _content_words(sent)
            if w != _normalize_option(cue)
            and w not in _STOPWORDS
            and w not in _WEAK_WORDS
            and (_normalize_option(w.title()) in key_set or w in vocabulary)
        ]
        if not local:
            continue
        answer = local[0].title()

        elsewhere = []
        for j, other in enumerate(sentences):
            if j == idx:
                continue
            elsewhere.extend(w.title() for w in _content_words(other))
        pool = [w for w in elsewhere if _normalize_option(w) != _normalize_option(answer)]
        distractors = _pick_distractors(answer, pool, 3, terms)
        if len(distractors) < 3:
            continue
        return _q(
            f'According to the document, which of the following is connected with "{cue}"?',
            answer, distractors[:3], "association", sent)
    return None


def gen_definition(sentences, terms, vocabulary, rotate):
    """"According to the document, what is <term>?" - terminology questions."""
    for sent in sentences:
        # A heading like "Practical 1: Introduction to React" is not a
        # definition; matching it produced a question that only restated the
        # document's own title.
        if _TITLE_LIKE.match(sent):
            continue
        for pattern in _DEFINITION_PATTERNS:
            m = pattern.match(sent)
            if not m:
                continue
            term = _clean(m.group("term"))
            if not term or term.lower() in _STOPWORDS or len(term) < 3:
                continue
            if len(term.split()) > 6:
                continue
            pool = [t for t in terms if _normalize_option(t) != _normalize_option(term)]
            distractors = _pick_distractors(term, pool, 3, terms)
            if len(distractors) < 3:
                continue
            options, letter = _shuffle_with_answer(
                distractors[:3] + [term], term, rotate)
            return _q(
                f'According to the document, which term is described as '
                f'"{_clean(m.group("def"))[:90]}"?',
                term, distractors[:3], "definition", sent)
    return None


def gen_purpose(sentences, terms, vocabulary, rotate):
    """"Why is X done?" - intent questions from 'is used to' structures."""
    for sent in sentences:
        m = _PURPOSE_RE.match(sent)
        if not m:
            continue
        subject = _clean(m.group("subj"))
        purpose = _clean(m.group("purp")).rstrip(".")
        if len(purpose.split()) < 3 or len(purpose.split()) > 24:
            continue
        stem_subject = subject if len(subject.split()) <= 12 else " ".join(subject.split()[:12])
        pool = [s for s in sentences if _normalize_option(s) != _normalize_option(purpose)]
        distractors = _pick_distractors(purpose, pool, 3, sentences)
        if len(distractors) < 3:
            # Fall back to term-based distractors when no other sentence is usable.
            distractors = _pick_distractors(purpose, terms, 3, terms)
        if len(distractors) < 3:
            continue
        options, letter = _shuffle_with_answer(
            distractors[:3] + [purpose], purpose, rotate)
        return _q(
            f"According to the document, what is {stem_subject} used for?",
            purpose, distractors[:3], "purpose", sent)
    return None


def gen_cause(sentences, terms, vocabulary, rotate):
    """Cause/effect questions, from both 'because' and 'leads to' phrasing."""
    for sent in sentences:
        m = _EFFECT_RE.match(sent)
        if not m:
            continue
        cause = _clean(m.group("cause"))
        effect = _clean(m.group("effect")).rstrip(".")
        if not (3 <= len(effect.split()) <= 24):
            continue
        if len(cause.split()) < 3:
            continue
        pool = [s for s in sentences if _normalize_option(s) != _normalize_option(effect)]
        distractors = _pick_distractors(effect, pool, 3, sentences)
        if len(distractors) < 3:
            distractors = _pick_distractors(effect, terms, 3, terms)
        if len(distractors) < 3:
            continue
        options, letter = _shuffle_with_answer(
            distractors[:3] + [effect], effect, rotate)
        return _q(
            f'According to the document, "{_clean(cause)[:110]}" is described as leading to:',
            effect, distractors[:3], "cause", sent)
    return None


def gen_numeric(sentences, terms, vocabulary, rotate):
    """Figure recall: "How many ... does the document mention?"."""
    for sent in sentences:
        for m in _NUMBER_RE.finditer(sent):
            value = _clean(m.group("value"))
            if len(value) < 2:
                continue
            before = _clean(sent[:m.start()])
            after = _clean(sent[m.end():])
            # Frame the question with whichever side of the number has content.
            if len(before.split()) >= 3:
                stem = f"According to the document, {before[0].lower() + before[1:] if before else ''} ___?"
            else:
                stem = f'According to the document, the value given for "{before or after[:60]}" is:'
            # Wrong numbers: other figures from the document, else plausible variants.
            pool = []
            for other in sentences:
                for om in _NUMBER_RE.finditer(other):
                    v = _clean(om.group("value"))
                    if v and v != value:
                        pool.append(v)
            if len(pool) < 3:
                base = re.sub(r"[^\d.]", "", value) or "5"
                try:
                    n = float(base)
                except ValueError:
                    continue
                for mult in (2, 3, 0.5):
                    alt = base if mult == 1 else f"{n * mult:g}"
                    pool.append(f"{alt}{value[len(base):]}")
            distractors = _pick_distractors(value, pool, 3, terms)
            if len(distractors) < 3:
                continue
            options, letter = _shuffle_with_answer(
                distractors[:3] + [value], value, rotate)
            return _q(stem, value, distractors[:3], "numeric", sent)
    return None


def gen_statement(sentences, terms, vocabulary, rotate):
    """"Which statement about the document is correct?"

    Built by taking a real sentence as the true statement and mutating one
    concrete term in three fakes, so exactly one option can be supported by the
    text.
    """
    for sent in sentences:
        words = sent.split()
        if len(words) < 8:
            continue
        # Mutate a plain content word. Substituting a proper noun inside a title
        # produces nonsense like "Skills 1: Introduction to React" rather than a
        # believable false statement.
        keywords = [w for w in words
                    if w[:1].islower()
                    and w.lower().strip(".,;:") not in _STOPWORDS
                    and len(w.strip(".,;:")) > 4
                    and not w.strip(".,;:").isdigit()
                    and not _is_code_like(w)]
        if len(keywords) < 2:
            continue
        target = keywords[len(keywords) // 2]
        term_pool = [t for t in terms if _normalize_option(t) != _normalize_option(target)]

        fakes = []
        for replacement in term_pool:
            mutated = sent.replace(target, replacement, 1)
            if mutated == sent or not _plausible_option(mutated):
                continue
            # The substitution has to be visible early. Replacing a word late in
            # a long sentence left all four options sharing their first 40
            # characters, so they were indistinguishable on screen.
            head = min(len(mutated), len(sent), 60).lower()
            if mutated[:60].lower() == sent[:60].lower():
                continue
            if _normalize_option(mutated[:40]) == _normalize_option(sent[:40]):
                continue
            fakes.append(mutated)
            if len(fakes) == 3:
                break
        if len(fakes) < 3:
            continue
        return _q(
            "Which of the following statements about the document is correct?",
            sent, fakes[:3], "statement", sent)
    return None


_GENERATORS = (
    gen_recall,
    gen_definition,
    gen_association,
    gen_purpose,
    gen_cause,
    gen_numeric,
    gen_statement,
)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _finalize(raw: dict, rotate: int) -> dict:
    """Turn a raw generator result into the app's question shape."""
    answer_text = raw.get("answer_text")
    distractors = list(raw.get("distractors") or [])

    if not answer_text:
        return None

    options = distractors[:3] + [answer_text]
    if len(options) < 4:
        return None
    if len({_normalize_option(o) for o in options}) < 4:
        return None
    options, letter = _shuffle_with_answer(options, answer_text, rotate)
    if not letter:
        return None
    return {
        "question": raw["question"],
        "options": options,
        "answer": letter,
        "type": raw.get("type") or "recall",
        "complete": True,
    }


def build_mcq_set(text: str, count: int = 5, skip_stems=None, max_per_type: int = 1) -> list:
    """Build up to `count` varied questions from `text`.

    Generators are run in a fixed rotation and each takes the first sentence
    pattern it can use, so successive questions come from different parts of the
    document and different cognitive levels. `count` above the number of
    distinct patterns available simply returns fewer questions rather than
    repeating one.

    `skip_stems` holds question stems already used, and `max_per_type` caps how
    many questions one cognitive level may contribute, so a caller can ask for a
    wider set of a document it has partly mined already.
    """
    text = (text or "").strip()
    if not text:
        return []

    sentences = sentences_of(text)
    if len(sentences) < 2:
        return []
    terms = _key_terms(text)
    vocabulary = {t.lower() for t in terms}

    built = []
    seen_stems = {_normalize_option(s) for s in (skip_stems or [])}
    per_type = {}
    # Rotate the starting generator so a two-question request does not always
    # return the same two types.
    order = list(_GENERATORS)
    if len(order) > 1:
        order = order[1:] + order[:1]

    def attempt(step, type_cap):
        if len(built) >= count:
            return
        gen = order[step % len(order)]
        # Each generator starts scanning at a different point in the document.
        # Without this every generator matched the first sentence it could, so a
        # five-question set was five questions about the document's title line.
        offset = (step * 3) % max(1, len(sentences))
        window = sentences[offset:] + sentences[:offset]
        try:
            raw = gen(window, terms, vocabulary, rotate=len(built))
        except Exception:
            return
        if not raw:
            return
        kind = raw.get("type") or "recall"
        if per_type.get(kind, 0) >= type_cap:
            return
        q = _finalize(raw, rotate=len(built))
        if not q or not q.get("complete"):
            return
        key = _normalize_option(q["question"])
        if key in seen_stems:
            return
        seen_stems.add(key)
        per_type[kind] = per_type.get(kind, 0) + 1
        built.append(q)

    # First pass: one question per type, so a set spans as many cognitive levels
    # as the document supports. `gen_association` matches far more often than the
    # rest, so without this cap a six-question set was three "connected with"
    # questions and one each of everything else.
    for step in range(max(count, 1) * 3):
        if len(built) >= count:
            break
        attempt(step, max_per_type)

    # Second pass: allow another question per type only if the document was too
    # thin to fill the request.
    for step in range(max(count, 1) * 3):
        if len(built) >= count:
            break
        attempt(step, max_per_type + 1)

    return built
