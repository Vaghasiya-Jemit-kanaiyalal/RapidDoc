"""Shared fixtures for the RapidDoc backend tests.

Every test gets its own document built from scratch under ``tmp_path``. Nothing
is mocked at the file-format level: the point of these tests is that a real
.docx/.pdf on disk survives a real edit, so a fixture that stubs python-docx or
PyMuPDF would test nothing that matters.
"""

import io
import os
import sys

# Mirrors how the app is imported in production: the package is addressed as
# RapidDoc.backend.app..., so the parent of the RapidDoc package dir has to be on
# the path (backend/ alone is not enough).
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.abspath(os.path.join(BACKEND, "..", ".."))
for path in (ROOT, BACKEND):
    if path not in sys.path:
        sys.path.insert(0, path)

import docx  # noqa: E402
import fitz  # noqa: E402
import pytest  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Emu  # noqa: E402
from PIL import Image  # noqa: E402

from RapidDoc.backend.app.services.docx_editor import get_docx_image_parts  # noqa: E402,F401


def png_bytes(w, h, color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(w, h, color=(0, 0, 255)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def add_floating_picture(run, width_emu, height_emu):
    """Promote a picture's ``wp:inline`` to a ``wp:anchor`` (floating).

    python-docx can only insert inline pictures, so this is done by hand. It
    matters because a floating picture is invisible to ``doc.inline_shapes`` -
    the API the buggy writer used - so it is the case that catches index drift.
    """
    drawing = run._r.find(qn("w:drawing"))
    inline = drawing.find(qn("wp:inline"))

    # CT_Anchor's required child order is fixed by the schema:
    # simplePos, positionH, positionV, extent, effectExtent, wrap*, docPr,
    # cNvGraphicFramePr, graphic.
    anchor = inline.makeelement(qn("wp:anchor"), {})
    for name, val in (
        ("distT", "0"), ("distB", "0"), ("distL", "0"), ("distR", "0"),
        ("simplePos", "0"), ("relativeHeight", "251658240"), ("behindDoc", "0"),
        ("locked", "0"), ("layoutInCell", "1"), ("allowOverlap", "1"),
    ):
        anchor.set(name, val)

    anchor.append(inline.makeelement(qn("wp:simplePos"), {"x": "0", "y": "0"}))
    for tag, rel, offset in (
        ("wp:positionH", "column", "914400"),
        ("wp:positionV", "paragraph", "914400"),
    ):
        pos = inline.makeelement(qn(tag), {"relativeFrom": rel})
        off = inline.makeelement(qn("wp:posOffset"), {})
        off.text = offset
        pos.append(off)
        anchor.append(pos)

    for child in list(inline):
        anchor.append(child)
    drawing.replace(inline, anchor)


@pytest.fixture
def docx_images(tmp_path):
    """A .docx with three distinct images plus one shared twice.

    Layout, in document order:
      0  floating picture (only reachable via the canonical walk)
      1  logo, embedded once and drawn twice -> one index, occurrences=2
      2  banner, wide
    """
    logo = tmp_path / "logo.png"
    banner = tmp_path / "banner.png"
    figure = tmp_path / "figure.png"
    logo.write_bytes(png_bytes(40, 40, (255, 0, 0)))
    banner.write_bytes(png_bytes(800, 60, (0, 0, 255)))
    figure.write_bytes(png_bytes(500, 500, (0, 255, 0)))

    d = docx.Document()
    run = d.add_paragraph().add_run()
    run.add_picture(str(figure), width=Emu(4572000), height=Emu(2286000))
    add_floating_picture(run, 4572000, 2286000)

    d.add_paragraph("logo")
    d.add_picture(str(logo))
    d.add_paragraph("logo again")
    d.add_picture(str(logo))

    d.add_paragraph("banner")
    d.add_picture(str(banner), width=Emu(7315200))

    path = tmp_path / "images.docx"
    d.save(str(path))
    return str(path)


@pytest.fixture
def docx_no_images(tmp_path):
    path = tmp_path / "plain.docx"
    d = docx.Document()
    d.add_paragraph("Just text, no pictures.")
    d.save(str(path))
    return str(path)


@pytest.fixture
def pdf_images(tmp_path):
    """A 3-page PDF: 2 images on page 1, 1 on page 2, 2 on page 3.

    Page 1 and page 3 are deliberately multi-image so the resolver's
    disambiguation path is exercised against a real file.
    """
    doc = fitz.open()
    page_specs = [
        [(0, 0, 120, 90), (200, 300, 200, 100)],   # page 1: two, one wide
        [(0, 0, 150, 150)],                        # page 2: exactly one
        [(0, 0, 120, 120), (300, 300, 120, 120)],   # page 3: two
    ]
    for specs in page_specs:
        page = doc.new_page()
        for i, (x, y, w, h) in enumerate(specs):
            page.insert_image(
                fitz.Rect(x, y, x + w, y + h),
                stream=png_bytes(w, h, (i * 60 % 255, 0, 0)),
            )
    path = tmp_path / "images.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_repeated_logo(tmp_path):
    """One logo stamped on all 3 pages - the shared-xref case for PDFs.

    Replacing any slot must change all three, because a PDF stores the pixels
    once; this fixture exists so a test can assert that is reported rather than
    silently surprising the user.

    Note the contrast with resizing: each page draws the same xref through its
    own transformation matrix, so a resize legitimately touches one page at a
    time. :func:`pdf_same_page_twice` covers the shared-page case.
    """
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_image(fitz.Rect(0, 0, 80, 80), stream=png_bytes(80, 80, (9, 9, 9)))
    path = tmp_path / "logo.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_same_page_twice(tmp_path):
    """The same logo drawn twice on ONE page: two slots, one xref."""
    doc = fitz.open()
    page = doc.new_page()
    logo = png_bytes(80, 80, (9, 9, 9))
    page.insert_image(fitz.Rect(10, 10, 90, 90), stream=logo)
    page.insert_image(fitz.Rect(10, 200, 90, 280), stream=logo)
    path = tmp_path / "same_page.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_rotated_image(tmp_path):
    """A picture drawn through a rotated matrix, which resize must refuse."""
    path = tmp_path / "rotated.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(
        fitz.Rect(100, 100, 200, 200),
        stream=png_bytes(100, 100, (4, 5, 6)),
        rotate=90,
    )
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_with_headers(tmp_path):
    """A 4-page A4 PDF with a running header and footer on every page.

    Both bands are positioned the way the AWDF reference document positions
    them: the header straddles the nominal 45pt band (y 36-49) and the footer
    straddles the bottom one. A test that only used neatly aligned furniture
    would pass against the old white-rectangle writer, which is why the
    straddling offsets are part of the fixture.
    """
    path = tmp_path / "headers.pdf"
    doc = fitz.open()
    for number in range(1, 5):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 90), f"Chapter {number}", fontsize=12)
        page.insert_text((60, 120), "Body text that must survive.", fontsize=10)
        page.insert_text((60, 40), "Subject: Old Subject   ID: 0000", fontsize=9)
        page.insert_text((60, 800), f"DEPSTAR   {number}", fontsize=9)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_body_at_top(tmp_path):
    """A PDF whose body text starts at y=20, inside the header band.

    The old implementation filled the top 45pt with opaque white on every page,
    so this body text vanished. Nothing may erase it now.
    """
    path = tmp_path / "body_at_top.pdf"
    doc = fitz.open()
    for number in range(1, 3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 24), f"Very high body line {number}", fontsize=9)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdf_mixed_headers(tmp_path):
    """Three pages carrying *different* headers.

    Targeting one repeated header and rewriting it without disturbing a second,
    different one is the whole point of ``target_header_text``, and it can only be
    tested when the pages disagree.
    """
    path = tmp_path / "mixed_headers.pdf"
    doc = fitz.open()
    for header, number in (("HEADER ALPHA", 1), ("HEADER BETA", 2), ("HEADER ALPHA", 3)):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 300), f"Body {number}", fontsize=11)
        page.insert_text((60, 40), header, fontsize=9)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def docx_with_headers(tmp_path):
    """A 2-page DOCX with a header and footer that span two paragraphs."""
    path = tmp_path / "headers.docx"
    d = docx.Document()
    for number in range(1, 3):
        d.add_paragraph(f"Body paragraph {number}")
        if number < 2:
            d.add_page_break()
    for section in d.sections:
        header = section.header
        header.paragraphs[0].text = "Subject: Old Subject"
        header.add_paragraph("ID: 0000")
        footer = section.footer
        footer.paragraphs[0].text = "DEPSTAR"
        footer.add_paragraph("1")
    d.save(str(path))
    return str(path)