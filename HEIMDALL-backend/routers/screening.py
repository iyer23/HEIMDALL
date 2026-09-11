"""
HEIMDALL — Screening Router
SIH 2026 · PS 26188

Pipeline: Validate Upload → OCR → Validation → MRZ (if applicable) → Forensics → Face → Risk
ONE canonical result object is created and stored. Frontend and report both use this object.
"""
from __future__ import annotations
import asyncio, uuid, time, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from models.screening import ScreeningRecord
from services.ocr_service        import run_ocr
from services.validation_service import run_validation
from services.mrz_service        import run_mrz, MRZ_APPLICABLE_TYPES
from services.tampering_service  import run_tampering
from services.face_service       import run_face_verification
from services.risk_service       import compute_risk
from services.report_service     import generate_pdf_report
from utils.file_utils            import save_upload, validate_upload, delete_file

router = APIRouter(prefix="/api", tags=["screening"])
logger = logging.getLogger("heimdall.router")


def _pdf_to_image(pdf_path: Path) -> Path:
    """Convert page 1 of a PDF upload to a 200-DPI PNG so OCR/forensics engines can process it."""
    import fitz  # PyMuPDF
    out = pdf_path.with_suffix(".png")
    with fitz.open(str(pdf_path)) as doc:
        pix = doc[0].get_pixmap(dpi=200)
        pix.save(str(out))
    return out


def _build_result(
    screening_id: str,
    demo_case:    Optional[str],
    doc_path:     Optional[Path],
    person_path:  Optional[Path],
    start_ms:     float,
    demo_mode:    bool,
) -> dict:
    """
    Run the complete screening pipeline and return ONE canonical result object.
    This is the single source of truth for frontend, history, and report.
    """
    # ── 1. OCR ────────────────────────────────────────────────────────────────
    ocr = run_ocr(doc_path, demo_case)
    doc_type     = ocr.get("document_type", "unknown")
    doc_type_conf= ocr.get("document_type_confidence", 0.0)

    # ── 2. Field Validation ───────────────────────────────────────────────────
    validation = run_validation(ocr, demo_case)

    # ── 3. MRZ — ONLY for MRZ-applicable document types ──────────────────────
    mrz = run_mrz(ocr, demo_case)

    # ── 4. Image Forensics ────────────────────────────────────────────────────
    tampering = run_tampering(doc_path, demo_case)

    # ── 5. Face Verification ──────────────────────────────────────────────────
    face = run_face_verification(doc_path, person_path, demo_case)

    # ── 6. Evidence Fusion + Risk Score ──────────────────────────────────────
    risk_result = compute_risk(ocr, validation, mrz, tampering, face)

    # Promote nested keys to top-level for easy frontend/report access
    evidence_fusion    = risk_result.pop("evidence_fusion", {"narrative": "", "signals": []})
    analysis_limitations = risk_result.pop("analysis_limitations", [])
    # keep all_factors inside risk for now; factors = risk indicators only

    elapsed = int((time.time() * 1000) - start_ms)

    return {
        "screening_id":             screening_id,
        "timestamp":                datetime.now(timezone.utc).isoformat(),
        "document_type":            doc_type,
        "document_type_confidence": round(doc_type_conf * 100, 1),
        "ocr":                      ocr,
        "validation":               validation,
        "mrz":                      mrz,
        "tampering":                tampering,
        "face_verification":        face,
        "risk":                     risk_result,
        "evidence_fusion":          evidence_fusion,
        "analysis_limitations":     analysis_limitations,
        "processing_time_ms":       elapsed,
        "demo_mode":                demo_mode or bool(demo_case),
    }


# ── POST /api/screening/run ───────────────────────────────────────────────────
@router.post("/screening/run")
async def run_screening(
    background_tasks: BackgroundTasks,
    document:         UploadFile           = File(...),
    person_image:     Optional[UploadFile] = File(None),
    demo_mode:        Optional[str]        = Form("false"),
    demo_case:        Optional[str]        = Form(None),
    db: AsyncSession = Depends(get_db),
):
    start        = time.time() * 1000
    screening_id = f"HM-{uuid.uuid4().hex[:12].upper()}"
    is_demo      = (demo_mode == "true") or bool(demo_case)

    doc_bytes = await document.read()
    err = validate_upload(document.content_type or "image/jpeg", len(doc_bytes))
    if err:
        raise HTTPException(status_code=400, detail=err)

    doc_path    = None
    person_path = None
    try:
        doc_path = await save_upload(
            doc_bytes, document.filename or "document.jpg", subfolder=screening_id
        )
        upload_path = doc_path
        if doc_path.suffix.lower() == ".pdf":
            doc_path = await asyncio.to_thread(_pdf_to_image, doc_path)
        if person_image and person_image.filename:
            p_bytes = await person_image.read()
            perr    = validate_upload(person_image.content_type or "image/jpeg", len(p_bytes))
            if not perr:
                person_path = await save_upload(
                    p_bytes, person_image.filename, subfolder=screening_id
                )

        result = await asyncio.to_thread(
            _build_result, screening_id, demo_case, doc_path, person_path, start, is_demo
        )
        await _persist(db, result)
        background_tasks.add_task(_cleanup, upload_path, doc_path, person_path)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screening pipeline error [{screening_id}]: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Screening pipeline failed. Please try again.")


# ── POST /api/screening/demo ──────────────────────────────────────────────────
@router.post("/screening/demo")
async def run_demo_screening(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    demo_case    = body.get("demo_case", "valid_passport")
    start        = time.time() * 1000
    screening_id = f"HM-{uuid.uuid4().hex[:12].upper()}"
    result       = _build_result(screening_id, demo_case, None, None, start, True)
    await _persist(db, result)
    return result


# ── GET /api/screening/{id} ───────────────────────────────────────────────────
@router.get("/screening/{screening_id}")
async def get_screening(screening_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(ScreeningRecord, screening_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Screening not found")
    data = rec.get_result()
    if not data:
        raise HTTPException(status_code=404, detail="Result data not found")
    return data


# ── GET /api/screenings ───────────────────────────────────────────────────────
@router.get("/screenings")
async def list_screenings(
    limit:    int           = 20,
    offset:   int           = 0,
    decision: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(ScreeningRecord).order_by(ScreeningRecord.timestamp.desc())
    if decision:
        q = q.where(ScreeningRecord.decision == decision)
    total_q = select(func.count()).select_from(ScreeningRecord)
    if decision:
        total_q = total_q.where(ScreeningRecord.decision == decision)

    total = (await db.execute(total_q)).scalar_one()
    rows  = (await db.execute(q.offset(offset).limit(limit))).scalars().all()

    records = [
        {
            "screening_id":       r.screening_id,
            "timestamp":          r.timestamp.isoformat() if r.timestamp else "",
            "document_type":      r.document_type,
            "nationality":        r.nationality,
            "risk_score":         r.risk_score,
            "decision":           r.decision,
            "processing_time_ms": r.processing_time,
            "demo_mode":          r.demo_mode,
        }
        for r in rows
    ]
    return {"records": records, "total": total}


# ── DELETE /api/screening/{id} ────────────────────────────────────────────────
@router.delete("/screening/{screening_id}")
async def delete_screening(screening_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(ScreeningRecord, screening_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(rec)
    await db.commit()
    return {"deleted": True}


# ── GET /api/screening/{id}/report ────────────────────────────────────────────
@router.get("/screening/{screening_id}/report")
async def get_report(screening_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(ScreeningRecord, screening_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Screening not found")
    data = rec.get_result()
    if not data:
        raise HTTPException(status_code=404, detail="No result data found")

    try:
        pdf = generate_pdf_report(data)
    except Exception as e:
        logger.error(f"Report generation failed [{screening_id}]: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Report generation failed.")

    ct = "application/pdf" if pdf[:4] == b"%PDF" else "text/plain"
    return Response(
        content=pdf, media_type=ct,
        headers={
            "Content-Disposition": f'attachment; filename="HEIMDALL_{screening_id}_report.pdf"'
        },
    )


# ── GET /api/analytics ────────────────────────────────────────────────────────
@router.get("/analytics")
async def get_analytics(db: AsyncSession = Depends(get_db)):
    total  = (await db.execute(select(func.count()).select_from(ScreeningRecord))).scalar_one()
    high   = (await db.execute(
        select(func.count()).select_from(ScreeningRecord).where(ScreeningRecord.decision == "HIGH_RISK")
    )).scalar_one()
    review = (await db.execute(
        select(func.count()).select_from(ScreeningRecord).where(ScreeningRecord.decision == "REVIEW_REQUIRED")
    )).scalar_one()
    passed = (await db.execute(
        select(func.count()).select_from(ScreeningRecord).where(ScreeningRecord.decision == "PASS")
    )).scalar_one()
    avg_t  = (await db.execute(
        select(func.avg(ScreeningRecord.processing_time)).select_from(ScreeningRecord)
    )).scalar_one()

    from sqlalchemy import text
    trend_rows = (await db.execute(text(
        "SELECT strftime('%w', timestamp) as dow, COUNT(*) as cnt "
        "FROM screenings GROUP BY dow ORDER BY dow"
    ))).fetchall()
    day_names  = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    day_counts = {str(i): 0 for i in range(7)}
    for row in trend_rows:
        day_counts[str(row[0])] = row[1]

    return {
        "total_screened":         total,
        "high_risk":              high,
        "review_required":        review,
        "passed":                 passed,
        "avg_processing_time_ms": int(avg_t or 0),
        "risk_distribution": [
            {"name": "Passed",    "value": passed, "color": "#356859"},
            {"name": "Review",    "value": review, "color": "#C47A2C"},
            {"name": "High Risk", "value": high,   "color": "#B54848"},
        ],
        "recent_trend": [
            {"date": day_names[i], "count": day_counts[str(i)]} for i in range(7)
        ],
    }


# ── GET /api/health ───────────────────────────────────────────────────────────
@router.get("/health")
async def health_check():
    def has(m: str) -> bool:
        try: __import__(m); return True
        except ImportError: return False
    return {
        "ocr_engine":       has("easyocr"),
        "tampering_engine": has("cv2"),
        "face_engine":      has("deepface"),
        "risk_engine":      True,
        "database":         True,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _persist(db: AsyncSession, result: dict):
    import copy
    from dotenv import dotenv_values
    env = dotenv_values(".env")
    stored = result
    if str(env.get("REDACT_OCR_IN_DB", "false")).lower() == "true":
        # Privacy mode: keep scores/decisions, strip extracted PII before storing.
        stored = copy.deepcopy(result)
        ocr = stored.get("ocr", {})
        for f in ocr.get("fields", []):
            if f.get("value"):
                f["value"] = "[REDACTED]"
        ocr["raw_mrz"] = None
        mrz = stored.get("mrz", {})
        if isinstance(mrz.get("parsed"), dict):
            stored["mrz"]["parsed"] = {k: "[REDACTED]" for k in mrz["parsed"]}

    # ── Blockchain evidence (additive, never blocks/fails the pipeline) ──────
    # Anchors a PII-free SHA-256 hash of the result's integrity fields.
    try:
        from services.blockchain_service import anchor_result
        evidence = await asyncio.to_thread(anchor_result, result)
        stored["blockchain"] = evidence
        result["blockchain"] = evidence
    except Exception as e:
        logger.warning(f"Blockchain anchoring skipped [{result.get('screening_id')}]: {e}")

    nationality = next(
        (f.get("value") for f in result.get("ocr", {}).get("fields", [])
         if f.get("label") in ("Nationality", "Issuing Country") and f.get("value")),
        None,
    )
    rec = ScreeningRecord(
        screening_id    = result["screening_id"],
        document_type   = result["document_type"],
        doc_type_conf   = result.get("document_type_confidence", 0.0),
        nationality     = nationality,
        risk_score      = result["risk"]["score"],
        decision        = result["risk"]["decision"],
        processing_time = result["processing_time_ms"],
        demo_mode       = result["demo_mode"],
    )
    rec.set_result(stored)
    db.add(rec)
    await db.commit()


def _cleanup(*paths):
    for p in paths:
        if p:
            delete_file(Path(p))
