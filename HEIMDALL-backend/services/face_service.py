"""
HEIMDALL — Face Verification Service
SIH 2026 · PS 26188

KEY RULES:
- If face model unavailable → status = INCONCLUSIVE (zero risk, not invented score).
- If no reference photo → status = NOT_PROVIDED (zero risk).
- Face similarity is a supporting indicator, NOT identity proof.
- Thresholds must be defined and documented.
- MATCH / POSSIBLE_MATCH / REVIEW / MISMATCH / INCONCLUSIVE / NOT_PROVIDED / UNAVAILABLE
- Never: "96.8% identity confirmed."

DeepFace VGG-Face cosine distance:
  distance 0.0 = identical embeddings
  distance 1.0 = maximally different
  Empirical thresholds for VGG-Face cosine:
    < 0.40  → MATCH         (high similarity)
    0.40-0.55 → POSSIBLE_MATCH / REVIEW (borderline)
    > 0.55  → MISMATCH      (low similarity)
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("heimdall.face")

# ── Configurable thresholds ───────────────────────────────────────────────────
# VGG-Face cosine distance (lower = more similar)
FACE_MATCH_THRESHOLD   = 0.40   # <= 0.40 → MATCH
FACE_REVIEW_THRESHOLD  = 0.55   # <= 0.55 → POSSIBLE_MATCH/REVIEW
# Above 0.55 → MISMATCH

# Convert to similarity percentage for display:
#   similarity = max(0, (1 - distance)) * 100


# ── Demo fixtures ─────────────────────────────────────────────────────────────
DEMO_FACE: dict[str, dict] = {
    "aadhaar_valid": {
        "status":                 "MATCH",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            94.7,
        "distance":               0.28,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "good",
        "message": (
            "Face comparison similarity: 94.7% (distance 0.28 < threshold 0.40). "
            "Similarity is above the configured match threshold. "
            "Face similarity is a supporting indicator and does not independently prove identity."
        ),
        "demo_mode": True,
    },
    "aadhaar_tampered": {
        "status":                 "REVIEW",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            71.5,
        "distance":               0.49,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "fair",
        "message": (
            "Face comparison similarity: 71.5% (distance 0.49, between match threshold 0.40 and "
            "review threshold 0.55). Result is borderline. Manual officer comparison is recommended. "
            "Combined with document tampering indicators, review is strongly advised."
        ),
        "demo_mode": True,
    },
    "valid_passport": {
        "status":                 "MATCH",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            92.3,
        "distance":               0.31,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "good",
        "message": (
            "Face comparison similarity: 92.3% (distance 0.31 < threshold 0.40). "
            "Similarity is above the configured match threshold. "
            "Face similarity is a supporting indicator and does not independently prove identity."
        ),
        "demo_mode": True,
    },
    "expired_document": {
        "status":                 "MATCH",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            89.4,
        "distance":               0.37,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "good",
        "message": (
            "Face comparison similarity: 89.4% (distance 0.37 < threshold 0.40). "
            "Above match threshold. Note: document is expired. "
            "Face similarity is a supporting indicator only."
        ),
        "demo_mode": True,
    },
    "tampered_text": {
        "status":                 "REVIEW",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            76.8,
        "distance":               0.46,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "fair",
        "message": (
            "Face comparison similarity: 76.8% (distance 0.46, between match threshold 0.40 and "
            "review threshold 0.55). Borderline result. "
            "Combined with document forensic indicators, manual officer review is required."
        ),
        "demo_mode": True,
    },
    "face_mismatch": {
        "status":                 "MISMATCH",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            38.2,
        "distance":               0.72,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "good",
        "message": (
            "Face comparison similarity: 38.2% (distance 0.72 > review threshold 0.55). "
            "Similarity is below the configured review threshold. "
            "The presented individual does not appear to closely match the document photo. "
            "Human officer comparison is required before any consequential decision."
        ),
        "demo_mode": True,
    },
    "multiple_flags": {
        "status":                 "MISMATCH",
        "face_available":         True,
        "face_detected_document": True,
        "face_detected_person":   True,
        "multiple_faces_document":False,
        "multiple_faces_person":  False,
        "match_score":            24.1,
        "distance":               0.88,
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "poor",
        "message": (
            "Face comparison similarity: 24.1% (distance 0.88 >> review threshold 0.55). "
            "Very low similarity. "
            "The presented individual does not appear to match the document photo. "
            "Human officer comparison is required."
        ),
        "demo_mode": True,
    },
}

_NO_PERSON = {
    "status":                 "NOT_PROVIDED",
    "face_available":         True,
    "face_detected_document": False,
    "face_detected_person":   False,
    "multiple_faces_document":False,
    "multiple_faces_person":  False,
    "match_score":            None,
    "distance":               None,
    "threshold_used":         FACE_MATCH_THRESHOLD,
    "image_quality":          "N/A",
    "message": "No reference photograph was provided. Face comparison was not performed.",
}

_UNAVAILABLE = {
    "status":                 "UNAVAILABLE",
    "face_available":         False,
    "face_detected_document": False,
    "face_detected_person":   False,
    "multiple_faces_document":False,
    "multiple_faces_person":  False,
    "match_score":            None,
    "distance":               None,
    "threshold_used":         FACE_MATCH_THRESHOLD,
    "image_quality":          "N/A",
    "message": (
        "Face verification engine (DeepFace) is not installed or could not load. "
        "Face comparison is unavailable. Result is inconclusive."
    ),
}


def _distance_to_status(distance: float) -> str:
    if distance <= FACE_MATCH_THRESHOLD:
        return "MATCH"
    if distance <= FACE_REVIEW_THRESHOLD:
        return "REVIEW"
    return "MISMATCH"


def _distance_to_score(distance: float) -> float:
    """Convert cosine distance to a similarity percentage for display."""
    return round(max(0.0, min(100.0, (1.0 - distance) * 100)), 1)


def _weights_ready() -> bool:
    """True when the VGG-Face weights file is fully downloaded."""
    import os
    wdir = os.path.join(os.path.expanduser("~"), ".deepface", "weights")
    try:
        return any(
            f == "vgg_face_weights.h5" and os.path.getsize(os.path.join(wdir, f)) > 10_000_000
            for f in os.listdir(wdir)
        )
    except OSError:
        return False


def _run_deepface(doc_path: Path, person_path: Path) -> dict:
    if not _weights_ready():
        # Weights still downloading in the background — fail fast, never stall a request.
        return {
            **_UNAVAILABLE,
            "message": (
                "Face verification model is still loading. "
                "Face comparison was skipped for this screening. Result is inconclusive."
            ),
        }

    from deepface import DeepFace

    # Detect faces explicitly first: this both avoids duplicate detection work
    # (faster) and prevents an undetected face from producing a garbage
    # embedding that would show up as a false MISMATCH score.
    doc_faces = DeepFace.extract_faces(
        img_path=str(doc_path), detector_backend="opencv", enforce_detection=False,
    )
    person_faces = DeepFace.extract_faces(
        img_path=str(person_path), detector_backend="opencv", enforce_detection=False,
    )
    doc_faces    = [f for f in doc_faces    if f.get("confidence", 0) >= 0.20]
    person_faces = [f for f in person_faces if f.get("confidence", 0) >= 0.20]

    if not doc_faces or not person_faces:
        missing = []
        if not doc_faces:    missing.append("the document photo")
        if not person_faces: missing.append("the reference photograph")
        return {
            **_UNAVAILABLE,
            "status": "INCONCLUSIVE",
            "face_detected_document": bool(doc_faces),
            "face_detected_person":   bool(person_faces),
            "multiple_faces_document": len(doc_faces) > 1,
            "multiple_faces_person":   len(person_faces) > 1,
            "image_quality": "poor",
            "message": (
                f"No face could be reliably detected in {' or '.join(missing)}. "
                "Face comparison was not performed. Result is inconclusive — "
                "please upload clearer images. Manual officer comparison is required."
            ),
        }

    # Multi-face images: compare the most confidently detected face of each.
    doc_crop    = max(doc_faces,    key=lambda f: f.get("confidence", 0))["face"]
    person_crop = max(person_faces, key=lambda f: f.get("confidence", 0))["face"]

    result = DeepFace.verify(
        img1_path=doc_crop,
        img2_path=person_crop,
        model_name="VGG-Face",
        enforce_detection=False,
        distance_metric="cosine",
    )
    distance = float(result.get("distance", 1.0))
    status   = _distance_to_status(distance)
    score    = _distance_to_score(distance)

    doc_face     = True
    person_face  = True

    if status == "MATCH":
        msg = (
            f"Face comparison similarity: {score:.1f}% (distance {distance:.2f} ≤ threshold {FACE_MATCH_THRESHOLD}). "
            "Similarity is above the configured match threshold. "
            "Face similarity is a supporting indicator and does not independently prove identity."
        )
    elif status == "REVIEW":
        msg = (
            f"Face comparison similarity: {score:.1f}% (distance {distance:.2f}, between "
            f"match threshold {FACE_MATCH_THRESHOLD} and review threshold {FACE_REVIEW_THRESHOLD}). "
            "Result is borderline. Manual officer comparison is recommended."
        )
    else:
        msg = (
            f"Face comparison similarity: {score:.1f}% (distance {distance:.2f} > "
            f"review threshold {FACE_REVIEW_THRESHOLD}). "
            "Similarity is below the configured review threshold. "
            "The presented individual does not appear to closely match the document photo. "
            "Human officer comparison is required before any consequential decision."
        )

    return {
        "status":                 status,
        "face_available":         True,
        "face_detected_document": doc_face,
        "face_detected_person":   person_face,
        "multiple_faces_document": len(doc_faces) > 1,
        "multiple_faces_person":   len(person_faces) > 1,
        "match_score":            score,
        "distance":               round(distance, 4),
        "threshold_used":         FACE_MATCH_THRESHOLD,
        "image_quality":          "good",
        "message":                msg,
        "demo_mode":              False,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def run_face_verification(
    doc_path: Optional[Path],
    person_path: Optional[Path],
    demo_case: Optional[str] = None,
) -> dict:
    """
    Run face verification.

    - demo_case set → return labelled synthetic fixture.
    - No person_path → NOT_PROVIDED (zero risk, not penalised).
    - DeepFace unavailable → UNAVAILABLE (zero risk, never invent score).
    - DeepFace fails → INCONCLUSIVE (zero risk, never invent score).
    """
    if demo_case:
        data = DEMO_FACE.get(demo_case, DEMO_FACE["valid_passport"])
        return {**data, "demo_mode": True}

    if not person_path or not person_path.exists():
        return {**_NO_PERSON, "demo_mode": False}

    # Check DeepFace is available
    try:
        import deepface  # noqa
    except ImportError:
        logger.warning("DeepFace not installed — face verification unavailable.")
        return {**_UNAVAILABLE, "demo_mode": False}

    try:
        return _run_deepface(doc_path, person_path)
    except Exception as e:
        logger.warning(f"DeepFace verification failed: {e}")
        return {
            **_UNAVAILABLE,
            "status":  "INCONCLUSIVE",
            "message": (
                f"Face verification failed: {e}. "
                "Result is inconclusive. Manual face comparison is required."
            ),
            "demo_mode": False,
        }


# ── Boot-time warmup ──────────────────────────────────────────────────────────
# Building the VGG-Face model takes ~15-30 s on CPU. Do it once in a background
# thread at server startup so the first real verification is fast. DeepFace
# caches the built model in-process, so later calls reuse it.

def _warmup() -> None:
    import time
    for _ in range(120):  # wait up to 10 min for the weights download to finish
        if _weights_ready():
            break
        time.sleep(5)
    else:
        return
    try:
        from deepface import DeepFace
        DeepFace.build_model("VGG-Face")
        logger.info("Face verification engine warmed up (VGG-Face ready).")
    except Exception as e:
        logger.warning(f"Face engine warmup failed (will build on first request): {e}")

try:
    import threading as _threading
    _threading.Thread(target=_warmup, name="face-warmup", daemon=True).start()
except Exception:
    pass
