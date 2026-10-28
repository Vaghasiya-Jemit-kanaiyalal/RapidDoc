"""Offline translation using Argos Translate (MIT license).

Provides a local fallback when cloud translation is unavailable or quota-exceeded.
Language packages (~50-100 MB each) are downloaded on first use and cached.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Global lock for package installation (prevents concurrent downloads)
_install_lock = threading.Lock()
_installed_pairs: set[tuple[str, str]] = set()

# Common language code mapping (Argos uses ISO 639-1 codes)
LANG_CODE_MAP = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "arabic": "ar",
    "hindi": "hi",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
    "vietnamese": "vi",
    "thai": "th",
    "indonesian": "id",
    "czech": "cs",
    "greek": "el",
    "hebrew": "he",
    "swedish": "sv",
    "danish": "da",
    "finnish": "fi",
    "norwegian": "no",
    "romanian": "ro",
    "hungarian": "hu",
    "ukrainian": "uk",
}

def _normalize_lang_code(lang: str) -> str:
    """Convert human-readable language name to ISO 639-1 code."""
    lang = (lang or "").strip().lower()
    return LANG_CODE_MAP.get(lang, lang[:2].lower())

def _ensure_package_installed(from_code: str, to_code: str) -> bool:
    """Download and install Argos language package if not already installed."""
    pair = (from_code, to_code)
    if pair in _installed_pairs:
        return True

    with _install_lock:
        if pair in _installed_pairs:
            return True

        try:
            import argostranslate.package
            import argostranslate.translate

            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()

            pkg = next(
                (p for p in available
                 if p.from_code == from_code and p.to_code == to_code),
                None
            )
            if pkg is None:
                logger.warning("No Argos package for %s -> %s", from_code, to_code)
                return False

            pkg.install()
            _installed_pairs.add(pair)
            logger.info("Installed Argos package: %s -> %s", from_code, to_code)
            return True

        except Exception as exc:
            logger.error("Failed to install Argos package %s->%s: %s", from_code, to_code, exc)
            return False

def translate_offline(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    """
    Translate text using locally installed Argos models.
    Returns translated text or None if translation unavailable.
    """
    if not text or not text.strip():
        return ""

    from_code = _normalize_lang_code(source_lang)
    to_code = _normalize_lang_code(target_lang)

    if from_code == to_code:
        return text

    if not _ensure_package_installed(from_code, to_code):
        return None

    try:
        import argostranslate.translate
        translated = argostranslate.translate.translate(text, from_code, to_code)
        return translated if translated else None
    except Exception as exc:
        logger.error("Argos translation error %s->%s: %s", from_code, to_code, exc)
        return None

def is_offline_translation_available(source_lang: str, target_lang: str) -> bool:
    """Check if a language pair is installed or installable."""
    from_code = _normalize_lang_code(source_lang)
    to_code = _normalize_lang_code(target_lang)
    if from_code == to_code:
        return True

    try:
        import argostranslate.package
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        return any(
            p.from_code == from_code and p.to_code == to_code
            for p in available
        )
    except Exception:
        return False