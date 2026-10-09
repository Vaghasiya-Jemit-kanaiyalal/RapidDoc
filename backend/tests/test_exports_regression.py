"""Regression cover for the paths this feature work sits next to.

None of this is new functionality, and that is the point: image editing,
resizing and versioning all funnel through the same upload, export and PPT code
that already existed, so a change there would show up as "the editor broke" with
nothing pointing at the cause. These pin the behaviour the rest of the app
depends on, using the real libraries that read the produced files.
"""

import io
import zipfile

import docx
import fitz
import pytest
from docx.oxml.ns import qn

from RapidDoc.backend.app.routers.documents import validate_file, verify_upload_bytes
from RapidDoc.backend.app.services.docx_editor import (
    get_docx_content, update_docx_content,
)
from RapidDoc.backend.app.services.export_service import (
    build_pptx_bytes, build_txt_bytes, build_docx_bytes,
)
from RapidDoc.backend.app.services.pdf_editor import (
    _whiteout_and_write_text, update_pdf_content,
)


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["a.docx", "b.PDF", "c.Docx"])
def test_valid_extensions_are_accepted(name):
    assert validate_file(name) in (".docx", ".pdf")


@pytest.mark.parametrize("name", ["a.txt", "a.exe", "a.doc", "noextension", "a.pdf.exe"])
def test_other_extensions_are_rejected(name):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        validate_file(name)
    assert caught.value.status_code == 400


def test_an_empty_upload_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        verify_upload_bytes(b"", ".docx")
    assert caught.value.status_code == 400
    assert "empty" in caught.value.detail.lower()


def test_a_text_file_renamed_to_docx_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        verify_upload_bytes(b"just some text, definitely not a Word file", ".docx")
    assert caught.value.status_code == 400


def test_a_pdf_renamed_from_text_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        verify_upload_bytes(b"%PDF-1.4 but not really", ".pdf")
    assert caught.value.status_code == 400


def test_a_plain_zip_is_not_mistaken_for_a_docx():
    from fastapi import HTTPException

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(HTTPException) as caught:
        verify_upload_bytes(buf.getvalue(), ".docx")
    assert caught.value.status_code == 400
    assert "not a Word" in caught.value.detail


def test_a_real_document_passes_validation(docx_images, pdf_images):
    for path in (docx_images, pdf_images):
        with open(path, "rb") as fh:
            verify_upload_bytes(fh.read(), validate_file(path))


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

@pytest.fixture
def pdf_with_text(tmp_path):
    """The image fixtures carry no text, which makes them useless for exports."""
    path = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(60, 80), "STRUCTURAL SURVEY", fontsize=18)
    page.insert_text(fitz.Point(60, 120), "Span lengths and pile foundations.", fontsize=11)
    doc.save(str(path))
    doc.close()
    return str(path)

def test_txt_export_contains_the_document_text(pdf_with_text):
    text = build_txt_bytes(pdf_with_text, "pdf").decode("utf-8")
    assert "STRUCTURAL SURVEY" in text


def test_docx_export_round_trips_a_pdf(pdf_with_text):
    data = build_docx_bytes(pdf_with_text, "pdf")
    document = docx.Document(io.BytesIO(data))
    body = "\n".join(p.text for p in document.paragraphs)
    assert "STRUCTURAL SURVEY" in body


def test_pptx_export_produces_slides_from_a_pdf(pdf_with_text):
    data = build_pptx_bytes(pdf_with_text, "pdf", theme="modern")
    assert data[:2] == b"PK"

    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    assert len(presentation.slides) >= 1


def test_pptx_export_survives_editing_the_source_pdf(pdf_with_text, tmp_path):
    """Exports run against the live file, so they must not depend on it staying put."""
    edited = tmp_path / "edited.pdf"
    with open(pdf_with_text, "rb") as fh:
        with fitz.open(stream=fh.read(), filetype="pdf") as doc:
            page = doc[0]
            page.insert_text(fitz.Point(40, 60), "ADDED BY AN EDIT", fontsize=20)
            doc.save(str(edited))

    data = build_pptx_bytes(str(edited), "pdf", theme="corporate")
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    assert len(presentation.slides) >= 1


@pytest.mark.parametrize("theme", ["modern", "corporate", "minimal"])
def test_every_advertised_pptx_theme_builds(pdf_with_text, theme):
    data = build_pptx_bytes(pdf_with_text, "pdf", theme=theme)
    assert data[:2] == b"PK"


def _positioned_shapes(presentation):
    """``[(slide_no, shape, (x0, y0, x1, y1))]`` for everything with a box."""
    for slide_no, slide in enumerate(presentation.slides, 1):
        for shape in slide.shapes:
            try:
                left, top, width, height = shape.left, shape.top, shape.width, shape.height
            except Exception:
                continue
            if None in (left, top, width, height):
                continue
            yield slide_no, shape, (left, top, left + width, top + height)


@pytest.mark.parametrize("theme", ["modern", "corporate", "minimal"])
def test_no_pptx_shape_falls_off_the_slide(pdf_with_text, theme):
    """The reported failure: a wide screenshot landed 24in wide on a 13in slide.

    A picture placed by height alone keeps its native aspect ratio, so anything
    wider than it is tall runs off the edge and is lost when presenting or
    printing. Nothing may sit outside the slide - not by more than a rounding
    error.
    """
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(build_pptx_bytes(pdf_with_text, "pdf", theme=theme)))
    sw, sh = presentation.slide_width, presentation.slide_height
    tolerance = 9525  # 1/96 inch

    offenders = [
        (slide_no, shape.shape_id, shape.shape_type, rect)
        for slide_no, shape, rect in _positioned_shapes(presentation)
        if rect[0] < -tolerance or rect[1] < -tolerance
        or rect[2] > sw + tolerance or rect[3] > sh + tolerance
    ]
    assert not offenders, f"shapes outside the {sw}x{sh} slide: {offenders}"


@pytest.mark.parametrize("theme", ["modern", "corporate", "minimal"])
def test_pptx_pictures_are_smaller_than_their_slots(pdf_images, theme):
    """A picture is always scaled to fit its box, never to its native size."""
    from pptx import Presentation

    presentation = Presentation(
        io.BytesIO(build_pptx_bytes(pdf_images, "pdf", theme=theme))
    )
    sw, sh = presentation.slide_width, presentation.slide_height
    pictures = [
        rect
        for _n, shape, rect in _positioned_shapes(presentation)
        if shape.shape_type == 13
    ]
    assert pictures, "a document with images should export at least one picture"
    for rect in pictures:
        assert (rect[2] - rect[0]) <= sw, "picture wider than the slide"
        assert (rect[3] - rect[1]) <= sh, "picture taller than the slide"


def test_pptx_body_text_is_editable_text_not_one_picture(pdf_with_text):
    """Editing the deck is the whole point; text must be real text runs."""
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(build_pptx_bytes(pdf_with_text, "pdf", theme="modern")))
    runs = 0
    for _n, shape, _rect in _positioned_shapes(presentation):
        if not shape.has_text_frame:
            continue
        for paragraph in shape.text_frame.paragraphs:
            runs += sum(1 for run in paragraph.runs if run.text.strip())
    assert runs >= 5, "exported slides must contain selectable, editable text"


# ---------------------------------------------------------------------------
# Content edits written back into the document
# ---------------------------------------------------------------------------

def _docx_with_heading_body_and_table(tmp_path):
    """Heading, body paragraph and a cell that the edit pipeline must keep in place."""
    path = tmp_path / "structured.docx"
    document = docx.Document()
    heading = document.add_paragraph("Conclusion")
    heading.style = document.styles["Heading 2"]
    for run in heading.runs:
        run.bold = True
    document.add_paragraph("The findings of this phase are solid.")
    table = document.add_table(rows=2, cols=2)
    table.cell(1, 1).text = "Owner A"
    document.save(str(path))
    return str(path)


def test_multiline_paragraph_edit_becomes_real_paragraphs(tmp_path):
    """The rewriter brain/multi-line textarea emit \\n-separated text.

    Writing that literal string into one run made Word/LibreOffice render it as
    stray whitespace, so edited text no longer stayed in its own paragraph
    (e.g. a "Conclusion" heading that stopped being a heading). Each line must
    become a real paragraph sharing the target's style, so the document keeps
    its structure, and a table cell edit must stay inside its cell.
    """
    src = _docx_with_heading_body_and_table(tmp_path)
    out = tmp_path / "edited.docx"

    ok = update_docx_content(src, str(out), [
        {"index": 1, "text": "The findings of this phase are solid.\nThey were verified twice.\nNo anomalies remain."},
        {"table_index": 0, "row": 1, "col": 1, "text": "Owner A\nOwner B"},
    ])
    assert ok

    document = docx.Document(str(out))
    texts = [p.text for p in document.paragraphs]
    assert texts == [
        "Conclusion",
        "The findings of this phase are solid.",
        "They were verified twice.",
        "No anomalies remain.",
    ]
    assert document.paragraphs[0].style.name == "Heading 2"
    assert document.paragraphs[0].runs[0].bold is True
    cell = document.tables[0].rows[1].cells[1]
    assert [p.text for p in cell.paragraphs] == ["Owner A", "Owner B"]


def test_single_line_paragraph_edit_stays_one_paragraph(tmp_path):
    src = _docx_with_heading_body_and_table(tmp_path)
    out = tmp_path / "edited.docx"

    ok = update_docx_content(src, str(out), [
        {"index": 1, "text": "The findings were verified twice."},
    ])
    assert ok

    document = docx.Document(str(out))
    assert [p.text for p in document.paragraphs] == [
        "Conclusion",
        "The findings were verified twice.",
    ]
    assert document.paragraphs[0].style.name == "Heading 2"


# ---------------------------------------------------------------------------
# Manual line breaks (<w:br/>) in paragraphs
# ---------------------------------------------------------------------------

def _docx_with_manual_line_break(tmp_path):
    """A paragraph whose run carries a real <w:br/> soft line break."""
    path = tmp_path / "linebreak.docx"
    document = docx.Document()
    document.add_paragraph("Results")
    paragraph = document.add_paragraph()
    run = paragraph.add_run("First line")
    run.add_break()
    run.add_text("Second line")
    document.add_paragraph("Tail.")
    document.save(str(path))
    return str(path)


def test_paragraph_with_manual_line_break_reads_a_newline(tmp_path):
    """python-docx's ``.text`` drops <w:br/>, gluing "First line" and "Second
    line" together in the editor; the reader must surface the break so the
    user sees the real line structure before editing."""
    src = _docx_with_manual_line_break(tmp_path)
    items = get_docx_content(src)
    assert items[1]["text"] == "First line\nSecond line"


def test_editing_a_line_break_paragraph_becomes_real_paragraphs(tmp_path):
    """Editing that paragraph into more lines expands the soft breaks into real
    paragraphs (same rule as any multi-line edit) and leaves no phantom <w:br/>
    behind in the rewritten ones."""
    src = _docx_with_manual_line_break(tmp_path)
    out = tmp_path / "edited.docx"

    ok = update_docx_content(src, str(out), [
        {"index": 1, "text": "First line\nSecond line updated\nThird line"},
    ])
    assert ok

    document = docx.Document(str(out))
    assert [p.text for p in document.paragraphs] == [
        "Results",
        "First line",
        "Second line updated",
        "Third line",
        "Tail.",
    ]
    left_over = [br for p in document.paragraphs for br in p._p.iter(qn("w:br"))]
    assert not left_over


def test_untouched_line_break_paragraph_keeps_its_break(tmp_path):
    """An edit to a different paragraph must not disturb an existing <w:br/>."""
    src = _docx_with_manual_line_break(tmp_path)
    out = tmp_path / "edited.docx"

    ok = update_docx_content(src, str(out), [
        {"index": 2, "text": "Tail status changed"},
    ])
    assert ok

    document = docx.Document(str(out))
    assert [p.text for p in document.paragraphs] == [
        "Results",
        "First line\nSecond line",
        "Tail status changed",
    ]
    breaks = [br for p in document.paragraphs for br in p._p.iter(qn("w:br"))]
    assert len(breaks) == 1


# ---------------------------------------------------------------------------
# PDF block edits: wrap + flow, and bbox fallback
# ---------------------------------------------------------------------------

def _pdf_with_text(tmp_path, text="Old text here", size=12.0):
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=500)
    page.insert_text((50, 100), text, fontsize=size, fontname="helv")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_pdf_whiteout_wraps_and_keeps_the_font_size(tmp_path):
    """Replacing a block must write the full new text at the *original* font
    size, wrapped to the box width and flowing downward - the old behaviour
    shrank the font until it fit, which mangled a normal-length replacement."""
    src = _pdf_with_text(tmp_path)
    doc = fitz.open(src)
    page = doc[0]
    blocks = page.get_text("dict")["blocks"]
    rect = fitz.Rect(blocks[0]["bbox"])

    _whiteout_and_write_text(
        page, rect,
        "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota",
        {"font": "helv", "size": 12.0, "color": (0.0, 0.0, 0.0)},
    )

    text = " ".join(page.get_text().split())
    assert "Old text here" not in text
    assert text == "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota"

    spans = [
        sp
        for b in page.get_text("dict")["blocks"]
        for line in b.get("lines", [])
        for sp in line.get("spans", [])
    ]
    assert any(abs(sp["size"] - 12.0) < 0.05 for sp in spans)


def test_pdf_edit_without_bbox_targets_the_right_block(tmp_path):
    """A block edit that carries no bbox (legacy shape) must still land on the
    right text - the writer re-derives the rect from block_no instead of
    silently dropping the user's edit."""
    src = _pdf_with_text(tmp_path)
    out = tmp_path / "edited.pdf"

    ok = update_pdf_content(src, str(out), [
        {"page_num": 0, "blocks": [
            {"block_no": 0, "text": "Replacement sentence goes here."},
        ]},
    ])
    assert ok

    with fitz.open(str(out)) as pdf:
        text = pdf[0].get_text()
    assert "Old text here" not in text
    assert "Replacement sentence goes here." in " ".join(text.split())
