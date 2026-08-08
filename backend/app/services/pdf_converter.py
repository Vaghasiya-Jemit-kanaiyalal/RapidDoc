import logging
import os
import shutil
import subprocess
import tempfile

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

CONVERSION_TIMEOUT_SECONDS = 60


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


def convert_docx_bytes_to_pdf(docx_bytes: bytes) -> bytes:
    """
    Convert an in-memory DOCX document to an in-memory PDF buffer.

    Uses headless LibreOffice (`soffice --headless --convert-to pdf`) so no
    document is ever written permanently to disk. A temporary directory holds
    the input/output files for the duration of the conversion and is removed
    afterwards.
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LibreOffice is not installed on this server. Please install "
                   "LibreOffice to enable DOCX preview generation.",
        )

    with tempfile.TemporaryDirectory(prefix="rapiddoc_preview_") as tmp_dir:
        input_path = os.path.join(tmp_dir, "document.docx")
        with open(input_path, "wb") as fh:
            fh.write(docx_bytes)

        try:
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp_dir,
                    input_path,
                ],
                capture_output=True,
                text=True,
                timeout=CONVERSION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice conversion timed out after %ss", CONVERSION_TIMEOUT_SECONDS)
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

        pdf_path = os.path.join(tmp_dir, "document.pdf")
        if result.returncode != 0 or not os.path.exists(pdf_path):
            logger.error(
                "LibreOffice conversion failed (code=%s). stdout=%s stderr=%s",
                result.returncode, result.stdout, result.stderr,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to convert the document to PDF for preview.",
            )

        with open(pdf_path, "rb") as fh:
            return fh.read()
