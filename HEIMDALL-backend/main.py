"""
HEIMDALL — AI-Powered Identity & Document Screening
SIH 2026 · Problem Statement 26188
Ministry of Home Affairs · Sashastra Seema Bal (SSB)

Run: uvicorn main:app --reload --port 8000
"""
import os
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from database.db import init_db
from routers.screening import router as screening_router
from routers.auth import router as auth_router
from routers.blockchain import router as blockchain_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("heimdall")

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
).split(",")


def _warmup_engines():
    """Preload ML models in a background thread so the first request is fast."""
    try:
        from services.ocr_service import _get_reader
        _get_reader()
        logger.info("🔥 OCR engine warmed up.")
    except Exception as e:
        logger.warning(f"OCR warmup failed: {e}")
    try:
        import deepface  # noqa: F401  — preloads TensorFlow
        from deepface import DeepFace
        import numpy as _np
        _blank = _np.zeros((120, 120, 3), dtype="uint8")
        DeepFace.verify(_blank, _blank, model_name="VGG-Face", enforce_detection=False, silent=True)
        logger.info("🔥 Face engine warmed up.")
    except Exception as e:
        logger.warning(f"Face engine warmup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🛡  HEIMDALL starting up — SIH PS 26188")
    await init_db()
    logger.info("✅ Database initialised.")
    threading.Thread(target=_warmup_engines, daemon=True, name="heimdall-warmup").start()
    yield
    logger.info("🛑 HEIMDALL shutting down.")


app = FastAPI(
    title="HEIMDALL",
    description=(
        "AI-Powered Identity & Document Screening System — SIH 2026\n\n"
        "PS 26188 · Ministry of Home Affairs · Sashastra Seema Bal (SSB)\n\n"
        "Evidence-Based Risk Intelligence for Identity Verification"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screening_router)
app.include_router(auth_router)
app.include_router(blockchain_router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


@app.get("/")
async def root():
    return {
        "system":      "HEIMDALL",
        "version":     "1.0.0",
        "description": "AI-Powered Identity & Document Screening — SIH PS 26188",
        "status":      "online",
        "docs":        "/api/docs",
    }
