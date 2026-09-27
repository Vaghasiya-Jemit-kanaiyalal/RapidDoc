import os
import sys

# Ensure the repo root's parent is importable so the `RapidDoc.backend.app.*`
# package imports resolve no matter which directory the server is started from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from RapidDoc.backend.app.config import settings
from RapidDoc.backend.app.routers import auth, documents
from RapidDoc.backend.app.routers import preview
from RapidDoc.backend.app.routers import ai as ai_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Preload the four local brain models in the background so AI chat/search
    commands are fast on first use instead of paying a multi-second model load.

    warm_start_brains() only spawns daemon threads and returns immediately, so
    the server is never blocked by it. A failure here must not stop the API
    from booting - every brain also loads lazily on first use."""
    try:
        from RapidDoc.backend.app.services.local_models import warm_start_brains
        warm_start_brains()
    except Exception as exc:
        logger.error("Brain warm start could not be started: %s", exc)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for RapidDoc AI-Powered Document Intelligence & Editing",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for React Vite local server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(preview.router)
app.include_router(ai_router.router)


# Custom exception handler for standard ConnectionError (database down, etc.)
@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError):
    logger.error("Database connection exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )

# Generic exception handler for unexpected crashes
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error occurred: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )

@app.get("/")
async def root():
    # Simple endpoint to check if backend is running
    from RapidDoc.backend.app.database import db_conn
    db_status = "connected" if db_conn.is_connected() else "disconnected"
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "database_status": db_status
    }

if __name__ == "__main__":
    uvicorn.run("RapidDoc.backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
