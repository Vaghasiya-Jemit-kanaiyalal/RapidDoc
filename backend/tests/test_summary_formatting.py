"""Summary formatting regressions from a hard-wrapped PDF extraction.

The document had a repeated page header, split words/headings, bullet glyphs and
a Conclusion section stored after the Problem Statement. The old summary turned
the header into the overview, embedded raw newlines in bullets, and reused the
Problem Statement as the conclusion.
"""

import re

from RapidDoc.backend.app.services.document_summarizer import generate_complete_document_summary
from RapidDoc.backend.app.services.summary_text import normalize_extracted_text

P5_LIKE = """Subject: ITUE301 - Advanced Web Development Frameworks ID: 24DCS140
DEPSTAR (CSE) – 5CSE - 2(C)  1
Practical 5: MongoDB Integration and Schema Design with
Mongoose
Objective To connect a MongoDB database to an Express server and enforce data validation through
Mongoose schema.

Subject: ITUE301 - Advanced Web Development Frameworks ID: 24DCS140
DEPSTAR (CSE) – 5CSE - 2(C)  2
Problem
Statement
\uf0b7 Extend the Task Management backend from Practical 4 by connecting MongoDB using
Mongoose.
\uf0b7 Define a Task schema with at least 4 fields: title (String, required), description (String),
completed (Boolean, default false), createdAt (Date, default Date.now).
\uf0b7 Replace the in-memory array from Practical 4 with real Mongoose model operations.
\uf0b7 Test all CRUD operations against the live database using Postman.
\uf0b7 Ensure validation errors are returned as structured JSON, not raw Mongoose error
objects.

Subject: ITUE301 - Advanced Web Development Frameworks ID: 24DCS140
DEPSTAR (CSE) – 5CSE - 2(C)  3
Project
Structure
task-manager-backend/
Implementatio
n
Install Mongoose in the backend and define the data model.
Create routes for CRUD operations against MongoDB.

Subject: ITUE301 - Advanced Web Development Frameworks ID: 24DCS140
DEPSTAR (CSE) – 5CSE - 2(C)  4
Conclusion In this practical, the Task Management backend was successfully connected to a MongoDB database
using Mongoose. However, a Task schema was defined with required fields and default values (title, description,
completed, createdAt), and the in-memory array from Practical 4 was replaced with real MongoOse model
Operations. CRUD operations were tested against the live database using Postman and validation errors were
Returned as structured JSON responses, confirming the data persists after a server restart.
"""


def _section(summary: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", summary, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def test_normalizer_joins_wrapped_words_and_headings():
    text = (
        "Problem \n"
        "Statement\n"
        "\uf0b7 Extend the Task Management backend from Practical 4 by connecting MongoDB using\n"
        "Mongoose.\n"
        "Implementatio\n"
        "n\n"
        "Project\n"
        "Structure\n"
    )
    normalized = normalize_extracted_text(text)

    assert "Problem Statement" in normalized
    assert "using Mongoose." in normalized
    assert "Implementation" in normalized
    assert "Project Structure" in normalized
    assert "\uf0b7" not in normalized


def test_pdf_style_summary_is_clean_and_does_not_reuse_the_problem_statement():
    result = generate_complete_document_summary(P5_LIKE, doc_title="24DCS140_P5.pdf")
    summary = result["summary"]
    assert summary

    overview = _section(summary, "Overview")
    key_points = _section(summary, "Key Points")
    conclusion = _section(summary, "Conclusion")

    # Page furniture must not become the overview.
    assert "Subject:" not in summary
    assert "DEPSTAR" not in summary
    assert "Practical 5: MongoDB" not in overview
    assert "To connect a MongoDB database" in overview

    # Real requirements, not a wall of hard-wrapped header text.
    assert "Extend the Task Management backend" in key_points
    assert "Define a Task schema" in key_points
    assert "Test all CRUD operations" in key_points
    assert "However, a Task schema" not in key_points

    # The actual Conclusion section wins over the terminal Problem Statement.
    assert "successfully connected to a MongoDB database" in conclusion
    assert "CRUD operations were tested" in conclusion
    assert "Extend the Task Management backend" not in conclusion

    # Bullets must be single-line Markdown, with no PDF glyphs or split headings.
    assert "\uf0b7" not in summary
    assert "Design with\n\nMongoose" not in summary
    assert "Problem\nStatement" not in summary
    for line in summary.splitlines():
        if line.startswith("- "):
            assert line.strip() != "-"
            assert "\uf0b7" not in line
