"""
HEIMDALL — Tampering / Forensic Analysis Service
SIH 2026 · PS 26188

KEY RULES:
- ELA anomalies are indicators, NOT proof of forgery.
- EXIF absence alone contributes ZERO risk points.
- Forensic results use responsible status labels: CLEAN | LOW_ANOMALY | SUSPICIOUS | HIGH_ANOMALY | INCONCLUSIVE
- Metadata flags are classified: editing-software (meaningful) vs absent (informational).
- Never flag "metadata stripped therefore forged".
"""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("heimdall.forensics")


# ── Status levels ─────────────────────────────────────────────────────────────
#  CLEAN        : no significant anomalies
#  LOW_ANOMALY  : minor indicators (common in normal photos)
#  SUSPICIOUS   : meaningful indicators present (review warranted)
#  HIGH_ANOMALY : strong indicators (strong review/escalation)
#  INCONCLUSIVE : analysis could not complete reliably


# ── Demo fixtures ─────────────────────────────────────────────────────────────
DEMO_TAMPERING: dict[str, dict] = {
    "valid_passport": {
        "forensics_available": True,
        "status": "CLEAN",
        "is_suspicious": False,
        "overall_confidence": 4.2,
        "regions": [],
        "metadata_flags": [],
        "metadata_status": "PRESENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": "No significant image forensic anomalies were detected.",
        "demo_mode": True,
    },
    "expired_document": {
        "forensics_available": True,
        "status": "CLEAN",
        "is_suspicious": False,
        "overall_confidence": 6.0,
        "regions": [],
        "metadata_flags": ["Document scan appears older — minor age-related compression artefacts"],
        "metadata_status": "PRESENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": "No significant forensic anomalies. Minor age-related compression artefacts are expected in older scanned documents.",
        "demo_mode": True,
    },
    "tampered_text": {
        "forensics_available": True,
        "status": "SUSPICIOUS",
        "is_suspicious": True,
        "overall_confidence": 72.0,
        "regions": [
            {
                "label": "Text Region — Passport Number",
                "confidence": 76.0,
                "bbox": [0.15, 0.35, 0.40, 0.08],
                "reason": "Localised JPEG compression inconsistency in passport number region. Compression level differs from surrounding document background, which may indicate text replacement.",
            },
            {
                "label": "Text Region — Date of Birth",
                "confidence": 68.0,
                "bbox": [0.15, 0.48, 0.35, 0.07],
                "reason": "Local noise pattern is inconsistent with surrounding document area. Possible image layer editing.",
            },
        ],
        "metadata_flags": [
            "Image editing software detected in EXIF: Adobe Photoshop",
            "Image modification timestamp post-dates expected document issuance",
        ],
        "metadata_status": "PRESENT_WITH_ANOMALIES",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": (
            "Image forensic analysis detected indicators potentially consistent with document manipulation. "
            "Localised compression anomalies were found near text fields. "
            "Additionally, image metadata indicates editing software was used. "
            "These are indicators for review — they can also arise from legitimate image processing. "
            "Human review is required."
        ),
        "demo_mode": True,
    },
    "face_mismatch": {
        "forensics_available": True,
        "status": "CLEAN",
        "is_suspicious": False,
        "overall_confidence": 5.0,
        "regions": [],
        "metadata_flags": [],
        "metadata_status": "PRESENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": "No significant image forensic anomalies. Document image appears unaltered.",
        "demo_mode": True,
    },
    "multiple_flags": {
        "forensics_available": True,
        "status": "HIGH_ANOMALY",
        "is_suspicious": True,
        "overall_confidence": 88.0,
        "regions": [
            {
                "label": "Photo Region — Portrait Area",
                "confidence": 84.0,
                "bbox": [0.05, 0.15, 0.25, 0.45],
                "reason": "Portrait region shows significant noise discontinuity at boundary. Possible photo replacement.",
            },
            {
                "label": "Stamp/Seal Region",
                "confidence": 79.0,
                "bbox": [0.60, 0.65, 0.30, 0.25],
                "reason": "Official seal region shows edge sharpness inconsistent with surrounding document print quality. Possible digital insertion.",
            },
            {
                "label": "Text Block — Issuing Authority",
                "confidence": 71.0,
                "bbox": [0.10, 0.72, 0.55, 0.06],
                "reason": "Localised compression inconsistency in authority text block. Font characteristics differ from document baseline.",
            },
        ],
        "metadata_flags": [
            "Image editing software detected in EXIF: GIMP",
            "Image resolution inconsistency: different DPI in portrait vs background region",
        ],
        "metadata_status": "PRESENT_WITH_ANOMALIES",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": (
            "Multiple strong forensic anomalies detected across independent image regions: portrait area, "
            "official seal, and authority text block. Image metadata also indicates editing software. "
            "These independent signals in combination significantly increase the probability of document manipulation. "
            "Human investigation is strongly recommended."
        ),
        "demo_mode": True,
    },
    "aadhaar_valid": {
        "forensics_available": True,
        "status": "CLEAN",
        "is_suspicious": False,
        "overall_confidence": 5.1,
        "regions": [],
        "metadata_flags": [],
        "metadata_status": "ABSENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": (
            "No significant forensic anomalies detected. "
            "EXIF metadata is absent, which is common for scanned or photographed documents "
            "and does not indicate tampering."
        ),
        "demo_mode": True,
    },
    "aadhaar_tampered": {
        "forensics_available": True,
        "status": "SUSPICIOUS",
        "is_suspicious": True,
        "overall_confidence": 71.0,
        "regions": [
            {
                "label": "Aadhaar Number Region",
                "confidence": 74.0,
                "bbox": [0.10, 0.58, 0.45, 0.07],
                "reason": "Localised JPEG compression inconsistency around the Aadhaar number field. Possible digit replacement.",
            },
            {
                "label": "Date of Birth Region",
                "confidence": 66.0,
                "bbox": [0.10, 0.42, 0.40, 0.06],
                "reason": "Noise pattern inconsistent with adjacent text in date-of-birth field. Possible image overlay.",
            },
            {
                "label": "QR Code Region",
                "confidence": 78.0,
                "bbox": [0.72, 0.55, 0.22, 0.22],
                "reason": "QR code region shows pixel-level artefacts inconsistent with standard UIDAI QR generation.",
            },
        ],
        "metadata_flags": [
            "Image editing software detected in EXIF: GIMP 2.10",
            "Modification timestamp post-dates expected document issuance",
            "Image DPI (72) is below expected for scanned official documents (300+)",
        ],
        "metadata_status": "PRESENT_WITH_ANOMALIES",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": (
            "Forensic analysis detected localised compression inconsistencies near the Aadhaar number, "
            "date of birth, and QR code regions. Image metadata shows editing software indicators. "
            "These are indicators consistent with possible document alteration. Human review required."
        ),
        "demo_mode": True,
    },
}


# ── Real analysis helpers ─────────────────────────────────────────────────────

def _ela_analysis(image_path: Path) -> tuple[str, float, list[dict]]:
    """
    Error Level Analysis.
    Returns (status, confidence_0_to_100, suspicious_regions).
    confidence here = how confident we are that anomalies exist (NOT a forgery probability).
    """
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return "INCONCLUSIVE", 0.0, []

    h, w = img.shape[:2]
    if w < 50 or h < 50:
        return "INCONCLUSIVE", 0.0, []

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    cv2.imwrite(tmp_path, img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    compressed = cv2.imread(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)

    if compressed is None or img.shape != compressed.shape:
        return "INCONCLUSIVE", 0.0, []

    ela = cv2.absdiff(img, compressed).astype(np.float32)
    ela_amp = np.clip(ela * 10, 0, 255).astype(np.uint8)
    ela_gray = cv2.cvtColor(ela_amp, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(ela_gray, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area  = 0
    regions     = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 600:
            continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        total_area += area
        # Region confidence: how prominent is this anomaly (0-100)
        region_conf = round(min(90, 40 + (area / (w * h)) * 3000), 1)
        regions.append({
            "label": "Image Region Anomaly",
            "confidence": region_conf,
            "bbox": [round(x/w, 3), round(y/h, 3), round(cw/w, 3), round(ch/h, 3)],
            "reason": (
                "ELA analysis detected a localised JPEG compression inconsistency in this region. "
                "Such anomalies can result from image editing, recompression, screenshotting, "
                "or social-media processing. This is one indicator and not proof of forgery."
            ),
        })

    regions.sort(key=lambda r: r["confidence"], reverse=True)
    area_fraction = total_area / (w * h)

    # Map area fraction to status — conservative thresholds
    if area_fraction < 0.01:
        status, conf = "CLEAN",        round(area_fraction * 1000, 1)
    elif area_fraction < 0.05:
        status, conf = "LOW_ANOMALY",  round(20 + area_fraction * 400, 1)
    elif area_fraction < 0.15:
        status, conf = "SUSPICIOUS",   round(40 + area_fraction * 300, 1)
    else:
        status, conf = "HIGH_ANOMALY", min(90.0, round(60 + area_fraction * 200, 1))

    return status, min(90.0, conf), regions[:5]


def _metadata_analysis(image_path: Path) -> tuple[list[str], str]:
    """
    Check image EXIF metadata.
    Returns (flags_list, metadata_status).
    metadata_status: PRESENT | ABSENT | PRESENT_WITH_ANOMALIES

    EXIF absent = informational, NOT suspicious.
    Only editing software / modification timestamp contradictions are meaningful.
    """
    flags = []
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img_obj = Image.open(image_path)
        try:
            exif_data = img_obj._getexif()
        except Exception:
            exif_data = None

        if not exif_data:
            # Absent EXIF = purely informational, zero risk contribution
            return [], "ABSENT"

        exif = {TAGS.get(k, k): v for k, v in exif_data.items()}
        has_anomaly = False

        software = str(exif.get("Software", ""))
        if software and any(kw in software.lower() for kw in
                             ["photoshop", "gimp", "lightroom", "affinity", "pixlr",
                              "paint.net", "photoscape"]):
            flags.append(f"Image editing software detected in EXIF: {software}")
            has_anomaly = True

        # Modification date vs creation date contradiction
        dt_orig = exif.get("DateTimeOriginal", "")
        dt_mod  = exif.get("DateTime", "")
        if dt_orig and dt_mod and dt_orig != dt_mod:
            flags.append(f"Modification timestamp ({dt_mod}) differs from original capture ({dt_orig})")
            has_anomaly = True

        # Low DPI (below 72 is unusual for an official document scan)
        x_res = exif.get("XResolution", None)
        if x_res:
            try:
                dpi = float(x_res)
                if dpi < 72:
                    flags.append(f"Unusually low image resolution: {dpi:.0f} DPI (official scans typically ≥150 DPI)")
            except Exception:
                pass

        status = "PRESENT_WITH_ANOMALIES" if has_anomaly else "PRESENT"
        return flags, status

    except Exception:
        return [], "ABSENT"


# ── Public API ────────────────────────────────────────────────────────────────

def run_tampering(
    image_path: Optional[Path],
    demo_case: Optional[str] = None,
) -> dict:
    """
    Run image forensic analysis.
    Returns structured result with status, regions, metadata, and interpretation.
    """
    # ── Demo mode ─────────────────────────────────────────────────────────────
    if demo_case:
        data = DEMO_TAMPERING.get(demo_case, DEMO_TAMPERING["valid_passport"])
        return {**data, "demo_mode": True}

    # ── No image ──────────────────────────────────────────────────────────────
    if image_path is None:
        return {
            "forensics_available": False,
            "status": "INCONCLUSIVE",
            "is_suspicious": False,
            "overall_confidence": 0.0,
            "regions": [],
            "metadata_flags": [],
            "metadata_status": "ABSENT",
            "analysis_types": {"ela": False, "metadata": False},
            "interpretation": "No image was provided for forensic analysis.",
            "demo_mode": False,
        }

    # ── Try OpenCV ELA ────────────────────────────────────────────────────────
    ela_status     = "INCONCLUSIVE"
    ela_conf       = 0.0
    ela_regions    = []
    ela_available  = False

    try:
        import cv2  # noqa
        ela_status, ela_conf, ela_regions = _ela_analysis(image_path)
        ela_available = True
    except ImportError:
        logger.warning("OpenCV (cv2) not installed — ELA unavailable.")
    except Exception as e:
        logger.warning(f"ELA analysis failed: {e}")

    # ── Metadata analysis ─────────────────────────────────────────────────────
    meta_flags, meta_status = _metadata_analysis(image_path)

    # ── Combine signals ───────────────────────────────────────────────────────
    # Boost confidence slightly if metadata also shows editing software
    editing_meta = any(
        kw in f.lower() for f in meta_flags
        for kw in ["editing software", "photoshop", "gimp"]
    )
    if editing_meta and ela_conf > 0:
        ela_conf = min(90.0, ela_conf + 8)
        if ela_status == "LOW_ANOMALY":
            ela_status = "SUSPICIOUS"

    # Final status
    if not ela_available:
        status = "INCONCLUSIVE"
    else:
        status = ela_status

    is_suspicious = status in ("SUSPICIOUS", "HIGH_ANOMALY")

    # Build interpretation
    if status == "INCONCLUSIVE":
        interpretation = (
            "Image forensic analysis could not complete (OpenCV unavailable). "
            "This module result is inconclusive."
        )
    elif status == "CLEAN":
        interpretation = (
            "No significant image forensic anomalies were detected. "
            "Image compression appears consistent throughout the document."
        )
        if meta_status == "ABSENT":
            interpretation += (
                " EXIF metadata is absent, which is normal for images shared via messaging apps, "
                "uploaded online, or converted from PDF. This alone does not indicate tampering."
            )
    elif status == "LOW_ANOMALY":
        interpretation = (
            f"Minor image compression inconsistencies detected ({ela_conf:.0f}% anomaly confidence). "
            "Such anomalies are common in documents that have been scanned, screenshotted, "
            "resized, or shared via social media. This is a low-risk indicator and does not "
            "by itself indicate document tampering."
        )
    elif status == "SUSPICIOUS":
        interpretation = (
            f"Localised image forensic anomalies detected ({ela_conf:.0f}% confidence). "
            "These indicators may be consistent with image editing, though they can also arise "
            "from JPEG recompression, format conversion, or social-media processing. "
            "This is one signal among several and requires review alongside other evidence."
        )
    else:  # HIGH_ANOMALY
        interpretation = (
            f"Multiple strong image forensic anomalies detected ({ela_conf:.0f}% confidence). "
            "Independent regions show significant compression inconsistencies. "
            "This level of anomaly, particularly across multiple document regions, "
            "warrants careful human review. This is not proof of forgery."
        )

    return {
        "forensics_available": ela_available,
        "status":              status,
        "is_suspicious":       is_suspicious,
        "overall_confidence":  ela_conf,
        "regions":             ela_regions,
        "metadata_flags":      meta_flags,
        "metadata_status":     meta_status,
        "analysis_types":      {"ela": ela_available, "metadata": True},
        "interpretation":      interpretation,
        "demo_mode":           False,
    }
