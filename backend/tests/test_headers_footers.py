"""Header and footer behaviour that a word processor is expected to have.

The regressions here are the ones users actually reported:

* a white rectangle painted over the top of the page, eating body content;
* the same page number stamped on every page;
* no way to give left (even) and right (odd) pages different furniture.

The fixtures deliberately put the old header and footer slightly off the 45pt
band, because a test written against neatly aligned furniture would still pass
with the old white-out-everything implementation.
"""

import docx
import fitz
import pytest
from docx.oxml.ns import qn

from RapidDoc.backend.app.services import header_footer as hf
from RapidDoc.backend.app.services.docx_editor import (
    apply_docx_styling,
    get_docx_headers_footers,
)
from RapidDoc.backend.app.services.pdf_editor import (
    apply_pdf_styling,
    get_pdf_headers_footers,
)


def band_text(page, which):
    """All text a header/footer band should be judged on."""
    rect = hf.band_rect(page, which)
    if which == "footer":
        rect = fitz.Rect(0, rect.y0 - 20, page.rect.width, page.rect.height)
    else:
        rect = fitz.Rect(0, 0, page.rect.width, rect.y1 + 20)
    return " ".join(page.get_text("text", clip=rect).split())


def full_text(page):
    return " ".join(page.get_text("text").split())


def _pages(path):
    """Every page of a written PDF, still open for the caller to inspect."""
    doc = fitz.open(path)
    return [doc[index] for index in range(len(doc))]


def _full_bands(path):
    """Header and footer text of every page, for an equality comparison."""
    doc = fitz.open(path)
    try:
        return [
            (band_text(page, "header"), band_text(page, "footer"))
            for page in doc
        ]
    finally:
        doc.close()


def apply_pdf(path, **kwargs):
    assert apply_pdf_styling(path, path, **kwargs) is True


def apply_docx(path, **kwargs):
    assert apply_docx_styling(path, path, **kwargs) is True


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def test_page_field_renders_per_page_value():
    assert hf.render("Page {PAGE} of {NUMPAGES}", 3, 12) == "Page 3 of 12"
    assert hf.render("p <<PAGE>>", 7, 9) == "p 7"


def test_field_parsing_keeps_literal_text_around_macros():
    segments = hf.parse_segments("Page {PAGE} of {NUMPAGES}")
    assert segments == [
        ("text", "Page "), ("field", "PAGE"),
        ("text", " of "), ("field", "NUMPAGES"),
    ]


def test_unknown_macro_is_left_alone():
    """An unrecognised token must survive verbatim rather than be swallowed."""
    assert hf.render("{ AUTHOR } stays", 1, 1) == "{ AUTHOR } stays"


def test_pdf_page_number_counts_up_instead_of_repeating(pdf_with_headers):
    apply_pdf(pdf_with_headers, footer_text="Page {PAGE} of {NUMPAGES}")

    doc = fitz.open(pdf_with_headers)
    try:
        numbers = [band_text(page, "footer") for page in doc]
    finally:
        doc.close()

    assert numbers == [f"Page {n} of 4" for n in range(1, 5)]


def test_pdf_page_number_is_not_literal_old_text(pdf_with_headers):
    """The replaced footer must not leave the previous page number behind."""
    apply_pdf(pdf_with_headers, footer_text="Page {PAGE}")

    doc = fitz.open(pdf_with_headers)
    try:
        page2 = band_text(doc[1], "footer")
    finally:
        doc.close()

    assert page2 == "Page 2"


# ---------------------------------------------------------------------------
# No opaque white box
# ---------------------------------------------------------------------------

def test_pdf_header_does_not_paint_a_white_box(pdf_body_at_top):
    """Body text starting at y=20 must survive a header edit.

    The previous implementation filled the whole 45pt band with opaque white,
    which deleted this text.
    """
    apply_pdf(pdf_body_at_top, header_text="NEW HEADER")

    doc = fitz.open(pdf_body_at_top)
    try:
        for index, page in enumerate(doc):
            assert f"Very high body line {index + 1}" in full_text(page)
            white = [
                d for d in page.get_drawings()
                if d.get("fill") == (1.0, 1.0, 1.0)
                and d["rect"].width > page.rect.width * 0.8
                and d["rect"].height > 20
            ]
            assert white == [], "an opaque white rectangle was drawn across the page"
    finally:
        doc.close()


def test_pdf_header_replacement_keeps_page_body_and_images(pdf_with_headers):
    before = [full_text(p) for p in fitz.open(pdf_with_headers)]
    apply_pdf(pdf_with_headers, header_text="Subject: New", footer_text="Page {PAGE}")

    doc = fitz.open(pdf_with_headers)
    try:
        after = [full_text(p) for p in doc]
        assert len(doc) == len(before)
        for index, (old, new) in enumerate(zip(before, after)):
            assert f"Chapter {index + 1}" in new
            assert "Body text that must survive." in new
            assert "Old Subject" not in new
            assert "DEPSTAR" not in new
    finally:
        doc.close()


def test_pdf_replacement_lands_on_the_old_baseline(pdf_with_headers):
    """Editing a header must not move it to a different line.

    The old header sat at y 36-49; the new one belongs there, not at the very
    top of the band.
    """
    apply_pdf(pdf_with_headers, header_text="Subject: New")

    doc = fitz.open(pdf_with_headers)
    try:
        spans = hf.zone_spans(doc[0], hf.band_rect(doc[0], "header"))
        assert spans, "the new header was not written into the band"
        assert 25 < spans[0]["bbox"][1] < 45
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Odd / even and first page
# ---------------------------------------------------------------------------

def test_pdf_odd_and_even_pages_get_different_text(pdf_with_headers):
    apply_pdf(
        pdf_with_headers,
        header_text_odd="RIGHT SIDE",
        header_text_even="LEFT SIDE",
    )

    doc = fitz.open(pdf_with_headers)
    try:
        texts = [band_text(page, "header") for page in doc]
    finally:
        doc.close()

    assert texts == ["RIGHT SIDE", "LEFT SIDE", "RIGHT SIDE", "LEFT SIDE"]


def test_pdf_odd_even_pair_covers_every_page(tmp_path):
    """Only an even-side value given: odd pages must not be left blank."""
    path = tmp_path / "even_only.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page(width=595, height=842)
    doc.save(str(path))
    doc.close()

    apply_pdf(path, header_text_even="EVEN ONLY")
    doc = fitz.open(path)
    try:
        texts = [band_text(page, "header") for page in doc]
    finally:
        doc.close()

    assert texts == ["EVEN ONLY", "EVEN ONLY", "EVEN ONLY"]


def test_pdf_first_page_can_differ(pdf_with_headers):
    apply_pdf(
        pdf_with_headers,
        header_text_first="COVER",
        header_text_odd="BODY HEADER",
    )

    doc = fitz.open(pdf_with_headers)
    try:
        texts = [band_text(page, "header") for page in doc]
    finally:
        doc.close()

    assert texts[0] == "COVER"
    assert texts[1:] == ["BODY HEADER"] * 3


def test_pdf_read_only_first_page_leaves_the_rest_alone(pdf_with_headers):
    apply_pdf(pdf_with_headers, header_text_first="COVER")

    doc = fitz.open(pdf_with_headers)
    try:
        texts = [band_text(page, "header") for page in doc]
    finally:
        doc.close()

    assert texts[0] == "COVER"
    assert "Old Subject" in texts[1], "pages 2+ should be untouched"


# ---------------------------------------------------------------------------
# Targeting one header without touching the others
# ---------------------------------------------------------------------------

def test_pdf_target_text_limits_the_change_to_matching_pages(pdf_mixed_headers):
    apply_pdf(
        pdf_mixed_headers,
        header_text="BETA REPLACED",
        target_header_text="HEADER BETA",
    )

    doc = fitz.open(pdf_mixed_headers)
    try:
        texts = [band_text(page, "header") for page in doc]
    finally:
        doc.close()

    assert texts == ["HEADER ALPHA", "BETA REPLACED", "HEADER ALPHA"]


def test_pdf_unmatched_target_changes_nothing(pdf_with_headers):
    before = [full_text(p) for p in fitz.open(pdf_with_headers)]
    apply_pdf(pdf_with_headers, header_text="X", target_header_text="not present")

    after = [full_text(p) for p in fitz.open(pdf_with_headers)]
    assert before == after


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

def test_pdf_reader_reports_odd_even_variants(pdf_with_headers):
    apply_pdf(
        pdf_with_headers,
        header_text_odd="RIGHT SIDE",
        header_text_even="LEFT SIDE",
    )
    info = get_pdf_headers_footers(pdf_with_headers)

    assert info["header_odd"] == "RIGHT SIDE"
    assert info["header_even"] == "LEFT SIDE"
    assert info["different_odd_even"] is True
    assert set(info["headers"]) == {"RIGHT SIDE", "LEFT SIDE"}


def test_pdf_reader_keeps_headers_and_footers_keys(pdf_with_headers):
    """The editor still expects the flat lists."""
    info = get_pdf_headers_footers(pdf_with_headers)
    assert info["headers"] == ["Subject: Old Subject   ID: 0000"]
    assert info["footers"] == ["DEPSTAR   1", "DEPSTAR   2", "DEPSTAR   3", "DEPSTAR   4"]


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def test_docx_odd_even_parts_are_written(docx_with_headers):
    apply_docx(
        docx_with_headers,
        header_text_odd="RIGHT SIDE",
        header_text_even="LEFT SIDE",
    )

    d = docx.Document(docx_with_headers)
    section = d.sections[0]
    assert section.header.paragraphs[0].text == "RIGHT SIDE"
    assert section.even_page_header.paragraphs[0].text == "LEFT SIDE"
    assert d.settings.element.find(qn("w:evenAndOddHeaders")) is not None


def test_docx_page_number_is_a_real_field_not_literal_text(docx_with_headers):
    apply_docx(docx_with_headers, footer_text="Page {PAGE} of {NUMPAGES}")

    d = docx.Document(docx_with_headers)
    footer = d.sections[0].footer
    instr = [e.text.strip() for e in footer._element.iter(qn("w:instrText"))]
    assert instr == ["PAGE", "NUMPAGES"]

    # A cached result is present so a preview is not blank before Word refreshes.
    assert "Page" in footer.paragraphs[0].text
    assert footer.paragraphs[0].text.endswith("of 1")


def test_docx_old_header_paragraphs_are_removed(docx_with_headers):
    """Leaving blank paragraphs behind pushes the whole body down a line."""
    apply_docx(docx_with_headers, header_text="SINGLE LINE", footer_text="Page {PAGE}")

    d = docx.Document(docx_with_headers)
    assert len(d.sections[0].header.paragraphs) == 1
    assert len(d.sections[0].footer.paragraphs) == 1
    assert d.sections[0].header.paragraphs[0].text == "SINGLE LINE"


def test_docx_first_page_variant_sets_the_section_flag(docx_with_headers):
    apply_docx(docx_with_headers, header_text_first="COVER", header_text_odd="BODY")

    d = docx.Document(docx_with_headers)
    section = d.sections[0]
    assert section.different_first_page_header_footer is True
    assert section.first_page_header.paragraphs[0].text == "COVER"
    assert section.header.paragraphs[0].text == "BODY"


def test_docx_target_filter_leaves_a_mismatch_alone(docx_with_headers):
    before = [p.text for p in docx.Document(docx_with_headers).sections[0].header.paragraphs]
    apply_docx(docx_with_headers, header_text="NEW", target_header_text="no such header")

    after = [p.text for p in docx.Document(docx_with_headers).sections[0].header.paragraphs]
    assert after == before


def test_docx_target_filter_applies_on_a_match(docx_with_headers):
    apply_docx(
        docx_with_headers,
        header_text="NEW",
        target_header_text="Subject: Old Subject\nID: 0000",
    )
    header = docx.Document(docx_with_headers).sections[0].header
    assert header.paragraphs[0].text == "NEW"


def test_docx_body_is_untouched(docx_with_headers):
    before = [p.text for p in docx.Document(docx_with_headers).paragraphs]
    apply_docx(docx_with_headers, header_text="H", footer_text="Page {PAGE}")

    assert [p.text for p in docx.Document(docx_with_headers).paragraphs] == before
    assert not list(docx.Document(docx_with_headers).element.body.iter(qn("w:instrText")))


def test_docx_reader_reports_variants(docx_with_headers):
    apply_docx(
        docx_with_headers,
        header_text_odd="RIGHT SIDE",
        header_text_even="LEFT SIDE",
    )
    info = get_docx_headers_footers(docx_with_headers)

    assert info["header_odd"] == "RIGHT SIDE"
    assert info["header_even"] == "LEFT SIDE"
    assert info["different_odd_even"] is True


@pytest.mark.parametrize("macro", ["PAGE", "NUMPAGES", "DATE", "TIME"])
def test_docx_every_supported_field_emits_a_field(macro, docx_with_headers):
    apply_docx(docx_with_headers, footer_text=f"{{{macro}}}")

    d = docx.Document(docx_with_headers)
    instr = [e.text.strip() for e in d.sections[0].footer._element.iter(qn("w:instrText"))]
    assert instr == [macro]


def test_docx_unsupported_token_stays_literal(docx_with_headers):
    """``[PAGE]`` is not a macro; writing it verbatim is correct."""
    apply_docx(docx_with_headers, footer_text="[PAGE]")

    footer = docx.Document(docx_with_headers).sections[0].footer
    assert footer.paragraphs[0].text == "[PAGE]"
    assert not list(footer._element.iter(qn("w:instrText")))

# ---------------------------------------------------------------------------
# TITLE / FILENAME resolution
# ---------------------------------------------------------------------------

def test_pdf_title_field_resolves_to_the_documents_own_title(pdf_with_headers):
    """A user clicking "Document Title" in the editor got a blank footer."""
    apply_pdf(pdf_with_headers, footer_text="{TITLE}", doc_title="Churn Analysis Report")

    pages = _pages(pdf_with_headers)
    assert band_text(pages[0], "footer") == "Churn Analysis Report"


def test_pdf_filename_field_resolves_to_the_upload_name(pdf_with_headers):
    apply_pdf(
        pdf_with_headers,
        header_text="{FILENAME}",
        doc_filename="Practical2_AWDF_24DCS140.pdf",
    )

    pages = _pages(pdf_with_headers)
    assert band_text(pages[0], "header") == "Practical2_AWDF_24DCS140.pdf"


def test_pdf_title_and_filename_render_together_with_page_numbers(pdf_with_headers):
    apply_pdf(
        pdf_with_headers,
        footer_text="{TITLE} - Page {PAGE}/{NUMPAGES} - {FILENAME}",
        doc_title="Churn Analysis",
doc_filename="report.pdf",
    )

    pages = _pages(pdf_with_headers)
    assert band_text(pages[0], "footer") == "Churn Analysis - Page 1/4 - report.pdf"
    assert band_text(pages[1], "footer") == "Churn Analysis - Page 2/4 - report.pdf"


def test_pdf_filename_falls_back_to_the_stored_file_name(pdf_with_headers):
    """With no explicit name, the working file's own name is better than nothing."""
    apply_pdf(pdf_with_headers, header_text="{FILENAME}")

    pages = _pages(pdf_with_headers)
    rendered = band_text(pages[0], "header")
    assert rendered.endswith(".pdf")
    assert "None" not in rendered


def test_docx_title_field_carries_a_cached_value(docx_with_headers):
    """Word recomputes TITLE on open; the cache is for viewers that do not."""
    apply_docx(docx_with_headers, footer_text="{TITLE}", doc_title="Churn Analysis")

    footer = docx.Document(docx_with_headers).sections[0].footer
    cached = [e.text.strip() for e in footer._element.iter(qn("w:instrText"))]
    assert cached == ["TITLE"]
    assert "Churn Analysis" in footer.paragraphs[0].text


# ---------------------------------------------------------------------------
# Turning side-specific furniture back off
# ---------------------------------------------------------------------------

def test_docx_switching_to_all_pages_clears_the_stale_even_header(docx_with_headers):
    """The reported failure: an odd/even header survived as an invisible leftover.

    Word keeps using the even part whenever ``evenAndOddHeaders`` is set, so
    replacing the header with one line for every page had to clear that part too.
    """
    apply_docx(docx_with_headers, header_text_odd="ODD SIDE", header_text_even="EVEN SIDE")
    assert get_docx_headers_footers(docx_with_headers)["different_odd_even"] is True

    apply_docx(docx_with_headers, header_text="SINGLE LINE FOR EVERY PAGE")
    report = get_docx_headers_footers(docx_with_headers)

    assert report["different_odd_even"] is False
    assert report["headers"] == ["SINGLE LINE FOR EVERY PAGE"]


def test_docx_switching_to_all_pages_clears_the_stale_first_page_header(docx_with_headers):
    apply_docx(
        docx_with_headers,
        header_text="BODY HEADER",
        header_text_first="A DIFFERENT FIRST PAGE",
    )
    assert get_docx_headers_footers(docx_with_headers)["different_first"] is True

    apply_docx(docx_with_headers, header_text="BODY HEADER ONLY")
    report = get_docx_headers_footers(docx_with_headers)

    assert report["different_first"] is False
    assert report["header_first"] is None
    assert report["headers"] == ["BODY HEADER ONLY"]


def test_docx_switching_to_all_pages_leaves_no_text_in_any_other_part(docx_with_headers):
    import zipfile

    apply_docx(docx_with_headers, footer_text_odd="ODD FOOT", footer_text_even="EVEN FOOT")
    apply_docx(docx_with_headers, footer_text="ONE FOOTER")

    with zipfile.ZipFile(docx_with_headers) as archive:
        parts = [
            archive.read(name).decode("utf8", "replace")
            for name in archive.namelist()
            if name.startswith("word/footer")
        ]
    joined = " ".join(parts)
    assert "ODD FOOT" not in joined
    assert "EVEN FOOT" not in joined
    assert "ONE FOOTER" in joined


def test_docx_clearing_a_part_does_not_delete_the_field_code(docx_with_headers):
    """A blanked footer must not keep a live PAGE field that re-renders on open."""
    import zipfile

    apply_docx(docx_with_headers, footer_text="Page {PAGE} of {NUMPAGES}")
    apply_docx(docx_with_headers, footer_text="A PLAIN FOOTER")

    with zipfile.ZipFile(docx_with_headers) as archive:
        footers = [
            archive.read(name).decode("utf8", "replace")
            for name in archive.namelist()
            if name.startswith("word/footer")
        ]
    blanked = [part for part in footers if "A PLAIN FOOTER" not in part]
    for part in blanked:
        assert "PAGE" not in part
        assert "NUMPAGES" not in part


# ---------------------------------------------------------------------------
# An emptied field must never delete the furniture
# ---------------------------------------------------------------------------

def test_blank_variants_do_not_erase_the_header(pdf_with_headers):
    """The reported failure: clearing the side boxes wiped the header off every page.

    ``spec_from_legacy`` used to pass an empty string straight through, so the
    writer erased the band and then declined to write anything, because there was
    no text left to render.
    """
    spec = hf.spec_from_legacy(header_text="", header_odd="", header_even="")
    doc = fitz.open(pdf_with_headers)
    try:
        hf.apply_pdf_headers_footers(doc, spec)
        assert band_text(doc[0], "header") == "Subject: Old Subject ID: 0000"
    finally:
        doc.close()


def test_an_empty_request_leaves_the_document_untouched(pdf_with_headers):
    before = _full_bands(pdf_with_headers)

    apply_pdf(pdf_with_headers, header_text="", footer_text="")

    assert _full_bands(pdf_with_headers) == before


def test_whitespace_only_text_is_treated_as_absent(pdf_with_headers):
    spec = hf.spec_from_legacy(footer_text="   " + chr(10) + "  ", footer_odd="  ")
    doc = fitz.open(pdf_with_headers)
    try:
        hf.apply_pdf_headers_footers(doc, spec)
        assert band_text(doc[0], "footer") == "DEPSTAR 1"
    finally:
        doc.close()


def test_blank_side_boxes_fall_back_to_the_blanket_text(pdf_with_headers):
    """A half-filled sides mode must still write the header the user typed."""
    spec = hf.spec_from_legacy(
        header_text="TYPED HEADER", header_odd="", header_even="",
footer_text="TYPED FOOTER",
    )
    doc = fitz.open(pdf_with_headers)
    try:
        hf.apply_pdf_headers_footers(doc, spec)
        assert band_text(doc[0], "header") == "TYPED HEADER"
        assert band_text(doc[1], "footer") == "TYPED FOOTER"
    finally:
        doc.close()


def test_a_header_too_long_for_its_band_leaves_the_old_one_alone(pdf_with_headers):
    """The reported failure: an over-long header was erased, then nothing drawn.

    ``insert_textbox`` silently writes nothing when the text does not fit, so the
    order has to be prove-it-fits, then erase, then write.
    """
    before = _full_bands(pdf_with_headers)

    apply_pdf(pdf_with_headers, header_text="X" * 4000, font_size=24)

    assert _full_bands(pdf_with_headers) == before


def test_a_taller_header_still_renders_over_the_old_one(pdf_with_headers):
    """A one-line box cannot hold a three-line header; it used to vanish."""
    apply_pdf(
        pdf_with_headers,
        header_text="Line one of the new header" + chr(10)
        + "Line two of the new header" + chr(10) + "Line three",
        font_size=9,
    )

    doc = fitz.open(pdf_with_headers)
    try:
        rendered = band_text(doc[0], "header")
        assert "Line one of the new header" in rendered
        assert "Old Subject" not in rendered
    finally:
        doc.close()
