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
    """All text a header/footer band should be judged on.

    Deliberately a plain clipped read with whitespace squeezed, not the
    production extractor. It is an independent check: if the two agree, the
    structured reader is describing what is genuinely on the page rather than
    agreeing with itself. Note it cannot see columns - two spans on one line come
    back space-joined here and tab-joined by ``hf.band_text``, which is expected
    and why the column tests assert on ``hf.band_text``.
    """
    rect = hf.band_rect(page, which)
    if which == "footer":
        rect = fitz.Rect(0, rect.y0 - 20, page.rect.width, page.rect.height)
    else:
        rect = fitz.Rect(0, 0, page.rect.width, rect.y1 + 20)
    return " ".join(page.get_text("text", clip=rect).split())


def structured_band_text(page, which, page_number=1, page_count=1):
    """What the editor is shown: one string per band, columns tab-separated."""
    return hf.band_text(page, which, page_number, page_count)


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
    """The editor still expects the flat lists, tab-separated within an entry.

    The lists stay flat because that is what the editor indexes into, but the two
    halves of a band must not be glued together: flattening them with spaces is
    what made the editor show one string and then rewrite the ID into the middle
    of the page instead of flush right.
    """
    info = get_pdf_headers_footers(pdf_with_headers)
    assert info["headers"] == ["Subject: Old Subject\tID: 0000"]
    assert info["footers"] == ["DEPSTAR\t{PAGE}"]
    # One footer, not four: the differing digit is a page number, not four
    # different footers, and reporting four put the editor in side-specific mode.
    assert info["different_odd_even"] is False


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
        assert structured_band_text(doc[0], "header") == "Subject: Old Subject\tID: 0000"
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
        assert structured_band_text(doc[0], "footer") == "DEPSTAR\t{PAGE}"
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


# ---------------------------------------------------------------------------
# Two columns on one line
# ---------------------------------------------------------------------------

def test_two_column_header_survives_a_round_trip(pdf_with_headers):
    """A left and a right half must stay two halves, not become one string."""
    doc = fitz.open(pdf_with_headers)
    try:
        assert structured_band_text(doc[0], "header") == "Subject: Old Subject\tID: 0000"
        assert structured_band_text(doc[0], "footer") == "DEPSTAR\t{PAGE}"
    finally:
        doc.close()


def test_two_column_text_is_written_as_two_columns(pdf_with_headers):
    apply_pdf(pdf_with_headers, header_text="Subject: New\tID: 0001")

    doc = fitz.open(pdf_with_headers)
    try:
        page = doc[0]
        assert structured_band_text(page, "header") == "Subject: New\tID: 0001"

        # The right half has to end on the same right edge the original did,
        # not float wherever the text happens to stop.
        spans = hf.zone_spans(page, hf.band_rect(page, "header"), "header")
        right = max(fitz.Rect(s["bbox"]).x1 for s in spans)
        assert right == pytest.approx(464.0, abs=2.0)
    finally:
        doc.close()


def test_a_single_unbreakable_word_does_not_wrap_out_of_the_band(pdf_with_headers):
    """A long filename has no spaces to break on, so it used to overflow.

    ``insert_textbox`` reports success even when it silently wraps onto a second
    line. That second line fell below the band and was clipped, so the header came
    back missing its last character. The replacement now shrinks to fit instead.
    """
    apply_pdf(pdf_with_headers, header_text="Practical2_AWDF_24DCS140.pdf")

    doc = fitz.open(pdf_with_headers)
    try:
        text = structured_band_text(doc[0], "header")
        assert text == "Practical2_AWDF_24DCS140.pdf"

        page = doc[0]
        rect = hf.band_rect(page, "header")
        rows = hf.band_rows(hf.zone_spans(page, rect, "header"))
        assert len(rows) == 1, "the header wrapped onto a second line"
    finally:
        doc.close()


def test_the_replacement_keeps_the_documents_text_column(pdf_with_headers):
    """Not 8pt from the paper edge: aligned to where the body already is.

    A single centred section starts wherever centring puts it, so this asks for
    left alignment to pin the column itself down.
    """
    apply_pdf(
        pdf_with_headers,
        header_text="A new header",
        footer_text="A new footer",
        header_alignment="left",
        footer_alignment="left",
    )

    doc = fitz.open(pdf_with_headers)
    try:
        page = doc[0]
        for which in ("header", "footer"):
            spans = hf.zone_spans(page, hf.band_rect(page, which), which)
            assert spans, f"{which} went missing"
            left = min(fitz.Rect(s["bbox"]).x0 for s in spans)
            assert left == pytest.approx(60.0, abs=2.0), which
    finally:
        doc.close()


def test_a_two_column_header_spans_the_full_text_column(pdf_with_headers):
    """The left half starts at the margin, the right half ends at the old right edge."""
    apply_pdf(pdf_with_headers, header_text="Left half\tRight half")

    doc = fitz.open(pdf_with_headers)
    try:
        spans = hf.zone_spans(doc[0], hf.band_rect(doc[0], "header"), "header")
        assert len(spans) == 2
        left = min(fitz.Rect(s["bbox"]).x0 for s in spans)
        right = max(fitz.Rect(s["bbox"]).x1 for s in spans)
        assert left == pytest.approx(60.0, abs=2.0)
        assert right == pytest.approx(464.0, abs=2.0)
    finally:
        doc.close()


def test_typography_is_inherited_when_the_caller_names_no_font(pdf_with_headers):
    """Changing the words must not also change how they look.

    The editor sends no font unless the user picks one, so a Times bold header
    used to come back as small grey Helvetica - a downgrade nobody asked for.
    """
    before = fitz.open(pdf_with_headers)
    try:
        original = hf.read_pdf_headers_footers(before)["header_style"]
    finally:
        before.close()

    apply_pdf(pdf_with_headers, header_text="Still the same look")

    after = fitz.open(pdf_with_headers)
    try:
        assert hf.read_pdf_headers_footers(after)["header_style"] == original
    finally:
        after.close()


def test_an_explicit_font_still_overrides(pdf_with_headers):
    apply_pdf(pdf_with_headers, header_text="Override", font_name="Courier New")

    doc = fitz.open(pdf_with_headers)
    try:
        style = hf.read_pdf_headers_footers(doc)["header_style"]
        assert style["font"] == "Courier New"
    finally:
        doc.close()


def test_typographic_characters_are_not_corrupted_into_question_marks(pdf_with_headers):
    """A base-14 PDF font cannot draw an en dash, and PyMuPDF wrote '?' instead.

    The save reported success while quietly replacing the dash on every page, so
    the difference has to be made deliberately, not by accident.
    """
    apply_pdf(pdf_with_headers, footer_text="DEPSTAR \u2013 Campus")

    doc = fitz.open(pdf_with_headers)
    try:
        text = band_text(doc[0], "footer")
        assert "?" not in text
        assert "DEPSTAR" in text and "Campus" in text
    finally:
        doc.close()


def test_one_footer_is_not_mistaken_for_four_different_footers(pdf_with_headers):
    """A changing page number is not a difference between left and right pages."""
    info = get_pdf_headers_footers(pdf_with_headers)
    assert len(info["footers"]) == 1
    assert info["footer_odd"] == info["footer_even"]
    assert info["different_odd_even"] is False


def test_a_first_header_on_a_page_that_has_none_is_actually_written(pdf_no_furniture):
    """Adding a header to a document that has none used to silently do nothing.

    Every header/footer test replaced furniture that was already there. On a page
    with none, the replacement box was anchored a hair above the band's own top
    edge, so the text landed at y=4.8-18.6 where ``zone_spans`` classifies it as
    body text - the save reported success and the header read back as empty.
    """
    apply_pdf(pdf_no_furniture, header_text="Subject: New\tID: 24DCS140")

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        assert structured_band_text(page, "header", 1, 4) == "Subject: New\tID: 24DCS140"
        assert "Body content on page 1." in full_text(page)
    finally:
        doc.close()


def test_a_first_footer_on_a_page_that_has_none_is_actually_written(pdf_no_furniture):
    apply_pdf(pdf_no_furniture, footer_text="DEPSTAR (CSE)\t{PAGE}")

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        assert structured_band_text(page, "footer", 1, 4) == "DEPSTAR (CSE)\t{PAGE}"
        assert "Body content on page 1." in full_text(page)
    finally:
        doc.close()


def test_a_new_two_column_header_lands_on_the_margins(pdf_no_furniture):
    """The exact acceptance configuration, on a page with no existing furniture.

    Both columns on one row, left flush at the left margin, right flush at the
    right margin, and a real gap between them - the layout the reference document
    has and the editor's two fields imply.
    """
    apply_pdf(
        pdf_no_furniture,
        header_text="Subject: ITUE301 - Advanced Web Development Frameworks\tID: 24DCS140",
    )

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        rows = hf.band_rows(hf.zone_spans(page, hf.band_rect(page, "header"), "header"))
        assert len(rows) == 1, "the header wrapped instead of staying on one row"

        boxes = [fitz.Rect(span["bbox"]) for span in sorted(rows[0], key=lambda s: s["bbox"][0])]
        assert len(boxes) == 2
        left, right = boxes
        assert round(left.x0, 1) == 72.0
        assert round(right.x1, 1) == 523.0
        assert right.x0 > left.x1, "the two columns overlap"
    finally:
        doc.close()


def test_long_text_is_written_rather_than_dropped(pdf_no_furniture):
    """Text too long for one line used to be discarded entirely.

    ``_fits`` refused to let furniture wrap unless the author had typed a
    newline, so 300 characters fitted no size at all and the header was replaced
    by nothing. Wrapping is now allowed as a fallback, bounded by the space above
    the body so the two can never collide.
    """
    # Measured before the write: afterwards the header's own second line counts
    # as body text and the ceiling collapses onto it.
    before = fitz.open(pdf_no_furniture)
    ceiling = hf.body_top(before) - hf.ZONE_GROWTH
    before.close()

    apply_pdf(pdf_no_furniture, header_text="L" * 300)

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        # Read the whole top of the page, not the band: a wrapped header extends
        # below the nominal band, which is exactly what is under test here.
        rendered = page.get_text("text", clip=fitz.Rect(0, 0, page.rect.width, ceiling))
        assert rendered.count("L") >= 290, f"only {rendered.count('L')} of 300 characters rendered"
        assert "Body content on page 1." in full_text(page)
    finally:
        doc.close()


def test_a_wrapped_header_stays_above_the_body(pdf_no_furniture):
    """Growth into the gap above the body must stop at the body."""
    before = fitz.open(pdf_no_furniture)
    ceiling = hf.body_top(before) - hf.ZONE_GROWTH
    before.close()

    apply_pdf(pdf_no_furniture, header_text="L" * 300)

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        below = fitz.Rect(0, ceiling, page.rect.width, page.rect.height / 2)
        leaked = page.get_text("text", clip=below)
        assert "L" not in leaked, (
            f"the header wrapped past the ceiling at y={ceiling:.1f} into {leaked!r}"
        )
        assert "Body content on page 1." in full_text(page)
    finally:
        doc.close()


def test_a_right_only_header_gets_the_whole_column(pdf_no_furniture):
    """A right-only header was handed half the column and so could not be laid out.

    ``_zone_plan`` reserved 35% of the column for a left section that was not
    there, which halved the width available to the right one.
    """
    apply_pdf(pdf_no_furniture, header_text="\t" + "R" * 300)

    doc = fitz.open(pdf_no_furniture)
    try:
        page = doc[0]
        spans = hf.zone_spans(page, hf.band_rect(page, "header"), "header")
        assert spans, "a right-only header was dropped"
        assert max(fitz.Rect(span["bbox"]).x1 for span in spans) >= 520.0
    finally:
        doc.close()


def test_a_lone_page_number_is_read_back_as_a_field(pdf_no_furniture):
    """A footer that is only the page number is still an outermost column.

    Only multi-column bands were considered, so a bare ``{PAGE}`` came back as the
    literal ``1`` - and re-saving froze that number onto every page.
    """
    apply_pdf(pdf_no_furniture, footer_text="{PAGE}")

    doc = fitz.open(pdf_no_furniture)
    try:
        for number in range(1, 5):
            assert structured_band_text(doc[number - 1], "footer", number, 4) == "{PAGE}"
    finally:
        doc.close()


def test_a_bare_number_in_the_middle_is_not_taken_for_a_page_number(pdf_no_furniture):
    """The guard against over-eager detection must survive the change above."""
    apply_pdf(pdf_no_furniture, footer_text="Left\t2024\tRight")

    doc = fitz.open(pdf_no_furniture)
    try:
        text = structured_band_text(doc[0], "footer", 1, 4)
        assert "2024" in text
    finally:
        doc.close()


def test_a_distinct_first_page_is_reported_as_one(tmp_path):
    """``different_first`` compared page 1 against itself.

    ``header_odd`` was filled from the first odd page, which is page 1, so a
    3-page document with a cover header reported no distinct first page - and
    re-saving flattened the cover onto every page.
    """
    path = tmp_path / "first_page.pdf"
    doc = fitz.open()
    for number in range(1, 4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 300), f"Body {number}", fontsize=11)
    doc.save(str(path))
    doc.close()

    apply_pdf_styling(
        path, path,
        header_text="Normal header", header_text_first="Cover header",
        footer_text="Normal footer\t{PAGE}", footer_text_first="Cover footer",
    )

    doc = fitz.open(path)
    try:
        info = hf.read_pdf_headers_footers(doc)
        assert info["header_first"] == "Cover header"
        assert info["header_odd"] == "Normal header"
        assert info["different_first"] is True
    finally:
        doc.close()


def test_a_single_page_document_has_no_distinct_first_page(tmp_path):
    """With only page 1 there is nothing for it to differ from."""
    path = tmp_path / "single.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 300), "Body", fontsize=11)
    doc.save(str(path))
    doc.close()

    apply_pdf_styling(path, path, header_text="Only header")

    doc = fitz.open(path)
    try:
        info = hf.read_pdf_headers_footers(doc)
        assert info["header_odd"] == "Only header"
        assert info["different_first"] is False
    finally:
        doc.close()


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
