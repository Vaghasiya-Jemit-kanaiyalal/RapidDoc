"""A code-heavy document must not be summarised as code.

The reported failure was a Telco churn EDA report whose summary read like a
paraphrase of its own source listings - `df.shape`, `plt.title(...)`, a heading
welded onto the sentence beneath it, and a conclusion sentence repeated at the
end. These tests pin the behaviour that fixes it.
"""

import pytest

from RapidDoc.backend.app.services.document_text import (
    clean_prose,
    looks_like_code,
    looks_like_table_dump,
    prose_ratio,
    split_prose_sentences,
)
from RapidDoc.backend.app.services.gemini_service import (
    _topup_sentences,
    generate_mcqs,
    summarize_document,
)
from RapidDoc.backend.app.services.mcq_generator import sentences_of
from RapidDoc.backend.app.services.text_polish import split_sentences

NOTEBOOK = """1. Introduction to EDA
The Telco Customer Churn dataset contains customer activity and churn data for a
fictional telecom company. We explore it with pandas and numpy.

2. Importing Libraries
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
%matplotlib inline

3. Data Loading
df = pd.read_csv('WA_Fn-UseC_-Telco-Customer-Churn.csv')
df.shape

4. Data Cleaning
df['TotalCharges'] = pd.to_numeric(df['TotalCharges'], errors='coerce')
df.dropna(inplace=True)
print(df.isnull().sum())
   dtype   object  int64  float64  object

5. Conclusion
The analysis shows that 26.5% of customers churned. Month-to-month contracts are
the strongest churn driver, while tenure above 60 months correlates with
retention.
"""


# ---------------------------------------------------------------------------
# Code detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "import numpy as np",
    "import pandas as pd",
    "%matplotlib inline",
    "df = pd.read_csv('telco.csv')",
    "df['TotalCharges'] = pd.to_numeric(df['TotalCharges'])",
    "df.shape",
    "sns.countplot(x='Churn', data=df)",
    "function Header({name}) { return (<header><h1>{name}</h1></header>); }",
    "const total = items.reduce((a, b) => a + b.price, 0);",
    "});",
    "for (const x of items) console.log(x);",
    "#!/usr/bin/env python",
    "```python",
])
def test_code_lines_are_detected(line):
    assert looks_like_code(line) or looks_like_table_dump(line)


@pytest.mark.parametrize("line", [
    "The dataset contains 7,043 rows and 21 columns after cleaning.",
    "Contract type, internet service and payment method were the strongest predictors.",
    "Through this practical, a working data pipeline was built and validated.",
    "The analysis shows that 26.5% of customers churned overall.",
    "See Table 2 for the full list of columns and their dtypes.",
    "e.g. pandas and numpy were used throughout this analysis.",
    "Figure 1 shows the churn distribution across contract types.",
])
def test_prose_is_never_mistaken_for_code(line):
    """Dropping a real sentence is worse than keeping a line of code."""
    assert not looks_like_code(line)
    assert not looks_like_table_dump(line)


def test_clean_prose_removes_code_but_keeps_the_analysis():
    cleaned = clean_prose(NOTEBOOK)
    assert "import pandas as pd" not in cleaned
    assert "read_csv" not in cleaned
    assert "%matplotlib inline" not in cleaned
    assert "26.5% of customers churned" in cleaned
    assert "fictional telecom company" in cleaned


def test_clean_prose_returns_the_input_when_there_is_no_code():
    plain = "The quick brown fox jumps over the lazy dog near the riverbank today."
    assert clean_prose(plain) is plain


def test_clean_prose_drops_a_markdown_fenced_block():
    text = "Intro sentence explaining the approach used in this analysis.\n```\nimport os\nprint(os.getcwd())\n```\nConcluding sentence about what the analysis found."
    cleaned = clean_prose(text)
    assert "import os" not in cleaned
    assert "print(os.getcwd())" not in cleaned
    assert "Concluding sentence" in cleaned


def test_prose_ratio_distinguishes_the_two_kinds_of_document():
    assert prose_ratio(NOTEBOOK) < 0.6
    assert prose_ratio(
        "The report analyses churn. It compares contract types across tenants. "
        "The findings are summarised in the conclusion section."
    ) > 0.8


def test_a_heading_line_is_not_treated_as_a_sentence():
    """Headings sit on their own line; they must not join the sentence below."""
    text = (
        "Conclusion\n"
        "The analysis shows that churn is concentrated in the entry plans. "
        "Month-to-month contracts churn at nearly three times the base rate."
    )
    sentences = split_prose_sentences(text, split_sentences)
    assert not any(s.startswith("Conclusion") for s in sentences)
    assert any("concentrated in the entry plans" in s for s in sentences)


def test_a_short_label_line_is_not_quoted_as_a_sentence():
    assert split_prose_sentences("Objective", split_sentences) == []


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def test_summary_of_a_notebook_contains_no_code():
    summary = summarize_document(NOTEBOOK)["summary"] or ""
    assert "read_csv" not in summary
    assert "import pandas" not in summary
    assert "df.shape" not in summary
    assert "print(" not in summary


def test_summary_of_a_notebook_reports_the_actual_findings():
    summary = summarize_document(NOTEBOOK)["summary"] or ""
    assert "26.5%" in summary
    assert "churn" in summary.lower()


def test_summary_does_not_repeat_the_conclusion_in_the_topup():
    """The regression: the conclusion came back twice, once welded to a heading."""
    summary = summarize_document(NOTEBOOK)["summary"] or ""
    assert summary.lower().count("26.5% of customers churned") == 1


def test_summary_does_not_weld_a_heading_into_a_sentence():
    summary = summarize_document(NOTEBOOK)["summary"] or ""
    assert "Introduction to EDA The" not in summary
    assert "Conclusion The analysis" not in summary


def test_topup_excludes_conclusion_sentences():
    conclusion = ["The analysis shows that 26.5% of customers churned."]
    topup = _topup_sentences(NOTEBOOK, conclusion)
    assert conclusion[0] not in topup
    assert not any("read_csv" in s for s in topup)


def test_prose_only_document_is_unaffected():
    prose = (
        "Practical 3: Data Visualisation\n"
        "The objective of this practical is to visualise a sales dataset. "
        "Three charts are produced from the cleaned data. "
        "The conclusion states that revenue peaks in the fourth quarter each year.\n"
    )
    result = summarize_document(prose)
    assert result["summary"]
    assert "read_csv" not in result["summary"]


# ---------------------------------------------------------------------------
# MCQs
# ---------------------------------------------------------------------------

def test_sentences_are_rejoined_across_a_table_cell_boundary():
    """A blank must not land where the sentence has not finished."""
    text = (
        "Objective To set up a React development environment using Vite and build "
        "a static UI using \nindependently structured, reusable components. \n"
    )
    sentences = sentences_of(text)
    assert any("independently structured, reusable components" in s for s in sentences)


def test_a_row_label_is_not_part_of_the_question():
    sentences = sentences_of(
        "Objective To set up a React development environment using Vite today."
    )
    assert all(not s.lower().startswith("objective ") for s in sentences)


def test_association_cue_is_not_an_instruction_verb():
    text = (
        "Create a React application using Vite for a student portfolio page. "
        "The application must include at least four reusable components. "
        "React components receive data through props from the parent component. "
        "The portfolio page is deployed on a static hosting provider."
    )
    questions = generate_mcqs(text, 6)["questions"]
    for question in questions:
        if question.get("type") == "association":
            assert '"Create"' not in question["question"]


def test_no_question_stem_is_a_line_of_code():
    questions = generate_mcqs(NOTEBOOK, 6)["questions"]
    for question in questions:
        assert "read_csv" not in question["question"]
        assert "import " not in question["question"]
        assert not question["question"].strip().endswith(("using", "the", "and", "with"))