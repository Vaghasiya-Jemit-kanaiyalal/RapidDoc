"""Regression tests for keyword, translation, and study-note commands."""

import pytest

from RapidDoc.backend.app.services import gemini_service


@pytest.fixture(autouse=True)
def offline_routing(monkeypatch):
    """Keep command tests off the local transformer and cloud model paths."""
    monkeypatch.setattr(gemini_service, "classify_intent", lambda prompt: None)
    monkeypatch.setattr(
        gemini_service, "_understand_with_gemini", lambda *args, **kwargs: None
    )


def test_keyword_command_carries_requested_count():
    result = gemini_service.understand_command(
        "Extract 8 keywords from this document"
    )
    assert result["action"] == "extract_keywords"
    assert result["count"] == 8


def test_translation_command_carries_target_language():
    result = gemini_service.understand_command(
        "Translate the selected text into French"
    )
    assert result["action"] == "translate"
    assert result["target_language"] == "French"


def test_translation_without_language_is_still_a_translation_request():
    result = gemini_service.understand_command("Translate this document")
    assert result["action"] == "translate"
    assert result["target_language"] is None


def test_study_notes_are_structured_without_a_cloud_model():
    text = (
        "Photosynthesis converts light energy into chemical energy. Chloroplasts "
        "contain chlorophyll that absorbs sunlight. The light reactions produce "
        "ATP and NADPH. The Calvin cycle uses ATP and NADPH to fix carbon dioxide "
        "into glucose. Photosynthesis occurs in plant leaves. Glucose stores energy "
        "for plant growth."
    )
    result = gemini_service.generate_study_notes(text, "Photosynthesis Notes")

    assert result["engine"].endswith("+keywords")
    assert "# Study Notes: Photosynthesis Notes" in result["notes"]
    assert "## Key Terms" in result["notes"]
    assert "## Key Points" in result["notes"]
    assert "## Active Recall" in result["notes"]
    assert result["keywords"]


def test_translation_reports_missing_engine(monkeypatch):
    monkeypatch.setattr(gemini_service, "_gemini_client", lambda: None)
    result = gemini_service.translate_text("Hello world", "Spanish")

    assert result["translated_text"] == ""
    assert result["engine"] == "none"
    assert "GEMINI_API_KEY" in result["message"]
