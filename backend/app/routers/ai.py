import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from RapidDoc.backend.app.models import RewriteRequest
from RapidDoc.backend.app.routers.auth import get_current_user
from RapidDoc.backend.app.services.gemini_service import (
    brains_health, generate_mcqs, rewrite_text, summarize_document
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/brains")
async def ai_brains_status(current_user: dict = Depends(get_current_user)):
    """Which of the four local brain models are loaded and ready."""
    return {"status": "success", **brains_health()}


@router.post("/summarize")
async def ai_summarize_endpoint(
    request: RewriteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Summarize arbitrary text with the local BART brain (Gemini fallback)."""
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A 'text' value is required to summarize.",
        )
    try:
        result = await run_in_threadpool(summarize_document, text, request.instruction)
        if not result.get("summary"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message") or "No summarization engine is available.",
            )
        return {"status": "success", "characters": len(text), **result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in AI summarize endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while summarizing text.",
        )


@router.post("/generate-mcq")
async def ai_generate_mcq_endpoint(
    request: RewriteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate multiple-choice questions from arbitrary text."""
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A 'text' value is required to generate questions.",
        )
    try:
        count = 5
        if request.instruction:
            digits = "".join(ch if ch.isdigit() else " " for ch in request.instruction).split()
            if digits:
                count = int(digits[0])
        result = await run_in_threadpool(generate_mcqs, text, count)
        if not result.get("questions"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message") or "No question-generation engine is available.",
            )
        return {"status": "success", "characters": len(text), **result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in AI generate-mcq endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating questions.",
        )


@router.post("/rewrite")
async def ai_rewrite_endpoint(
    request: RewriteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Rewrite a piece of text using the local T5 brain (Gemini fallback)."""
    if not (request.text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A 'text' value is required to rewrite.",
        )
    try:
        result = await run_in_threadpool(rewrite_text, request.instruction, request.text)
        return {
            "status": "success",
            "original_text": request.text.strip(),
            **result,
        }
    except Exception as exc:
        logger.error("Error in AI rewrite endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while rewriting text.",
        )