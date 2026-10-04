"""Which action a prompt maps to, and how an attachment changes the answer.

``understand_command`` is the router for every AI action, so a regression here
surfaces as "the AI tried to rewrite text when I asked to swap a logo". Only the
actions ``documents.py`` actually branches on are asserted; inventing names for
formatting verbs that the router does not implement would have tested nothing.

Gemini is stubbed so the rule chain and the local brain stay deterministic and
offline. That is deliberate: a test whose result depends on a network model is a
test that fails for the wrong reason.
"""

import pytest

from RapidDoc.backend.app.services import gemini_service
from RapidDoc.backend.app.services.gemini_service import understand_command


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(gemini_service, "_understand_with_gemini", lambda *a, **k: None)


def intent(command, has_image_upload=False):
    result = understand_command(command, has_image_upload)
    return result["action"], result


# ---------------------------------------------------------------------------
# replace_image requires an upload
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "replace the logo",
    "swap the image on page 2",
    "change this picture",
    "replace the first image",
])
def test_attached_file_makes_an_image_request_an_image_action(command):
    assert intent(command, has_image_upload=True)[0] == "replace_image"


def test_image_words_without_an_upload_are_not_an_image_action():
    """There is no file to swap in, so claiming replace_image would be a no-op
    reported as success."""
    assert intent("replace the logo", has_image_upload=False)[0] != "replace_image"


def test_attached_file_does_not_swallow_a_text_request():
    """A stray attachment must not turn 'set the header to Draft' into a swap."""
    assert intent("set the header to Draft", has_image_upload=True)[0] == "header"


def test_replace_image_result_carries_no_text_slots():
    _, result = intent("replace the first image on page 2", has_image_upload=True)
    assert "find_text" not in result, result
    assert "new_text" not in result, result


# ---------------------------------------------------------------------------
# The actions the router implements
# ---------------------------------------------------------------------------

def test_replace_carries_both_slots():
    _, result = intent("replace this word with banana")
    assert result["action"] == "replace"
    assert result["find_text"] == "this word"
    assert result["replace_text"] == "banana"


def test_change_wording_also_produces_replace():
    _, result = intent("change this to banana")
    assert result["action"] == "replace"
    assert result["replace_text"] == "banana"


def test_header_carries_the_new_text():
    _, result = intent("set the header to Draft")
    assert result["action"] == "header"
    assert result["new_text"] == "Draft"


def test_footer_carries_the_new_text():
    _, result = intent("set the footer to Confidential")
    assert result["action"] == "footer"
    assert result["new_text"] == "Confidential"


def test_summarize_defaults_to_whole_document():
    _, result = intent("summarize this document")
    assert result["action"] == "summarize"
    assert result["scope"] == "document"
    assert result["page"] is None


def test_generate_mcq_defaults_to_five_questions():
    _, result = intent("generate 5 mcqs")
    assert result["action"] == "generate_mcq"
    assert result["num_questions"] == 5


def test_generate_mcq_respects_a_requested_count():
    _, result = intent("generate 10 mcqs")
    assert result["num_questions"] == 10


def test_mcq_prompt_without_a_count_still_gets_a_default():
    _, result = intent("create mcqs from this")
    assert result["action"] == "generate_mcq"
    assert result["num_questions"] >= 1


# ---------------------------------------------------------------------------
# Unknown input
# ---------------------------------------------------------------------------

def test_nonsense_is_not_guessed():
    assert intent("flibbertigibbet the sprocket")[0] == "unknown"


def test_empty_prompt_is_not_an_action():
    assert intent("")[0] == "unknown"


def test_whitespace_prompt_is_not_an_action():
    assert intent("   ")[0] == "unknown"


@pytest.mark.parametrize("command", ["make this bold", "align left", "centre this heading"])
def test_unimplemented_formatting_verbs_are_reported_unknown(command):
    """Pins current behaviour: these are toolbar operations, not AI actions.

    If one of these ever starts returning a real action, the router needs a
    branch for it - this test is the reminder.
    """
    assert intent(command)[0] == "unknown"


def test_actions_are_lowercase_and_stable():
    for command in ["set the header to Draft", "replace the logo", "summarize this", "???"]:
        for upload in (False, True):
            name, _ = intent(command, upload)
            assert name == name.lower()
            assert isinstance(name, str)


def test_unknown_result_is_json_safe():
    _, result = intent("???")
    assert set(result) <= {"action", "engine", "confidence", "intent"}, result
    assert all(
        isinstance(v, (str, int, float, bool, type(None))) for v in result.values()
    ), result