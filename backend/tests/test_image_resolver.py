"""Turning words into image indexes, against real documents.

The resolver is the part of image replacement a user can get wrong silently, so
these tests assert the *mapping* (words -> canonical index) rather than just the
status. A test that only checked "did not raise" would have passed while
"the 1st image on page 2" replaced the second image - which it did, until these
were written.
"""

import fitz
import pytest

from RapidDoc.backend.app.services.image_resolver import (
    MAX_REPLACEMENT_BYTES,
    build_image_inventory,
    read_and_validate_image,
    resolve_image_targets,
)

from imagefixtures import jpeg_bytes, png_bytes


@pytest.fixture
def multipage_pdf(tmp_path):
    """2 images on page 1, 5 on page 2, 1 on page 3.

    Every image has distinct pixels so each is its own xref - otherwise PyMuPDF
    folds identical streams into one object and "the 3rd image" would change all
    of them, which is a separate behaviour asserted below.
    """
    path = tmp_path / "multipage.pdf"
    doc = fitz.open()
    layout = [
        [(0, 0, 100, 100), (200, 0, 400, 100)],
        [(0, i * 120, 100, i * 120 + 100) for i in range(5)],
        [(0, 0, 200, 200)],
    ]
    for n, specs in enumerate(layout):
        page = doc.new_page()
        for x0, y0, x1, y1 in specs:
            page.insert_image(
                fitz.Rect(x0, y0, x1, y1),
                stream=png_bytes(int(x1 - x0), int(y1 - y0), (n * 40 % 255, 10, 10)),
            )
    doc.save(str(path))
    doc.close()
    return str(path)


def resolve(command, path, file_type="pdf"):
    return resolve_image_targets(command, path, file_type)


def indexes(command, path, file_type="pdf"):
    result = resolve(command, path, file_type)
    assert result["status"] == "resolved", result.get("message")
    return result["indexes"]


# ---------------------------------------------------------------------------
# Page-scoped ordinals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word,expected_index", [
    ("1st", 2),   # page 2 starts at canonical index 2
    ("first", 2),
    ("2nd", 3),
    ("second", 3),
    ("third", 4),
    ("3rd", 4),
    ("5th", 6),
    ("last", 6),
])
def test_page_scoped_ordinal_is_one_based(multipage_pdf, word, expected_index):
    assert indexes(f"replace the {word} image on page 2", multipage_pdf) == [expected_index]


def test_page_scoped_reason_reports_the_position_it_picked(multipage_pdf):
    result = resolve("replace the 3rd image on page 2", multipage_pdf)
    assert result["reason"] == "image 3 of 5 on page 2", result


@pytest.mark.parametrize("page", [1, 2, 3])
def test_page_one_and_last_resolve_on_every_page(multipage_pdf, page):
    assert len(indexes(f"replace the first image on page {page}", multipage_pdf)) == 1
    assert len(indexes(f"replace the last image on page {page}", multipage_pdf)) == 1


def test_noun_first_word_order_is_also_one_based(multipage_pdf):
    """'image 2 on page 2' is the same address as 'the 2nd image on page 2'."""
    assert indexes("replace image 2 on page 2", multipage_pdf) == indexes(
        "replace the 2nd image on page 2", multipage_pdf
    )


def test_ordinal_past_the_end_of_a_page_says_so(multipage_pdf):
    result = resolve("replace the 9th image on page 3", multipage_pdf)
    assert result["status"] == "unresolved"
    assert "no 9th one on that page" in result["message"], result["message"]
    assert "1 image" in result["message"], "must say what the page actually holds"


def test_scoped_ordinal_beats_document_wide_ordinal(multipage_pdf):
    """The page qualifier must win over the same ordinal read document-wide."""
    assert indexes("replace the 1st image on page 3", multipage_pdf) == [7]
    assert indexes("replace the 1st image", multipage_pdf) == [0]


# ---------------------------------------------------------------------------
# Ambiguity
# ---------------------------------------------------------------------------

def test_bare_page_reference_is_ambiguous_not_a_guess(multipage_pdf):
    result = resolve("replace the image on page 2", multipage_pdf)
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 5


def test_ambiguous_candidates_are_numbered_from_one(multipage_pdf):
    result = resolve("replace the image on page 2", multipage_pdf)
    assert [c["position"] for c in result["candidates"]] == [1, 2, 3, 4, 5]
    assert [c["position_label"] for c in result["candidates"]] == ["1st", "2nd", "3rd", "4th", "5th"]
    # The label is what the UI shows, so it must name the page it came from.
    assert all("on page 2" in c["label"] for c in result["candidates"])


def test_candidate_order_follows_reading_order_not_xref_order(multipage_pdf):
    """Top-to-bottom, then left-to-right - the order a reader would count in."""
    result = resolve("replace the image on page 2", multipage_pdf)
    tops = [c["bbox"][1] for c in result["candidates"]]
    assert tops == sorted(tops), tops


def test_candidate_ordinal_label_is_speakable_again(multipage_pdf):
    """The suggested phrasing must actually resolve, or the hint is a dead end."""
    result = resolve("replace the image on page 2", multipage_pdf)
    for candidate in result["candidates"]:
        spoken = f"replace the {candidate['position_label']} image on page 2"
        assert indexes(spoken, multipage_pdf) == [candidate["index"]]


def test_single_image_page_resolves_without_a_picker(multipage_pdf):
    assert indexes("replace the image on page 3", multipage_pdf) == [7]


def test_ambiguity_message_shows_the_shorthand(multipage_pdf):
    result = resolve("replace the image on page 2", multipage_pdf)
    assert 'the 2nd image on page 2' in result["message"], result["message"]


# ---------------------------------------------------------------------------
# Document-wide addressing
# ---------------------------------------------------------------------------

def test_document_wide_ordinal(multipage_pdf):
    assert indexes("replace the first image", multipage_pdf) == [0]
    assert indexes("replace the third image", multipage_pdf) == [2]
    assert indexes("replace the last image", multipage_pdf) == [7]


def test_spoken_number_is_one_based(multipage_pdf):
    """'image 1' is the first image, i.e. index 0 - the trap being pinned here."""
    assert indexes("replace image 1", multipage_pdf) == [0]


def test_out_of_range_document_ordinal(multipage_pdf):
    result = resolve("replace the 99th image", multipage_pdf)
    assert result["status"] == "unresolved"
    assert "no 99th image" in result["message"]


def test_command_without_an_image_noun_is_unresolved(multipage_pdf):
    result = resolve("make the text bigger", multipage_pdf)
    assert result["status"] == "unresolved"
    assert "double-click" in result["message"]


def test_every_resolved_index_exists_in_the_inventory(multipage_pdf):
    inventory = build_image_inventory(multipage_pdf, "pdf")
    known = {entry["index"] for entry in inventory}
    for command in [
        "replace the 2nd image on page 2", "replace the last image",
        "replace image 4", "replace the first image on page 3",
    ]:
        assert set(indexes(command, multipage_pdf)) <= known


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def test_role_scoped_to_a_page_narrows_the_set(multipage_pdf):
    """'the picture on page 1' is 2 candidates; the UI must offer exactly those."""
    result = resolve("replace the picture on page 1", multipage_pdf)
    assert result["status"] == "ambiguous"
    assert {c["page_num"] for c in result["candidates"]} == {0}


def test_single_role_on_a_page_resolves(multipage_pdf):
    assert indexes("replace the picture on page 3", multipage_pdf) == [7]


# ---------------------------------------------------------------------------
# DOCX addressing
# ---------------------------------------------------------------------------

def test_docx_has_no_page_numbering(docx_images):
    inventory = build_image_inventory(docx_images, "docx")
    assert all(entry["page_num"] is None for entry in inventory)


def test_docx_document_wide_ordinal(docx_images):
    assert indexes("replace the second image", docx_images, "docx") == [1]
    assert indexes("replace the last image", docx_images, "docx") == [2]


def test_docx_page_reference_is_not_answered_with_a_wrong_page(docx_images):
    """There are no pages, so a page number must not silently pick something."""
    result = resolve("replace the image on page 2", docx_images, "docx")
    assert result["status"] != "resolved", result


def test_replace_image_1_by_this_phrases(multipage_pdf):
    assert indexes("replace the image 1 by this", multipage_pdf) == [0]
    assert indexes("replace image 1 by this", multipage_pdf) == [0]
    assert indexes("replace image 1 with this", multipage_pdf) == [0]
    assert indexes("replace 1 by this", multipage_pdf) == [0]
    assert indexes("replace image 2 by this", multipage_pdf) == [1]


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

def test_png_is_accepted():
    assert read_and_validate_image(png_bytes(10, 10)) == png_bytes(10, 10)


def test_jpeg_is_accepted():
    assert read_and_validate_image(jpeg_bytes(10, 10))


def test_non_image_bytes_are_rejected():
    with pytest.raises(ValueError):
        read_and_validate_image(b"this is definitely not an image")


def test_empty_upload_is_rejected():
    with pytest.raises(ValueError):
        read_and_validate_image(b"")


def test_oversized_upload_is_rejected():
    with pytest.raises(ValueError):
        read_and_validate_image(png_bytes(10, 10) + b"\x00" * MAX_REPLACEMENT_BYTES)


def test_error_messages_name_the_limit():
    with pytest.raises(ValueError) as exc:
        read_and_validate_image(b"\x00" * (MAX_REPLACEMENT_BYTES + 1))
    assert "MB" in str(exc.value)