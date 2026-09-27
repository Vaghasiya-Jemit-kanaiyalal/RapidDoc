import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

CONVERSION_TIMEOUT_SECONDS = 180

# How many conversions may run at once. Each run already gets a private
# LibreOffice profile (`-env:UserInstallation`), which is what actually prevents
# the "Please verify input parameters" profile-lock collisions the frontend used
# to hit when React StrictMode double-invoked its effects. An unbounded pool
# still starves the machine on a big batch, so this stays deliberately small -
# but unlike the previous exclusive lock, two previews can be built at once
# instead of every request queueing behind the slowest one.
_CONVERSION_SLOTS = threading.BoundedSemaphore(2)

# Rendered-PDF cache. The editor requests a preview on mount *and* after every
# save, and LibreOffice needs seconds for a large document; without this the
# same unchanged file was re-converted over and over. Keyed by the source
# bytes' hash, so an edited file simply misses and is re-rendered - no staleness
# is possible, unlike a cache keyed on path or mtime alone.
_CACHE_MAX_ENTRIES = 6
_CACHE_MAX_BYTES = 96 * 1024 * 1024
_cache_lock = threading.Lock()
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_cache_bytes = 0


def _cache_key(docx_bytes: bytes) -> str:
    return hashlib.sha256(docx_bytes).hexdigest()


def _cache_get(key: str):
    with _cache_lock:
        value = _cache.get(key)
        if value is not None:
            _cache.move_to_end(key)
        return value


def _cache_put(key: str, value: bytes) -> None:
    global _cache_bytes
    with _cache_lock:
        if key in _cache:
            _cache_bytes -= len(_cache.pop(key))
        _cache[key] = value
        _cache.move_to_end(key)
        _cache_bytes += len(value)
        # Evict least-recently-used entries until both limits are satisfied.
        while _cache and (len(_cache) > _CACHE_MAX_ENTRIES or _cache_bytes > _CACHE_MAX_BYTES):
            evicted_key, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted)
            logger.debug("Evicted cached PDF preview %s", evicted_key[:12])


def clear_conversion_cache() -> None:
    with _cache_lock:
        _cache.clear()
        global _cache_bytes
        _cache_bytes = 0


def _profile_uri(directory: str) -> str:
    """`-env:UserInstallation` value for an isolated, per-run LibreOffice profile."""
    path = os.path.abspath(directory).replace("\\", "/")
    return f"file:///{path}"


def _find_libreoffice() -> str:
    """Locate the headless LibreOffice (soffice) binary on this machine."""
    # 1. Look on the PATH first.
    on_path = shutil.which("soffice")
    if on_path:
        return on_path

    # 2. Check well-known install locations per platform.
    if os.name == "nt":
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\LibreOffice\program\soffice.exe"),
        ]
    else:
        candidates = [
            "/usr/bin/libreoffice",
            "/usr/bin/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return ""


def _run_soffice(soffice: str, input_path: str, tmp_dir: str, out_name: str) -> tuple:
    """Run one conversion with an isolated profile. Returns (stdout, stderr)."""
    profile_dir = os.path.join(tmp_dir, "lo_profile")
    result = subprocess.run(
        [
            soffice,
            f"-env:UserInstallation={_profile_uri(profile_dir)}",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "--nofirststartwizard",
            "--convert-to",
            out_name,
            "--outdir",
            tmp_dir,
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=CONVERSION_TIMEOUT_SECONDS,
    )
    return result.stdout, result.stderr


def prewarm_docx_preview(docx_bytes: bytes) -> bool:
    """Populate the PDF cache ahead of the first preview request.

    A cold DOCX render costs 10-25s in headless LibreOffice, and that is exactly
    the wait a user sees when they open a document. Running the conversion right
    after upload means the preview request a few seconds later is a cache hit
    (0.04s). Failures are swallowed: a missing preview is a fallback, not an
    upload error.
    """
    try:
        convert_docx_bytes_to_pdf(docx_bytes)
        return True
    except Exception as exc:
        logger.warning("Could not pre-warm the document preview: %s", exc)
        return False


def convert_docx_bytes_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Convert an in-memory DOCX document to an in-memory PDF buffer.

    Uses headless LibreOffice (`soffice --headless --convert-to pdf`) so no
    document is ever written permanently to disk. A temporary directory holds
    the input/output files for the duration of the conversion and is removed
    afterwards.

    Three things keep this both correct and quick:

    * Every run gets its own LibreOffice profile, so concurrent runs cannot
      collide on the shared default profile in %APPDATA% - the cause of the
      "Please verify input parameters" failures behind "a Word file failed on
      first load and worked on retry".
    * A single retry is attempted, because LibreOffice's first run on a brand
      new profile can fail spuriously.
    * Results are cached by the SHA-256 of the input bytes, so reopening a
      document (or refreshing a preview that has not changed) returns instantly
      instead of paying for another conversion.
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LibreOffice is not installed on this server. Please install "
                   "LibreOffice to enable DOCX preview generation.",
        )

    key = _cache_key(docx_bytes)
    cached = _cache_get(key)
    if cached is not None:
        logger.debug("PDF preview cache hit for %s", key[:12])
        return cached

    # _CONVERSION_SLOTS bounds concurrency; every holder still writes to its own
    # temporary directory and profile, so the runs are genuinely independent.
    with _CONVERSION_SLOTS, tempfile.TemporaryDirectory(prefix="rapiddoc_preview_") as tmp_dir:
        input_path = os.path.join(tmp_dir, "document.docx")
        with open(input_path, "wb") as fh:
            fh.write(docx_bytes)

        pdf_path = os.path.join(tmp_dir, "document.pdf")
        last_error = ""

        for attempt in (1, 2):
            # Each attempt gets a clean profile directory.
            profile_dir = os.path.join(tmp_dir, "lo_profile")
            shutil.rmtree(profile_dir, ignore_errors=True)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

            try:
                stdout, stderr = _run_soffice(soffice, input_path, tmp_dir, "pdf")
            except subprocess.TimeoutExpired:
                last_error = f"timed out after {CONVERSION_TIMEOUT_SECONDS}s"
                logger.error("LibreOffice conversion %s (%s)", last_error, f"attempt {attempt}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Document conversion timed out. The document may be too complex to render.",
                )
            except Exception as exc:
                logger.error("Error launching LibreOffice: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not launch the document converter.",
                )

            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                with open(pdf_path, "rb") as fh:
                    result = fh.read()
                _cache_put(key, result)
                return result

            last_error = f"code={stdout!r} stdout={stdout} stderr={stderr}"
            logger.warning(
                "LibreOffice conversion produced no output on attempt %s: %s",
                attempt, last_error,
            )

        logger.error("LibreOffice conversion failed after 2 attempts: %s", last_error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to convert the document to PDF for preview.",
        )

