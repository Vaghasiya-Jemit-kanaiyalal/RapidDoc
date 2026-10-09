import pytest
from RapidDoc.backend.app.services.gemini_service import (
    understand_command,
    _extract_exact_replacement,
    _fallback_table_action,
    _fallback_heading_action,
    _fallback_image_action,
    _fallback_qa_action,
)

def test_exact_replacement_preserves_wording_character_for_character():
    # 1. Direct quotes with trailing dot
    cmd1 = "Replace 'ABC Corporation' with 'ABC Corp.'"
    res1 = understand_command(cmd1)
    assert res1["action"] == "replace"
    assert res1["find_text"] == "ABC Corporation"
    assert res1["replace_text"] == "ABC Corp."
    assert res1["engine"] == "exact_quoted_rule"

    # 2. Acronym replacement without punctuation change
    cmd2 = "Change 'Computer Science and Engineering' to 'CSE'"
    res2 = understand_command(cmd2)
    assert res2["action"] == "replace"
    assert res2["find_text"] == "Computer Science and Engineering"
    assert res2["replace_text"] == "CSE"

    # 3. Double quotes
    cmd3 = 'Find every occurrence of "machine learning" and replace it with "ML".'
    res3 = understand_command(cmd3)
    assert res3["action"] == "replace"
    assert res3["find_text"] == "machine learning"
    assert res3["replace_text"] == "ML"
    assert res3["replace_all"] is True

def test_heading_styling_intent_rules():
    cmd = "Change every heading to dark blue"
    res = _fallback_heading_action(cmd)
    assert res is not None
    assert res["action"] == "style_headings"
    assert res["color_rgb"] == (0, 32, 96) # dark blue in Word Office palette

    cmd2 = "Make all headings 20px and bold"
    res2 = _fallback_heading_action(cmd2)
    assert res2 is not None
    assert res2["action"] == "style_headings"
    assert res2["bold"] is True
    assert res2["font_size"] == 20

def test_table_manipulation_intent_rules():
    cmd1 = "Delete the second column from every table"
    res1 = _fallback_table_action(cmd1)
    assert res1 is not None
    assert res1["action"] == "delete_column"
    assert res1["column_index"] == 1  # 0-indexed: 2nd column is index 1
    assert res1["table_index"] == "all"

    cmd2 = "Remove the third row from the first table"
    res2 = _fallback_table_action(cmd2)
    assert res2 is not None
    assert res2["action"] == "delete_row"
    assert res2["row_index"] == 2
    assert res2["table_index"] == 0

def test_image_intent_rules():
    cmd1 = "Remove all images"
    res1 = _fallback_image_action(cmd1)
    assert res1 is not None
    assert res1["action"] == "delete_image"
    assert res1["image_index"] == "all"

    cmd2 = "Describe this image"
    res2 = _fallback_image_action(cmd2)
    assert res2 is not None
    assert res2["action"] == "describe_image"

def test_qa_and_notes_intent_rules():
    cmd1 = "Find the important points from this document"
    res1 = _fallback_qa_action(cmd1)
    assert res1 is not None
    assert res1["action"] == "qa_extract"

    cmd2 = "Create study notes from this document"
    res2 = _fallback_qa_action(cmd2)
    assert res2 is not None
    assert res2["action"] == "qa_extract"

def test_selection_context_support():
    selection = {"text": "This is a draft introduction."}
    cmd = "Make this more professional"
    res = understand_command(cmd, selection=selection)
    assert res["action"] in ("rewrite", "style_headings", "qa_extract")

def test_summary_and_quiz_commands():
    res1 = understand_command("Summarize this document in 5 bullet points.")
    assert res1["action"] == "summarize"

    res2 = understand_command("Generate 10 MCQs from chapter 3.")
    assert res2["action"] == "generate_mcq"

def test_footer_and_rewrite_commands():
    res1 = understand_command("Change the footer to 'CHARUSAT – DEPSTAR'.")
    assert res1["action"] == "footer"
    assert "CHARUSAT" in res1["new_text"]

    res2 = understand_command("Rewrite the conclusion in a professional tone.")
    assert res2["action"] == "rewrite"


def test_presentation_generation_commands():
    # 1. Standard presentation command
    res1 = understand_command("Generate a presentation from this document")
    assert res1["action"] == "generate_presentation"
    assert res1["theme"] == "modern"

    # 2. Corporate theme
    res2 = understand_command("Make a ppt in corporate theme")
    assert res2["action"] == "generate_presentation"
    assert res2["theme"] == "corporate"

    # 3. Minimal slides
    res3 = understand_command("Export to slides with clean minimal layout")
    assert res3["action"] == "generate_presentation"
    assert res3["theme"] == "minimal"

    # 4. Convert document to presentation
    res4 = understand_command("Turn this document into a pptx")
    assert res4["action"] == "generate_presentation"

