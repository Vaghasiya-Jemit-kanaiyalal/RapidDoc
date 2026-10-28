"""Quiz questions must teach document content, not repeat broken PDF lines.

The reported failure was a quiz made of line fragments: ``document-``,
``ments, along with the`` and blanks such as ``aware ____``. These tests pin the
quality gate that rejects incomplete PDF sentences before a question template
ever sees them.
"""

import pytest

from RapidDoc.backend.app.services import gemini_service
from RapidDoc.backend.app.services.document_text import clean_prose
from RapidDoc.backend.app.services.gemini_service import generate_mcqs
from RapidDoc.backend.app.services.mcq_generator import _is_complete_sentence
from RapidDoc.backend.app.services.summary_text import normalize_extracted_text


HARD_WRAPPED_DOC = """DocEdit contains more than 17k PDF and 10k design template documents.
The dataset contains 28K user edit requests. We also propose DocEditor, a
Transformer-based multimodal model that performs the new task. The retrieval
module is used to collect relevant text from the document image. The encoder is
used to represent document objects and text tokens. The decoder is used to predict
edit commands for ambiguous user requests. The evaluation suite is used to measure
the accuracy of generated commands. Our proposed model outperforms other baseline
approaches by 15-18%, providing a strong starting point for future work. Because
user requests are ambiguous, the system must interpret the visual cues in the
document. The model combines textual and visual features, which leads to more
accurate command prediction."""


@pytest.fixture(autouse=True)
def no_model_fallback(monkeypatch):
    """Only exercise the deterministic document-grounded generator."""
    monkeypatch.setattr(gemini_service, "generate_mcq", lambda *a, **k: None)
    monkeypatch.setattr(gemini_service, "_questions_to_gemini", lambda *a, **k: None)


def test_hard_wrapped_document_produces_five_complete_questions():
    result = generate_mcqs(HARD_WRAPPED_DOC, 5)
    questions = result["questions"]

    assert result["engine"] == "document"
    assert len(questions) == 5

    for question in questions:
        stem = question["question"]
        options = question["options"]

        assert stem.endswith("?")
        assert "____" not in stem
        assert "___" not in stem
        assert "edita" not in stem.lower()
        assert "reprethe" not in stem.lower()
        assert question["answer"] in {"A", "B", "C", "D"}
        assert len(options) == 4
        assert len(set(options)) == 4
        assert all(option.strip() for option in options)
        assert not any(option.rstrip().endswith(("-", "—")) for option in options)


def test_quiz_spans_several_knowledge_levels():
    questions = generate_mcqs(HARD_WRAPPED_DOC, 5)["questions"]
    kinds = {question["type"] for question in questions}

    assert {"numeric", "definition", "purpose", "statement"} <= kinds
    assert "recall" not in kinds
    assert "association" not in kinds


def test_numeric_question_keeps_its_unit():
    questions = generate_mcqs(HARD_WRAPPED_DOC, 5)["questions"]
    numeric = [question for question in questions if question["type"] == "numeric"]

    assert numeric
    for question in numeric:
        answer = question["options"][ord(question["answer"]) - ord("A")]
        assert any(char.isdigit() for char in answer)


def test_true_statement_is_the_only_option_supported_by_the_source():
    questions = generate_mcqs(HARD_WRAPPED_DOC, 5)["questions"]
    statements = [
        question for question in questions if question["type"] == "statement"
    ]
    assert statements

    source = normalize_extracted_text(clean_prose(HARD_WRAPPED_DOC)).lower()
    for question in statements:
        supported = [
            option for option in question["options"]
            if option.lower() in source
        ]
        assert len(supported) == 1, question


@pytest.mark.parametrize("fragment", [
    "The proposed system can process",
    "Professionals use docu-",
    "Shift the subheading to the left as shown in Figure 1.",
    "Departing from generic language-guided image edita different approach.",
])
def test_pdf_fragments_are_rejected_before_question_generation(fragment):
    assert not _is_complete_sentence(fragment)


def test_a_real_complete_sentence_still_passes_the_quality_gate():
    assert _is_complete_sentence(
        "The DocEdit dataset contains more than 17k PDF documents."
    )
