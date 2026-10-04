"""Tell prose apart from source code before anything tries to summarise it.

A student notebook is mostly code, and code has no summary: fed straight to a
summariser it produces things like

    "df = pd.read_csv('WA_Fn-UseC_-Telco-Customer-Churn.csv') df.shape"

which is noise presented as insight. This module strips the code out and leaves
the sentences a human actually wrote.

The heuristics are deliberately one-sided. A line is only dropped when several
independent signals agree, because a report line like

    "The dataset contains 7,043 rows and 21 columns after cleaning."

must survive even though it contains numbers, commas and a full stop. Losing a
real sentence is a worse failure than keeping one line of code, because the
user cannot tell the difference between a summary that missed a section and one
that was filtered.
"""

import re

# A line that opens with one of these is a statement, not a sentence. Includes
# the languages these documents actually use: Python, JS/TS, Java, C, SQL.
_STATEMENT_OPENERS = (
    "import ", "from ", "def ", "class ", "return", "print", "for ", "while ",
    "if ", "elif ", "else", "try:", "except", "finally", "with ", "lambda ",
    "pass", "break", "continue", "yield", "assert ", "del ", "global ",
    "nonlocal", "raise ", "async ", "await ", "const ", "let ", "var ",
    "function ", "public ", "private ", "protected ", "static ", "void ",
    "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ",
    "DROP ", "FROM ", "WHERE ", "GROUP BY ", "ORDER BY ",
)

# Markers that are unambiguous on their own.
_STRONG_CODE_MARKERS = (
    "```",            # markdown fence
    "!pip ",          # notebook shell escape
    "!conda ",
    "%matplotlib",    # notebook magic
    "$ pip ",
    ">>> ",           # interactive prompt
    "... ",
    "#!/",            # shebang
    "<?php",
    "</",
    "#include",
    "#define",
    "//",             # C-style comment (checked only when the line starts with it)
    "/*",
    "*/",
    "<!--",
    "SELECT * FROM",
)

_ASSIGNMENT = re.compile(r"^\s*[A-Za-z_$][\w.$]*(?:\s*\[[^\]]*\])*\s*(=|:=|:=)\s*\S")
_BRACKET_CALL = re.compile(r"\w+\s*\([^()]*\)")
_TRAILING_COLON = re.compile(r"^\s*[\w\s.,()\[\]'\"=+-]*:\s*$")
_ONLY_SYMBOLS = re.compile(r"^[\s\d.,;:|+*/<>=_-]*$")
_CAMEL_IDENT = re.compile(r"\b[a-z]+[A-Z][\wA-Z]*\b")
# `df.shape`, `pd.__version__` - an identifier chain with no call or spaces.
_DOTTED_CHAIN = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+")

_DTYPE_TOKEN = re.compile(
    r"^(int\d*|uint\d*|float\d*|bool|object|str|category|datetime64\[?[\w, ]*\]?|"
    r"timedelta64\[?[\w, ]*\]?|Int\d+|Float\d+|boolean|dtype|name)$",
    re.IGNORECASE,
)

_SYMBOLS = set("{}[]()<>=+-*/%&|^~!@#$.,;:\\'\"`?")


def looks_like_code(line: str) -> bool:
    """True when a single line is code (or machine output) rather than prose."""
    stripped = line.strip()
    if not stripped:
        return False

    # Prose always has sentence structure. Requiring at least two spaces between
    # words before any other test keeps ordinary English out of the fast path.
    for marker in _STRONG_CODE_MARKERS:
        if stripped.startswith(marker):
            return True

    if _ONLY_SYMBOLS.match(stripped):
        return True

    lowered = stripped.lower()
    if any(lowered.startswith(op) for op in _STATEMENT_OPENERS):
        # "Return the value of x" is a sentence, "return value of x" is not.
        return True

    if _TRAILING_COLON.match(stripped):
        return True

    words = stripped.split()
    spaced = sum(1 for w in words if " " in w)
    symbol_chars = sum(1 for ch in stripped if ch in _SYMBOLS)
    symbol_ratio = symbol_chars / max(len(stripped), 1)

    # Dense punctuation and no multi-word phrase: code.
    if symbol_ratio > 0.30 and spaced == 0:
        return True
    if symbol_ratio > 0.45:
        return True

    # Several call expressions, no sentence: `df.head().info() df.describe()`.
    calls = len(_BRACKET_CALL.findall(stripped))
    if calls >= 2 and not re.search(r"[.!?:]\s", stripped):
        return True

    # One call with arguments and no spaces at all: `sns.countplot(x='Churn')`.
    if spaced == 0 and "(" in stripped and ")" in stripped:
        if not re.search(r"[.!?:]\s", stripped):
            return True

    # An assignment whose right-hand side is not a sentence.
    if _ASSIGNMENT.match(stripped) and not re.search(r"[.!?:]\s", stripped):
        return True

    # `df.shape`, `model.summary`: an identifier chain on its own.
    if len(stripped) < 40 and " " not in stripped and _DOTTED_CHAIN.fullmatch(stripped):
        return True

    # camelCase/PascalCase identifiers are code with no spaces, e.g. `setxlabel()`.
    if spaced == 0 and _CAMEL_IDENT.search(stripped):
        return True

    # Indented continuation of a previous statement.
    if line[:1] in (" ", "\t") and _ASSIGNMENT.match(stripped):
        return True

    return False


def looks_like_table_dump(line: str) -> bool:
    """A pandas ``df.info()`` / ``describe()`` block: aligned dtype columns."""
    stripped = line.strip()
    if not stripped or "  " not in stripped:
        return False
    columns = stripped.split()
    if len(columns) < 2:
        return False
    if stripped.endswith((".", "!", "?")):
        return False
    dtypes = sum(1 for c in columns if _DTYPE_TOKEN.match(c))
    if dtypes < 2:
        return False
    # Either every column is a dtype/count keyword (`dtype  object`), or the row
    # is indented under such a block (`  int64  float64  ...`).
    return dtypes == len(columns) or line[:1] in (" ", "\t")


def _is_prose_sentence(line: str) -> bool:
    """A line worth keeping: real words, sentence-like length, ends properly."""
    stripped = line.strip()
    if not stripped or len(stripped) < 25:
        return False
    if stripped.count("|") >= 2:          # markdown table row
        return False
    words = stripped.split()
    if len(words) < 5 or len(words) > 90:
        return False
    letters = sum(1 for ch in stripped if ch.isalpha())
    if letters / max(len(stripped), 1) < 0.55:
        return False
    return True


def clean_prose(text: str) -> str:
    """Drop code and machine output, keeping blank-line paragraph structure.

    Returns the original string when almost nothing would be removed, so a normal
    report is never rewritten for the sake of it.
    """
    if not text:
        return ""

    lines = text.split("\n")
    kept = []
    in_fence = False
    dropped = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            dropped += 1
            continue
        if in_fence:
            dropped += 1
            continue

        if not stripped:
            kept.append("")
            continue

        if looks_like_table_dump(line) or looks_like_code(line):
            dropped += 1
            # Keep a paragraph break where code used to be, so the surrounding
            # sentences do not get welded into one paragraph.
            if kept and kept[-1] != "":
                kept.append("")
            continue

        kept.append(line)

    if dropped == 0:
        return text

    cleaned = "\n".join(kept)
    # Collapse the blank-line runs the removals left behind.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def prose_ratio(text: str) -> float:
    """Share of non-empty lines that read as prose rather than code."""
    lines = [ln for ln in (text or "").split("\n") if ln.strip()]
    if not lines:
        return 1.0
    prose = sum(
        1 for ln in lines
        if _is_prose_sentence(ln) and not looks_like_code(ln)
    )
    return prose / len(lines)


def split_prose_sentences(text: str, splitter) -> list:
    """Sentences from `text` that are prose, with headings and glue removed.

    `splitter` is the caller's sentence splitter, injected so this module does not
    have to agree with the summariser about sentence boundaries. Sentences that
    swallowed a heading - which is what happens when a DOCX table cell ends
    without punctuation - are dropped rather than quoted, because
    "Introduction to EDA The Telco dataset contains ..." reads as a glitch.
    """
    out = []
    for line in re.split(r"[\r\n]+", text or ""):
        stripped = line.strip()
        if not stripped or not _is_prose_sentence(stripped):
            continue
        if looks_like_code(stripped) or looks_like_table_dump(stripped):
            continue
        for sentence in splitter(stripped):
            sentence = sentence.strip()
            if not sentence or "\n" in sentence:
                continue
            words = re.findall(r"[A-Za-z][\w'-]{2,}", sentence)
            if len(words) < 6 or len(words) > 60:
                continue
            if sentence not in out:
                out.append(sentence)
    return out