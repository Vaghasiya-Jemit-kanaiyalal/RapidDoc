"""Deterministic text repair shared by the summarizer and the rewriter.

Both the T5 rewriter and the BART summarizer are small seq2seq models running on
CPU. They are good enough to rephrase and compress, but they have two
consistent failure modes that no amount of decoding fixes:

* They emit text that is not a well-formed sentence - no capital, no closing
  punctuation, a dangling clause that stops mid-thought. The user saw summaries
  that read as sentence fragments.
* On grammar-fix requests they paraphrase instead of correcting, or "correct" a
  sentence into a different one. A 77M-parameter model cannot be trusted to
  repair grammar, and when it mangled the result the old code simply returned
  the input unchanged - so "fix the grammar" did nothing at all.

This module does the part that can be done reliably with rules: mechanical
grammar and punctuation repair, and sentence-boundary clean-up. It never rewrites
wording, so it cannot change the author's meaning.

Nothing here is a general-purpose grammar checker. It fixes the errors that
actually show up in this app's documents - duplicated words, article agreement,
missing sentence punctuation, and the handful of confusions that the local
models introduce.
"""

import re

__all__ = [
    "polish_text",
    "polish_sentences",
    "ensure_sentence",
    "split_sentences",
    "looks_like_garbage",
]

# ---------------------------------------------------------------------------
# Word-level confusions that are safe to correct in place.
# Each maps a whole word; matching is case-insensitive and preserves the case
# pattern of the original so a sentence-initial "Teh" becomes "The".
# ---------------------------------------------------------------------------
_WORD_FIXES = {
    # doubled words are handled separately, this is for single typos
    "teh": "the",
    "adn": "and",
    "recieve": "receive",
    "recieved": "received",
    "seperate": "separate",
    "seperated": "separated",
    "definately": "definitely",
    "occured": "occurred",
    "occuring": "occurring",
    "untill": "until",
    "wich": "which",
    "whcih": "which",
    "thier": "their",
    "becuase": "because",
    "usefull": "useful",
    "sucessful": "successful",
    "successfull": "successful",
    "accomodate": "accommodate",
    "embarass": "embarrass",
    "independantly": "independently",
    "independant": "independent",
    "dependant": "dependent",
    "enviroment": "environment",
    "enviornment": "environment",
    "occassion": "occasion",
    "publically": "publicly",
    "reccomend": "recommend",
    "refered": "referred",
    "setted": "set",
    "wich": "which",
    "happend": "happened",
    "wich": "which",
    "there research": "their research",
    "its own": "its own",
    "informations": "information",
    "datas": "data",
    "criterias": "criteria",
    "researches": "research studies",
    "an research": "a research",
    "a hour": "an hour",
    "a idea": "an idea",
    "a image": "an image",
    "a example": "an example",
    "a error": "an error",
    "a study": "a study",
}

# "Hindu-based" is not a corruption the model invented out of nothing: the
# summarizer trained on newswire has a strong prior toward the token "Hindu",
# and "Hindi-based papers" decodes to it. Repairing it needs the document's own
# vocabulary, which the caller supplies.
_CONFUSABLE_BY_CONTEXT = (
    ("hindu", "hindi"),
    ("muslim", "muslim"),
)

# Punctuation that should be followed by a space.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?%)\]])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s*")
_MISSING_SPACE_AFTER_PUNCT = re.compile(r"([,.;:!?])([A-Za-z])")
_REPEATED_PUNCT = re.compile(r"([,;:])\1+")
_REPEATED_PUNCT_2 = re.compile(r"\.{4,}")
_REPEATED_BANG = re.compile(r"!{2,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SPACE_BEFORE_NEWLINE = re.compile(r"[ \t]+\n")

# A repeated word: "the the", "of of", "is is".
_DUP_WORD = re.compile(r"\b(\w+)(\s+)\1\b", re.IGNORECASE)
# Three or more in a row, which the single-pass fix below leaves behind.
_DUP_WORD_RUN = re.compile(r"\b(\w+)(\s+\1\b){2,}", re.IGNORECASE)

# A trailing conjunction or article means the sentence was cut off mid-clause.
_DANGLING_TAIL = re.compile(
    r"\s+(?:and|or|but|the|a|an|of|to|in|on|for|with|that|which|as|by|from|is|are|was|were|"
    r"its|their|this|these|those|than|then|however|therefore|also|because|while)\s*$",
    re.IGNORECASE,
)

# "a"/"an" follows the *sound* of the next word, not its first letter, so two
# kinds of exception are needed. These write with a silent h and therefore take
# "an" despite a consonant letter, and these start with a vowel letter that is
# pronounced as a consonant and therefore take "a".
_SILENT_H_SOUND = re.compile(r"^hour|^honest|^honou?r", re.IGNORECASE)
_CONSONANT_VOWEL_LETTER = re.compile(
    r"^uni|^use[ds]?\b|^user|^usual|^eu\b|^one\b|^once\b|^euro", re.IGNORECASE
)


def _match_case(source: str, replacement: str) -> str:
    """Apply the original word's capitalisation to the replacement."""
    if source.isupper() and len(source) > 1:
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _fix_word_typos(text: str) -> str:
    """Correct single-word typos and confusions, preserving capitalisation."""
    def repl(match):
        word = match.group(0)
        fixed = _WORD_FIXES.get(word.lower())
        return _match_case(word, fixed) if fixed else word

    return re.sub(r"\b[A-Za-z][\w'-]*\b", repl, text)


def _fix_articles(text: str) -> str:
    """Correct ``a``/``an`` agreement.

    Only the sound-changing prefixes that matter are special-cased; the default
    is the plain vowel-letter test.
    """

    def repl(match):
        article, word = match.group(1), match.group(2)
        # Default: the first letter decides, as in standard school grammar.
        vowel = word[:1].lower() in "aeiou"
        if _CONSONANT_VOWEL_LETTER.match(word):
            vowel = False      # "a university", "a user", "a European"
        elif _SILENT_H_SOUND.match(word):
            vowel = True       # "an hour", "an honest answer"
        if article.lower() == "a" and vowel:
            return "an " + word
        if article.lower() == "an" and not vowel:
            return "a " + word
        return match.group(0)

    return re.sub(r"\b([Aa]n?)\s+([A-Za-z][\w'-]*)", repl, text)


def _fix_doubled_words(text: str) -> str:
    """Collapse ``the the`` style repeats without touching legitimate doubles."""
    text = _DUP_WORD_RUN.sub(lambda m: m.group(1), text)
    return _DUP_WORD.sub(lambda m: m.group(1), text)


def _fix_confusables(text: str, vocabulary) -> str:
    """Repair confusions using the document's own vocabulary.

    ``Hindu`` -> ``Hindi`` is only a safe correction when the document actually
    uses "Hindi"; guessing would introduce the very error being fixed.
    """
    if not vocabulary:
        return text
    lowered_vocab = {w.lower() for w in vocabulary}

    def repl(match):
        word = match.group(0)
        if word.lower() not in lowered_vocab:
            return word
        for bad, good in _CONFUSABLE_BY_CONTEXT:
            if word.lower() == bad and good in lowered_vocab:
                return _match_case(word, good)
        return word

    # Apostrophes stay inside a token (don't, it's); hyphens must not, otherwise
    # "Hindu-based" is looked up whole, is absent from the vocabulary, and the
    # confusable is never corrected.
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", repl, text)


_EXTENSION_AFTER_DOT = re.compile(
    r"\b[A-Za-z][\w-]*\.(?:js|jsx|ts|tsx|mjs|cjs|yml|yaml|json|py|rb|go|rs|java|php|sh|bash|md|txt|csv|html|css|scss|sql|env|lock|toml|ini|cfg|conf|xml|com|org|net|io|dev|app|edu|gov)\b",
    re.IGNORECASE,
)
# A dotfile such as ".env" or a relative path such as "./src" or "../data".
_DOTFILE = re.compile(r"(?<![\w.])\.[A-Za-z][\w.-]*")
_DOT_GUARD_PUNCT = "\x00"


def _tidy_punctuation(text: str) -> str:
    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = _REPEATED_PUNCT_2.sub("...", text)
    text = _REPEATED_BANG.sub("!", text)
    # Hide the dot of a filename or domain first. "Node.js" is one word, and the
    # missing-space rule below would otherwise rewrite it to "Node. js" - the
    # exact artefact this whole pass exists to remove.
    text = _EXTENSION_AFTER_DOT.sub(
        lambda m: m.group(0).replace(".", _DOT_GUARD_PUNCT), text)
    # Likewise ".env": without this the space-before-punctuation rule glues the
    # article onto it, turning "the .env file" into "the.env file".
    text = _DOTFILE.sub(
        lambda m: m.group(0).replace(".", _DOT_GUARD_PUNCT), text)
    # guard abbrs
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    # Restore only at the very end: both space rules above match " ." and would
    # otherwise glue "the .env file" into "the.env file".
    return text.replace(_DOT_GUARD_PUNCT, ".")


def _cap_first(text: str) -> str:
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1:]
        if ch not in " \t\n\r\"'([{":
            break
    return text


def ensure_sentence(text: str) -> str:
    """Give a fragment a capital and a closing full stop.

    Abstractive decoders reliably forget both, which is why summaries arrived
    reading like ``Theoretical research papers were identified in each category
    achievements have been made in the past in the field of``.
    """
    text = (text or "").strip()
    if not text:
        return ""
    text = _cap_first(text)
    if text[-1] not in ".!?":
        # A dangling conjunction means the thought stopped halfway; cutting the
        # clause is better than shipping a fragment that trails off.
        trimmed = _DANGLING_TAIL.sub("", text)
        if len(trimmed.split()) >= 4:
            text = trimmed
        text = text.rstrip(" ,;:-") + "."
    return text


# A trailing sentence fragment like "in each category achievements have been
# made" is two sentences run together with no punctuation. Splitting on a
# subject-verb boundary is too risky in general, but a capital-less continuation
# after a noun phrase is common enough in these decodes to be worth one pass.
_MISSING_SENTENCE_BREAK = re.compile(
    r"(?<=[\.\?\!])\s+"
    r"(?=[A-Z])"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[]|\d)")

# "Node.js", "ci.yml", "App.jsx": the period belongs to the filename, not to a
# sentence end. Protecting it keeps the splitter from emitting "Node. js".
_DOTTED_TOKEN = re.compile(r"\b([A-Za-z])\.([A-Za-z])\b")
_DOT_GUARD = "\x00"

# Abbreviations that end in a period but do not end a sentence.
_ABBREVIATIONS = frozenset("""
e.g i.e etc vs etc. mr mrs ms dr prof fig no vol op cit al approx
jan feb mar apr jun jul aug sep sept oct nov dec
""".split())

# A sentence break followed by a lowercase word: "...with React. lazy() and
# Suspense." Splitting only before capitals glued these together, so a stray code
# fragment stayed attached to a real sentence and passed every check.
_SOFT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[a-z(\[])")

# Text carrying code punctuation is a fragment, not prose. Summaries that leak
# these are the "Hint: make sure MongoDB connection failed:', err" failure.
_CODE_PUNCT = re.compile(r"""['"`]\s*[,:;)]|[:;,]\s*['"`]\s|[(){}[\]<>]|=>|\|\||;\s*$""", re.IGNORECASE)


def _looks_like_code(text: str) -> bool:
    return bool(_CODE_PUNCT.search(text))


def _split_soft(text: str) -> list:
    out = []
    for part in _SOFT_BREAK.split(text):
        part = part.strip()
        if not part:
            continue
        # Do not break "Dr." / "e.g." style abbreviations.
        m = re.search(r"([A-Za-z.]+)\.$", part)
        if m and m.group(1).lower().strip(".") in _ABBREVIATIONS:
            out.append(part)
            continue
        out.append(part)
    return out


def split_sentences(text: str) -> list:
    """Split text into sentences, discarding fragments that are too short."""
    text = (text or "").strip()
    if not text:
        return []
    guarded = _DOTTED_TOKEN.sub(rf"\1{_DOT_GUARD}\2", text)
    parts = []
    for chunk in _SENTENCE_SPLIT.split(guarded):
        parts.extend(_split_soft(chunk))
    return [
        p.replace(_DOT_GUARD, ".")
        for p in (q.strip() for q in parts)
        if p and len(p.replace(_DOT_GUARD, ".").split()) >= 3
    ]


def polish_sentences(text: str, vocabulary=None) -> list:
    """Clean a block of text and return it as a list of proper sentences."""
    text = (text or "").strip()
    if not text:
        return []
    text = _fix_confusables(text, vocabulary)
    text = _fix_doubled_words(text)
    text = _fix_word_typos(text)
    text = _tidy_punctuation(text)
    text = _fix_split_filenames(text)
    text = _fix_subject_verb(text)
    text = _fix_articles(text)
    out = []
    for sentence in split_sentences(text):
        if _looks_like_code(sentence):
            continue
        # A sentence that starts lower-case after a full stop is a real
        # grammatical error ("...not good. it is a hour delay").
        sentence = ensure_sentence(sentence)
        if sentence and len(sentence.split()) >= 3:
            out.append(sentence)
    if not out:
        for sentence in split_sentences(text):
            sentence = ensure_sentence(sentence)
            if sentence and len(sentence.split()) >= 3:
                out.append(sentence)
                break
    if not out:
        fallback = ensure_sentence(text)
        return [fallback] if fallback else []
    return out


def looks_like_garbage(text: str) -> bool:
    """True when a decode is too damaged to show to a user."""
    text = (text or "").strip()
    if len(text) < 15:
        return True
    words = text.split()
    if not words:
        return True
    # Mostly non-alphabetic tokens means the model fell apart.
    alpha = sum(1 for w in words if any(c.isalpha() for c in w))
    if alpha / len(words) < 0.6:
        return True
    if len(set(w.lower() for w in words)) < max(2, len(words) // 6):
        return True
    return False


# Nouns that end in "s" but are singular. Without this list a blanket
# "plural noun + singular verb" rule turns "This is" into "This are".
_SINGULAR_S = frozenset("""
this its his hers yours ours theirs thus plus minus always unless across
towards series species means news analysis basis crisis diagnosis emphasis
hypothesis parenthesis thesis oasis axis genesis campus focus status process
access address class glass grass mass pass success stress business witness
gas bus lens virus bonus census syllabus corpus fungus genus atlas circus
chaos canvas bias alias bias us was is has does yes less its ethics physics
politics economics statistics mathematics gymnastics measles rabies
""".split())

_PLURAL_VERB = {
    "is": "are", "was": "were", "has": "have", "does": "do",
}
# A plural subject is only trusted directly after a determiner or quantifier.
_DETERMINER = (
    r"(?:the|a|an|these|those|all|both|many|most|some|few|several|"
    r"their|our|your|his|her|its|two|three|four|five|six|seven|eight|nine|ten)"
)


def _fix_subject_verb(text: str) -> str:
    """"The frontends was loaded" -> "The frontends were loaded".

    Applied only to a plain-s noun directly after a determiner and not in the
    singular-s list, which keeps it from mangling "This is" or "Analysis shows".
    """
    pattern = (
        rf"\b({_DETERMINER}\s+(?:[A-Za-z][A-Za-z']*\s+){{0,2}}?)"
        rf"([A-Za-z][A-Za-z']*s)\s+(is|was|has|does)\b"
    )

    def repl(match):
        noun = match.group(2)
        if noun.lower() in _SINGULAR_S:
            return match.group(0)
        verb = match.group(3).lower()
        return f"{match.group(1)}{noun} {_PLURAL_VERB[verb]}"

    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def _fix_split_filenames(text: str) -> str:
    """Re-join filenames a decoder split at their dot: "Node. js" -> "Node.js".

    The small summariser detokenises these apart, and the sentence splitter then
    treats the orphaned "js" as a new word. Only known extensions and dotfiles are
    rejoined, so an ordinary sentence break is left alone.
    """
    ext = r"(?:js|jsx|ts|tsx|mjs|cjs|yml|yaml|json|py|rb|go|rs|java|php|sh|bash|md|txt|csv|html|css|scss|sql|env|lock|toml|ini|cfg|conf|xml)"
    text = re.sub(rf"([A-Za-z])\.\s+({ext})\b", r"\1.\2", text)
    # Dotfiles: "backend (. env)" -> "backend (.env)"
    text = re.sub(r"\(\s*\.\s+([a-z][\w-]*)\s*\)", r"(.\1)", text)
    # "at. github/workflows/ci. yml" -> "at .github/workflows/ci.yml"
    text = re.sub(
        r"\b(at|in|on|from|to|under|inside|within|via)\.\s+([a-z][\w./-]*)",
        r"\1 .\2", text)
    return text


def _cap_sentence_starts(text: str) -> str:
    """Capitalise the first letter of every sentence and paragraph.

    Leaves the author's paragraph breaks exactly as written, and never touches a
    line that is code.
    """
    out = []
    for line in text.split("\n"):
        if _looks_like_code(line):
            out.append(line)
            continue

        def repl(match):
            return match.group(1) + _cap_first(match.group(2))

        # Start of the line, and the position after any sentence terminator.
        line = re.sub(r"(^|(?<=[.!?]\s))(\s*)([a-z])", lambda m: m.group(1) + m.group(2) + m.group(3).upper(), line)
        out.append(line)
    return "\n".join(out)


def polish_text(text: str, vocabulary=None) -> str:
    """Full clean-up of a block of prose, preserving paragraph breaks."""
    raw = (text or "").strip()
    if not raw:
        return ""

    text = _fix_confusables(raw, vocabulary)
    text = _fix_doubled_words(text)
    text = _fix_word_typos(text)
    text = _tidy_punctuation(text)
    # Must follow _tidy_punctuation: that pass collapses " .", which would
    # undo "at .github", and adds a space after a dot, which would undo ".env".
    text = _fix_split_filenames(text)
    text = _fix_subject_verb(text)
    text = _fix_articles(text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_NEWLINE.sub("\n", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    text = _cap_sentence_starts(text)

    # Only re-punctuate when the text has no sentence structure at all. Text
    # that already reads as sentences keeps exactly the author's own breaks.
    if not re.search(r"[.!?]", text):
        text = ensure_sentence(text)

    return text.strip()
