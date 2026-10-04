"""Resizing images without disturbing anything else.

Two things have to hold for a resize to be trustworthy: the picture really does
come out the requested size, and nothing *around* it moves. The second is the
one that regresses easily - a DOCX resize that only updates ``wp:extent`` leaves
the shape transform stale and Word renders the old box, and a PDF resize that
rewrites the content stream wrongly can corrupt the whole page rather than just
one picture. So these tests assert the final geometry from a re-opened file, not
just that the writer returned ok.
"""

import math

import fitz
import pytest

from RapidDoc.backend.app.services.docx_editor import (
    collect_docx_image_targets,
    get_docx_image_parts,
    resize_docx_images,
)
from RapidDoc.backend.app.services.image_geometry import (
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_PT,
    EMU_PER_PX,
    ResizeError,
    normalise_unit,
    resolve_target_box,
    to_emu,
)
from RapidDoc.backend.app.services.pdf_editor import get_pdf_image_slots, resize_pdf_images

from imagefixtures import png_bytes

ONE_INCH_EMU = EMU_PER_INCH


def emu_to_px(emu):
    return emu / EMU_PER_PX


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def test_inch_is_the_reference_unit():
    assert to_emu(1, "in") == EMU_PER_INCH
    assert to_emu(2.54, "cm") == pytest.approx(EMU_PER_INCH, rel=0.001)
    assert to_emu(25.4, "mm") == pytest.approx(EMU_PER_INCH, rel=0.001)
    assert to_emu(72, "pt") == EMU_PER_INCH


def test_pixel_is_96dpi():
    assert to_emu(96, "px") == EMU_PER_INCH


def test_unit_aliases_are_accepted():
    for alias in ("inches", "inch", '"', "IN"):
        assert normalise_unit(alias) == "in"
    for alias in ("pixels", "pixel"):
        assert normalise_unit(alias) == "px"


def test_unknown_unit_is_rejected_with_the_valid_set():
    with pytest.raises(ResizeError) as exc:
        normalise_unit("furlongs")
    assert "px" in str(exc.value) and "mm" in str(exc.value)


# ---------------------------------------------------------------------------
# Target box arithmetic
# ---------------------------------------------------------------------------

def test_width_only_derives_the_height_from_the_current_ratio():
    w, h = resolve_target_box(1000, 500, width=4, unit="in")
    assert w == 4 * EMU_PER_INCH
    assert h == 2 * EMU_PER_INCH


def test_height_only_derives_the_width():
    w, h = resolve_target_box(1000, 500, height=2, unit="in")
    assert w == 4 * EMU_PER_INCH
    assert h == 2 * EMU_PER_INCH


def test_both_dimensions_with_aspect_locked_takes_the_width():
    """A locked ratio cannot satisfy two numbers; width is the predictable one."""
    w, h = resolve_target_box(1000, 500, width=4, height=9, unit="in")
    assert w == 4 * EMU_PER_INCH
    assert h == 2 * EMU_PER_INCH


def test_both_dimensions_with_aspect_free_applies_both():
    w, h = resolve_target_box(1000, 500, width=4, height=9, unit="in", keep_aspect=False)
    assert w == 4 * EMU_PER_INCH
    assert h == 9 * EMU_PER_INCH


def test_one_dimension_without_aspect_leaves_the_other_alone():
    w, h = resolve_target_box(1000, 500, width=4, unit="in", keep_aspect=False)
    assert w == 4 * EMU_PER_INCH
    assert h == 500


def test_a_square_image_stays_square():
    w, h = resolve_target_box(1000, 1000, width=3, unit="in")
    assert w == h == 3 * EMU_PER_INCH


@pytest.mark.parametrize("kwargs,fragment", [
    ({}, "width, a height"),
    ({"width": 0}, "greater than zero"),
    ({"width": -5}, "greater than zero"),
    ({"height": 0}, "greater than zero"),
    ({"width": "wide"}, "number"),
    ({"width": 100000}, "larger than"),
])
def test_invalid_requests_are_refused_with_a_readable_reason(kwargs, fragment):
    with pytest.raises(ResizeError) as exc:
        resolve_target_box(1000, 500, unit="in", **kwargs)
    assert fragment in str(exc.value), str(exc.value)


def test_image_with_no_known_size_cannot_be_resized():
    with pytest.raises(ResizeError) as exc:
        resolve_target_box(0, 0, width=2, unit="in")
    assert "Replace it instead" in str(exc.value)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def docx_display_size(path, index=0):
    part = get_docx_image_parts(path)[index]
    return part["width"], part["height"]


def test_docx_width_in_inches(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "width": 1, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    width, height = docx_display_size(docx_images, 1)
    assert width == pytest.approx(96, abs=1), width
    assert height == pytest.approx(96, abs=1), height


def test_docx_height_only(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "height": 2, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    width, height = docx_display_size(docx_images, 1)
    assert height == pytest.approx(192, abs=1), height
    assert width == pytest.approx(192, abs=1), "aspect kept, so width followed"


def test_docx_resize_keeps_every_other_image_untouched(docx_images):
    before = docx_display_size(docx_images, 2)
    resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "width": 1, "unit": "in"}
    ])
    assert docx_display_size(docx_images, 2) == before


def test_docx_resize_does_not_renumber(docx_images):
    before = [p["index"] for p in get_docx_image_parts(docx_images)]
    resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "width": 1, "unit": "in"}
    ])
    assert [p["index"] for p in get_docx_image_parts(docx_images)] == before


def test_docx_resize_leaves_the_pixels_alone(docx_images):
    """Resizing is layout only - the image data must not be re-encoded."""
    from RapidDoc.backend.app.services.export_service import get_document_image_bytes

    before, _ = get_document_image_bytes(docx_images, "docx", 1)
    resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "width": 1, "unit": "in"}
    ])
    after, _ = get_document_image_bytes(docx_images, "docx", 1)
    assert before == after


def test_docx_resize_keeps_the_crop(docx_images):
    """The reported failure: a resize revealed regions the author had cropped out.

    A replacement must clear ``a:srcRect`` because the new image has its own
    framing. A resize is the *same* picture at a new size, so clearing the crop
    there silently changes the content of the image.
    """
    import docx
    from lxml import etree
    from docx.oxml.ns import qn

    doc = docx.Document(docx_images)
    blip = collect_docx_image_targets(doc)[0]["blips"][0]
    node = blip.getparent()
    while node.tag not in (qn("w:drawing"), qn("w:pict")):
        node = node.getparent()
    blip_fill = node.find(".//" + qn("pic:blipFill"))
    crop = blip_fill.find(qn("a:srcRect"))
    if crop is None:
        crop = etree.SubElement(blip_fill, qn("a:srcRect"))
    crop.set("l", "12000")
    crop.set("r", "12000")
    doc.save(docx_images)

    resize_docx_images(docx_images, docx_images, [
        {"target_index": 0, "width": 2, "unit": "in"}
    ])

    after = docx.Document(docx_images)
    blip = collect_docx_image_targets(after)[0]["blips"][0]
    node = blip.getparent()
    while node.tag not in (qn("w:drawing"), qn("w:pict")):
        node = node.getparent()
    kept = node.find(".//" + qn("pic:blipFill")).find(qn("a:srcRect"))
    assert kept is not None, "resize must not discard the crop"
    assert kept.get("l") == "12000"


def test_docx_resize_updates_the_shape_transform_not_just_the_layout_box(docx_images):
    """wp:extent alone is not enough; Word also reads a:xfrm/a:ext."""
    import docx
    from docx.oxml.ns import qn

    resize_docx_images(docx_images, docx_images, [
        {"target_index": 2, "width": 1, "unit": "in"}
    ])
    d = docx.Document(docx_images)
    r_id = next(
        b.get(qn("r:embed"))
        for b in d.element.body.iter(qn("a:blip"))
        if b.get(qn("r:embed"))
    )
    del r_id  # only the first blip is inspected below; see the assertion

    drawings = d.element.body.findall(".//" + qn("w:drawing"))
    target = drawings[-1]
    extent = target.find(".//" + qn("wp:extent"))
    ext = target.find(".//" + qn("a:ext"))
    assert extent.get("cx") == ext.get("cx"), "layout box and shape transform disagree"
    assert int(extent.get("cx")) == pytest.approx(EMU_PER_INCH, rel=0.02)


def test_docx_resize_of_a_shared_part_applies_to_every_placement(docx_images):
    """Same logo drawn twice: both drawings must move, since sizing is layout."""
    outcome = resize_docx_images(docx_images, docx_images, [
        {"target_index": 1, "width": 1, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    assert outcome["reports"][0]["placements"] == 2, outcome["reports"]


def test_docx_resize_rejects_an_out_of_range_index(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [
        {"target_index": 99, "width": 1, "unit": "in"}
    ])
    assert not outcome["ok"]
    assert "does not exist" in outcome["error"]


def test_docx_resize_rejects_a_request_with_no_dimensions(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [{"target_index": 0}])
    assert not outcome["ok"]
    assert "width" in outcome["error"]


def test_docx_bad_resize_does_not_block_a_good_one(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [
        {"target_index": 0, "width": -1, "unit": "in"},
        {"target_index": 1, "width": 1, "unit": "in"},
    ])
    assert outcome["resized"] == 1, outcome


def test_docx_empty_request_is_refused(docx_images):
    outcome = resize_docx_images(docx_images, docx_images, [])
    assert not outcome["ok"]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def pdf_bbox(path, index):
    return get_pdf_image_slots(path)[index]["bbox"]


def test_pdf_width_in_inches(pdf_images):
    outcome = resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    x0, y0, x1, y1 = pdf_bbox(pdf_images, 2)
    assert x1 - x0 == pytest.approx(144, abs=1)
    assert y1 - y0 == pytest.approx(144, abs=1), "square image stays square"


def test_pdf_height_only(pdf_images):
    outcome = resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "height": 1, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    x0, y0, x1, y1 = pdf_bbox(pdf_images, 2)
    assert y1 - y0 == pytest.approx(72, abs=1)
    assert x1 - x0 == pytest.approx(72, abs=1)


def test_pdf_resize_keeps_the_top_left_corner(pdf_images):
    before = pdf_bbox(pdf_images, 2)
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    after = pdf_bbox(pdf_images, 2)
    assert after[0] == pytest.approx(before[0], abs=0.5), "left edge must not drift"
    assert after[1] == pytest.approx(before[1], abs=0.5), "top edge must not drift"
    assert after[3] < before[3], "shrinking from the top left lifts the bottom edge up"


def test_pdf_center_anchor_keeps_the_middle(pdf_images):
    before = pdf_bbox(pdf_images, 2)
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 3, "unit": "in", "anchor": "center"}
    ])
    after = pdf_bbox(pdf_images, 2)
    before_cx = (before[0] + before[2]) / 2
    before_cy = (before[1] + before[3]) / 2
    assert (after[0] + after[2]) / 2 == pytest.approx(before_cx, abs=0.5)
    assert (after[1] + after[3]) / 2 == pytest.approx(before_cy, abs=0.5)


def test_pdf_resize_does_not_touch_other_images(pdf_images):
    before = pdf_bbox(pdf_images, 0)
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    assert [round(v, 2) for v in pdf_bbox(pdf_images, 0)] == [round(v, 2) for v in before]


def test_pdf_resize_keeps_the_page_readable(pdf_images):
    """A malformed content stream would show up here as a parse error."""
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    doc = fitz.open(pdf_images)
    try:
        assert len(doc) == 3
        for page_num in range(len(doc)):
            page = doc[page_num]
            assert page.get_text("dict") is not None
            for _ in page.get_images(full=True):
                pass
    finally:
        doc.close()


def test_pdf_resize_keeps_the_image_count(pdf_images):
    before = len(get_pdf_image_slots(pdf_images))
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    assert len(get_pdf_image_slots(pdf_images)) == before


def test_pdf_resize_is_per_page_for_an_image_spanning_pages(pdf_repeated_logo):
    """The logo is one xref drawn on 3 pages, each with its own matrix.

    Resizing index 0 must therefore change only page 1 - that is what the index
    the user clicked means. (Replacement behaves the opposite way and changes all
    three, because there the pixels are shared.)
    """
    outcome = resize_pdf_images(pdf_repeated_logo, pdf_repeated_logo, [
        {"target_index": 0, "width": 2, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    assert outcome["reports"][0]["placements"] == 1, outcome["reports"]

    widths = []
    for index in range(3):
        x0, y0, x1, y1 = pdf_bbox(pdf_repeated_logo, index)
        widths.append(round(x1 - x0))
    assert widths[0] == 144, widths
    assert widths[1] == widths[2] == 80, widths


def test_pdf_resize_touches_both_copies_on_the_same_page(pdf_same_page_twice):
    """Same page, same xref, two placements - both go through one rewrite."""
    slots = get_pdf_image_slots(pdf_same_page_twice)
    assert len(slots) == 2 and slots[0]["xref"] == slots[1]["xref"]

    outcome = resize_pdf_images(pdf_same_page_twice, pdf_same_page_twice, [
        {"target_index": 0, "width": 2, "unit": "in"}
    ])
    assert outcome["ok"], outcome
    assert outcome["reports"][0]["placements"] == 2, outcome["reports"]
    for index in (0, 1):
        x0, y0, x1, y1 = pdf_bbox(pdf_same_page_twice, index)
        assert x1 - x0 == pytest.approx(144, abs=1)


def test_pdf_resize_rejects_an_out_of_range_index(pdf_images):
    outcome = resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 99, "width": 1, "unit": "in"}
    ])
    assert not outcome["ok"]
    assert "does not exist" in outcome["error"]


def test_pdf_refuses_to_resize_a_rotated_image(pdf_rotated_image):
    """Rotated matrices need recomposition, not component replacement."""
    outcome = resize_pdf_images(pdf_rotated_image, pdf_rotated_image, [
        {"target_index": 0, "width": 2, "unit": "in"}
    ])
    assert not outcome["ok"], "a rotated draw matrix must not be rewritten blindly"
    assert "rotated" in outcome["error"], outcome["error"]


def test_a_refused_resize_leaves_the_file_untouched(pdf_rotated_image):
    with open(pdf_rotated_image, "rb") as fh:
        before = fh.read()
    resize_pdf_images(pdf_rotated_image, pdf_rotated_image, [
        {"target_index": 0, "width": 2, "unit": "in"}
    ])
    with open(pdf_rotated_image, "rb") as fh:
        assert fh.read() == before, "a failed resize must not rewrite the document"


def test_pdf_empty_request_is_refused(pdf_images):
    outcome = resize_pdf_images(pdf_images, pdf_images, [])
    assert not outcome["ok"]


def test_pdf_resize_survives_repeated_application(pdf_images):
    """Applying a resize twice must be idempotent in size, not cumulative."""
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    first = pdf_bbox(pdf_images, 2)
    resize_pdf_images(pdf_images, pdf_images, [
        {"target_index": 2, "width": 2, "unit": "in"}
    ])
    second = pdf_bbox(pdf_images, 2)
    assert [round(v, 2) for v in first] == [round(v, 2) for v in second]