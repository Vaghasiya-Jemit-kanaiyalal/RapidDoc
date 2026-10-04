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

from RapidDoc.backend.app.routers.documents import validate_file, verify_upload_bytes
from RapidDoc.backend.app.services.export_service import (
    build_pptx_bytes, build_txt_bytes, build_docx_bytes,
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
