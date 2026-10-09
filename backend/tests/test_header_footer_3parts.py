import pytest
from RapidDoc.backend.app.services import header_footer as hf
from RapidDoc.backend.app.services.gemini_service import understand_command


def test_split_and_join_3_parts():
    # 3 parts
    left, center, right = hf.split_3_parts("LeftText\tCenterText\tRightText")
    assert left == "LeftText"
    assert center == "CenterText"
    assert right == "RightText"

    joined = hf.join_3_parts(left, center, right)
    assert joined == "LeftText\tCenterText\tRightText"

    # 2 parts
    left2, center2, right2 = hf.split_3_parts("LeftText\tRightText")
    assert left2 == "LeftText"
    assert center2 == ""
    assert right2 == "RightText"

    # 1 part
    left1, center1, right1 = hf.split_3_parts("SingleText")
    assert left1 == "SingleText"
    assert center1 == ""
    assert right1 == ""


def test_update_3_part_text():
    # Update part 1 (left)
    orig = "OldLeft\tCenterVal\tRightVal"
    updated1 = hf.update_3_part_text(orig, 1, "NewLeft")
    assert updated1 == "NewLeft\tCenterVal\tRightVal"

    # Update part 2 (center)
    updated2 = hf.update_3_part_text(orig, 2, "NewCenter")
    assert updated2 == "OldLeft\tNewCenter\tRightVal"

    # Update part 3 (right)
    updated3 = hf.update_3_part_text(orig, 3, "NewRight")
    assert updated3 == "OldLeft\tCenterVal\tNewRight"

    # Update on single text: update center
    single = "MyHeader"
    updated_single = hf.update_3_part_text(single, 2, "Draft")
    assert updated_single == "MyHeader\tDraft\t"
    l, c, r = hf.split_3_parts(updated_single)
    assert l == "MyHeader"
    assert c == "Draft"

    # Update part 1 from empty
    assert hf.update_3_part_text("", 1, "LeftOnly") == "LeftOnly"


def test_command_bar_header_part_1_all_pages():
    # Exact wording matching user prompt ("change first part of heder tot this")
    res1 = understand_command("change first part of heder tot this")
    assert res1["action"] == "header"
    assert res1["part"] == 1
    assert res1["part_name"] == "left"
    assert res1["new_text"] == "this"
    assert res1["page"] == "all"

    # Numbered part 1
    res2 = understand_command("change 1st part of header to 'Confidential'")
    assert res2["action"] == "header"
    assert res2["part"] == 1
    assert res2["new_text"] == "Confidential"
    assert res2["page"] == "all"

    # "header part 1"
    res3 = understand_command("change header part 1 to RapidDoc Report")
    assert res3["action"] == "header"
    assert res3["part"] == 1
    assert res3["new_text"] == "RapidDoc Report"


def test_command_bar_header_part_2_and_3():
    # Part 2 / center
    res1 = understand_command("change second part of header to 'Draft'")
    assert res1["action"] == "header"
    assert res1["part"] == 2
    assert res1["part_name"] == "center"
    assert res1["new_text"] == "Draft"
    assert res1["page"] == "all"

    # Center keyword
    res2 = understand_command("change center header to 'Annual Review'")
    assert res2["action"] == "header"
    assert res2["part"] == 2
    assert res2["new_text"] == "Annual Review"

    # Part 3 / right
    res3 = understand_command("change 3rd part of header to 'Page {PAGE}'")
    assert res3["action"] == "header"
    assert res3["part"] == 3
    assert res3["part_name"] == "right"
    assert res3["new_text"] == "Page {PAGE}"

    # Right keyword
    res4 = understand_command("change right header to 2026")
    assert res4["action"] == "header"
    assert res4["part"] == 3
    assert res4["new_text"] == "2026"


def test_command_bar_footer_parts_and_page_targeting():
    # Footer part 1
    res1 = understand_command("change first part of footer to 'Copyright 2026'")
    assert res1["action"] == "footer"
    assert res1["part"] == 1
    assert res1["new_text"] == "Copyright 2026"
    assert res1["page"] == "all"

    # Footer part 2 on specific page (page 2)
    res2 = understand_command("change second part of footer to 'Page 2' on page 2")
    assert res2["action"] == "footer"
    assert res2["part"] == 2
    assert res2["page"] == 2
    assert res2["new_text"] == "Page 2"

    # Footer part 3 on first page
    res3 = understand_command("change footer part 3 to 'Internal Only' on first page")
    assert res3["action"] == "footer"
    assert res3["part"] == 3
    assert res3["page"] == "first"
    assert res3["new_text"] == "Internal Only"
