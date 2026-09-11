"""
HEIMDALL — Evidence Fusion Engine & Risk Scoring
SIH 2026 · PS 26188

ARCHITECTURE:
- Additive points with per-category caps.
- risk_score = sum(capped contributions), clamped 0-100.
- WHY FLAGGED comes exclusively from risk_factors[].
- analysis_limitations contains module failures (NOT fraud evidence).
- No double-counting. No random values.

DECISION THRESHOLDS (single source of truth):
  0–24  → PASS
  25–59 → REVIEW_REQUIRED
  60–100→ HIGH_RISK

CATEGORY CAPS:
  OCR quality:          0 pts  (OCR failure = limitation, not risk)
  Document validation:  30 pts (includes expiry — max 14 for expiry alone)
  MRZ integrity:        25 pts
  Image forensics:      25 pts
  Face verification:    40 pts (face mismatch is HIGH_RISK alone)
  Metadata:              5 pts

SAFETY OVERRIDES (force at least REVIEW, never force HIGH_RISK):
  - document_type = unknown → REVIEW
  - OCR unavailable → REVIEW
  - face INCONCLUSIVE when reference photo provided → REVIEW
"""
from __future__ import annotations

# ── Category caps ─────────────────────────────────────────────────────────────
CAP_OCR        =  0   # OCR failures are limitations, not risk
CAP_VALIDATION = 30
CAP_MRZ        = 25
CAP_FORENSICS  = 25
CAP_FACE       = 65   # face mismatch alone = HIGH_RISK (62 pts used)
CAP_METADATA   =  5

# ── Decision thresholds — SINGLE SOURCE OF TRUTH ──────────────────────────────
THRESHOLD_PASS = 24   # 0-24  → PASS
THRESHOLD_HIGH = 59   # 25-59 → REVIEW_REQUIRED, 60+ → HIGH_RISK

MRZ_APPLICABLE_TYPES = {"passport", "visa"}


def _cap(pts: int, maximum: int) -> int:
    return min(max(0, pts), maximum)


def _factor(label: str, points: int, severity: str, description: str,
            is_limitation: bool = False) -> dict:
    """
    Create a risk/limitation entry.
    is_limitation=True → goes in analysis_limitations, not risk_factors.
    """
    return {
        "label":        label,
        "points":       max(0, points),
        "severity":     severity,
        "description":  description,
        "is_limitation": is_limitation,
    }


# ── Module scorers ────────────────────────────────────────────────────────────

def _ocr_contribution(ocr: dict) -> tuple[int, list[dict]]:
    """
    OCR failures are ANALYSIS LIMITATIONS, not fraud evidence.
    CAP = 0 for risk. Low OCR confidence on specific flagged fields = small risk.
    """
    conf      = ocr.get("overall_confidence", 95.0)
    flagged   = sum(1 for f in ocr.get("fields", []) if f.get("flagged"))
    available = ocr.get("ocr_available", True)
    factors: list[dict] = []
    raw = 0

    if not available:
        # NOT a risk factor — goes to limitations
        factors.append(_factor(
            "OCR engine unavailable",
            0, "low",
            "OCR could not extract text from this document. "
            "This is an analysis limitation, not an indicator of fraud.",
            is_limitation=True,
        ))
    elif conf < 50:
        # Very low confidence — minor risk signal (poor quality may hide tampering)
        raw += 4
        factors.append(_factor(
            f"Very low OCR confidence ({conf:.0f}%)",
            4, "low",
            f"OCR confidence {conf:.0f}% — document text is largely unreadable. "
            "This may indicate poor image quality or an unsupported document format. "
            "Low OCR confidence is NOT evidence of fraud.",
        ))
    elif conf < 70:
        raw += 2
        factors.append(_factor(
            f"Low OCR confidence ({conf:.0f}%)",
            2, "low",
            f"OCR confidence {conf:.0f}%. Some fields may be inaccurate. "
            "Consider re-scanning with better lighting or resolution.",
        ))
    else:
        factors.append(_factor("OCR confidence adequate", 0, "low",
                               f"OCR confidence {conf:.0f}% — text extraction quality is acceptable."))

    # Flagged individual fields (low-confidence specific fields after extraction)
    if flagged > 0 and available:
        flagged_pts = _cap(flagged * 3, 6)
        raw += flagged_pts
        factors.append(_factor(
            f"{flagged} low-confidence OCR field(s)",
            flagged_pts, "low",
            "Specific fields show anomalously low extraction confidence. "
            "This may reflect poor print quality in those regions.",
        ))

    pts = _cap(raw, CAP_OCR)
    return pts, factors


def _validation_contribution(validation: dict, doc_type: str) -> tuple[int, list[dict]]:
    """
    Document-specific validation. Max CAP_VALIDATION.
    UNKNOWN doc type → skip field validation (return as limitation).
    Expiry FAIL = up to 14 pts. Other failures = up to 16 pts.
    """
    factors: list[dict] = []
    raw = 0

    # UNKNOWN doc: cannot apply document-specific rules
    if doc_type in ("unknown", "unsupported"):
        factors.append(_factor(
            "Document-specific validation skipped",
            0, "low",
            "Document type could not be determined, so document-specific field validation "
            "was not performed.",
            is_limitation=True,
        ))
        return 0, factors

    failed   = validation.get("failed", 0)
    warnings = validation.get("warnings", 0)
    checks   = validation.get("checks", [])

    # Separate expiry failures from other failures
    def is_expiry(c: dict) -> bool:
        txt = (c.get("check_name","") + c.get("message","")).lower()
        return any(kw in txt for kw in ("expiry","expired","valid until"))

    expiry_failed  = any(c.get("status") == "FAIL"    and is_expiry(c) for c in checks)
    expiry_warning = any(c.get("status") == "WARNING" and is_expiry(c) for c in checks)
    other_failed   = failed   - (1 if expiry_failed else 0)
    other_warnings = warnings - (1 if expiry_warning else 0)

    if expiry_failed:
        pts = 14; raw += pts
        msg = next((c["message"] for c in checks
                    if c.get("status") == "FAIL" and is_expiry(c)), "Document has expired.")
        factors.append(_factor("Document expired", pts, "high",
            f"{msg} An expired document is an operational risk, not necessarily forgery."))
    elif expiry_warning:
        pts = 5; raw += pts
        factors.append(_factor("Document expiring soon", pts, "medium",
            "Document expiry is approaching. Some authorities require ≥6 months validity."))

    if other_failed > 0:
        pts = _cap(other_failed * 10, 16); raw += pts
        factors.append(_factor(
            f"{other_failed} document rule violation(s)", pts, "high",
            "One or more validation rules failed (invalid format, impossible date, "
            "missing required field). These are indicators for review, not proof of forgery."))

    if other_warnings > 0:
        pts = _cap(other_warnings * 4, 8); raw += pts
        factors.append(_factor(
            f"{other_warnings} validation warning(s)", pts, "low",
            "Minor field anomalies (unusual date pattern, low-confidence field, etc.)."))

    if not any(f["points"] > 0 for f in factors):
        factors.append(_factor("All document validation checks passed", 0, "low",
                               "Document format, dates, and required fields are all valid."))

    return _cap(raw, CAP_VALIDATION), factors


def _mrz_contribution(mrz: dict, doc_type: str) -> tuple[int, list[dict]]:
    """Max CAP_MRZ. Only for MRZ-applicable types. 0 pts for non-MRZ docs."""
    factors: list[dict] = []

    if doc_type not in MRZ_APPLICABLE_TYPES:
        lim = doc_type in ("unknown", "unsupported")
        factors.append(_factor(
            "MRZ not applicable" if not lim else "MRZ check skipped (unknown document type)",
            0, "low",
            f"{'Document type ' + repr(doc_type) + ' does not use ICAO MRZ.' if not lim else 'Document type unknown — MRZ check skipped.'}",
            is_limitation=lim,
        ))
        return 0, factors

    is_passport  = doc_type == "passport"
    present      = mrz.get("mrz_present", False)
    status       = mrz.get("status", "")
    checks       = mrz.get("checks", [])
    cross        = mrz.get("cross_validation", [])
    raw = 0

    if not present:
        pts = 18 if is_passport else 6
        raw += pts
        factors.append(_factor(
            "MRZ absent in passport" if is_passport else "MRZ not detected (visa)",
            pts, "high" if is_passport else "medium",
            ("No MRZ detected. Genuine ICAO TD3 passports always contain a two-line MRZ. "
             "Absence is a significant anomaly — may indicate tampering or poor image quality."
             if is_passport else
             "No MRZ detected. Some visa formats include MRZ; absence may be format/quality issue."),
        ))
        return _cap(raw, CAP_MRZ), factors

    failed_chk = [c for c in checks if c.get("status") == "FAIL"]
    if failed_chk:
        pts = _cap(len(failed_chk) * 9, 18); raw += pts
        names = ", ".join(c["check_name"] for c in failed_chk[:3])
        factors.append(_factor(
            f"MRZ checksum failure: {names}", pts, "high",
            "ICAO 9303 check digits failed. A failure means the MRZ data does not match "
            "its stored check digit — indicating possible field alteration after printing."))
    else:
        factors.append(_factor("All MRZ checksums valid", 0, "low",
                               "All ICAO check digits (doc number, DOB, expiry, composite) pass."))

    mismatches = [c for c in cross if not c.get("match", True)]
    if mismatches:
        pts = _cap(len(mismatches) * 6, 12); raw += pts
        fields = ", ".join(m["field"] for m in mismatches[:3])
        factors.append(_factor(
            f"OCR/MRZ mismatch: {fields}", pts, "high",
            "The printed visible text does not match the MRZ machine-readable data. "
            "This may indicate alteration of the printed Visual Inspection Zone."))
    elif cross:
        factors.append(_factor("OCR and MRZ fields consistent", 0, "low",
                               "All compared fields match between visible text and MRZ."))

    return _cap(raw, CAP_MRZ), factors


def _forensics_contribution(tampering: dict) -> tuple[int, list[dict]]:
    """
    Max CAP_FORENSICS. ELA confidence ≠ risk score.
    Responsible wording — forensic anomalies are indicators, not proof.
    Regions are explanatory (0 pts each) to avoid double-counting.
    """
    suspicious  = tampering.get("is_suspicious", False)
    confidence  = tampering.get("overall_confidence", 0.0)
    regions     = tampering.get("regions", [])
    available   = tampering.get("forensics_available", True)
    factors: list[dict] = []
    raw = 0

    if not available:
        factors.append(_factor(
            "Image forensic analysis unavailable", 0, "low",
            "Forensic analysis could not run. This is an analysis limitation.",
            is_limitation=True,
        ))
        return 0, factors

    if suspicious:
        # Conservative mapping: confidence → pts (never direct mapping)
        if confidence >= 80:   pts = 22
        elif confidence >= 65: pts = 16
        elif confidence >= 45: pts = 10
        else:                  pts = 5
        raw += pts
        n = len(regions)
        factors.append(_factor(
            f"Image forensic anomaly ({confidence:.0f}% confidence, {n} region(s))",
            pts, "high" if pts >= 16 else "medium",
            f"Image analysis detected {n} region(s) with potential anomalies. "
            "Such indicators can arise from image editing, JPEG recompression, "
            "screenshotting, scanning, or format conversion. "
            "This is one signal and is NOT proof of document tampering."))
        # Per-region: purely explanatory, 0 pts each (avoid double-counting)
        for r in regions:
            factors.append(_factor(
                f"Flagged region: {r.get('label', 'Region')}",
                0, "medium",
                r.get("reason", "Forensic anomaly in this image region.")))
    else:
        factors.append(_factor("No significant forensic anomalies", 0, "low",
                               "Image integrity analysis found no significant anomalies."))

    return _cap(raw, CAP_FORENSICS), factors


def _metadata_contribution(tampering: dict) -> tuple[int, list[dict]]:
    """
    Max CAP_METADATA. EXIF absence = 0 pts (informational only).
    Only editing-software or genuine contradictions score points.
    """
    meta_flags = tampering.get("metadata_flags", [])
    factors: list[dict] = []
    raw = 0

    editing = [f for f in meta_flags if any(
        kw in f.lower() for kw in ["photoshop","gimp","lightroom","editing software",
                                    "modification timestamp","modification date"])]
    absent  = [f for f in meta_flags if "absent" in f.lower() or "missing" in f.lower()]
    other   = [f for f in meta_flags if f not in editing and f not in absent]

    if editing:
        pts = _cap(len(editing) * 2, CAP_METADATA); raw += pts
        factors.append(_factor("Metadata: editing software detected", pts, "medium",
            "Image metadata references editing software. Indicates the image was processed, "
            "though this alone does not prove malicious intent."))

    if absent:
        factors.append(_factor("Metadata: EXIF absent", 0, "low",
            "No EXIF metadata found. EXIF is routinely removed during upload, scanning, "
            "messaging, or conversion. Absence alone does NOT indicate tampering."))

    if other:
        pts = _cap(len(other), 3); raw += pts
        factors.append(_factor(f"Metadata: {len(other)} other indicator(s)",
                               pts, "low", "; ".join(other[:2])))

    if not meta_flags:
        factors.append(_factor("No metadata anomalies", 0, "low",
                               "No significant metadata indicators found."))

    return _cap(raw, CAP_METADATA), factors


def _face_contribution(face: dict, person_provided: bool) -> tuple[int, list[dict]]:
    """
    Max CAP_FACE (65 pts). Face mismatch alone drives HIGH_RISK (62 pts).
    Unavailable/not-provided = 0 pts AND limitation noted.
    """
    status    = face.get("status") or face.get("decision", "NOT_PROVIDED")
    score_val = face.get("match_score") or 0.0
    doc_face  = face.get("face_detected_document", False)
    available = face.get("face_available", True)
    factors: list[dict] = []
    raw = 0

    if not available or status == "UNAVAILABLE":
        factors.append(_factor(
            "Face verification engine unavailable", 0, "low",
            "The face verification engine could not load or is not installed. "
            "Face comparison was not performed. This is an analysis limitation.",
            is_limitation=True,
        ))
        return 0, factors

    if status == "NOT_PROVIDED" or not person_provided:
        factors.append(_factor(
            "No reference photo provided", 0, "low",
            "No reference photograph was supplied. Face comparison was skipped. "
            "This is not a risk indicator.",
            is_limitation=False,   # informational, not a limitation either
        ))
        return 0, factors

    if not doc_face:
        factors.append(_factor(
            "No face detected in document", 0, "low",
            "No face could be detected in the document image. Face comparison was skipped.",
            is_limitation=True,
        ))
        return 0, factors

    if status in ("INCONCLUSIVE",):
        factors.append(_factor(
            "Face verification inconclusive", 0, "low",
            "Face comparison could not produce a reliable result (image quality, pose, etc.).",
            is_limitation=True,
        ))
        return 0, factors

    if status in ("NO_MATCH", "MISMATCH"):
        pts = 62; raw += pts   # face mismatch alone drives HIGH_RISK
        factors.append(_factor(
            f"Face similarity below match threshold ({score_val:.1f}%)",
            pts, "high",
            f"Face comparison similarity: {score_val:.1f}% — below the configured match threshold. "
            "The presented individual may not match the document photograph. "
            "This is a supporting indicator; human review is required before any consequential action."))
    elif status == "REVIEW":
        pts = 18; raw += pts
        factors.append(_factor(
            f"Face similarity borderline ({score_val:.1f}%)",
            pts, "medium",
            f"Face similarity {score_val:.1f}% is near the review boundary. "
            "Manual officer comparison is recommended."))
    else:
        factors.append(_factor(
            f"Face similarity above threshold ({score_val:.1f}%)", 0, "low",
            f"Face similarity {score_val:.1f}% is above the configured match threshold. "
            "Face similarity is a supporting indicator, not independent proof of identity."))

    if face.get("multiple_faces_person"):
        pts = 4; raw += pts
        factors.append(_factor("Multiple faces in reference photo", pts, "low",
            "More than one face detected in the reference photo. Comparison reliability reduced."))

    return _cap(raw, CAP_FACE), factors


# ── Safety overrides ──────────────────────────────────────────────────────────

def _apply_overrides(
    score: int, decision: str,
    ocr: dict, doc_type: str,
    face: dict, person_provided: bool,
    validation: dict,
) -> tuple[str, str | None]:
    """
    Force at minimum REVIEW for incomplete/uncertain analysis or expired docs.
    NEVER force HIGH_RISK via override — only via score.
    """
    if decision in ("PASS", "REVIEW_REQUIRED"):
        # Expired documents are HARD-BLOCKED (cannot be accepted, regardless of other checks)
        checks = validation.get("checks", [])
        is_expired = any(
            c.get("status") == "FAIL" and
            any(kw in (c.get("check_name","") + c.get("message","")).lower()
                for kw in ("expiry","expired","valid until"))
            for c in checks
        )
        if is_expired:
            return "REVIEW_REQUIRED", (
                "Document is EXPIRED — flagged for manual review. An expired document should "
                "not be accepted for entry, but expiry is an operational issue, not proof of forgery. "
                "Applicant must present a valid document.")

        if doc_type in ("unknown", "unsupported"):
            return "REVIEW_REQUIRED", (
                "Document type could not be identified reliably. "
                "Automated field checks cannot be applied to an unknown document type.")

        if not ocr.get("ocr_available", True):
            return "REVIEW_REQUIRED", (
                "OCR was unavailable so field extraction did not succeed. "
                "Analysis is incomplete and manual review is required.")

        face_status = face.get("status") or face.get("decision", "")
        if person_provided and face_status == "INCONCLUSIVE":
            return "REVIEW_REQUIRED", (
                "Face verification was inconclusive despite a reference photo being supplied. "
                "Manual face comparison by an officer is required.")

    return decision, None


# ── Public API ────────────────────────────────────────────────────────────────

def compute_risk(
    ocr: dict,
    validation: dict,
    mrz: dict,
    tampering: dict,
    face: dict,
) -> dict:
    """
    Evidence Fusion Engine — single source of truth for all risk/decision output.
    Frontend, PDF, and history all use this same result dict.
    """
    doc_type        = ocr.get("document_type", "unknown")
    person_provided = (
        face.get("face_detected_document", False) or
        face.get("face_detected_person", False) or
        face.get("status") not in (None, "NOT_PROVIDED")
    )

    # ── Compute contributions ─────────────────────────────────────────────────
    ocr_pts,  ocr_facs  = _ocr_contribution(ocr)
    val_pts,  val_facs  = _validation_contribution(validation, doc_type)
    mrz_pts,  mrz_facs  = _mrz_contribution(mrz, doc_type)
    for_pts,  for_facs  = _forensics_contribution(tampering)
    meta_pts, meta_facs = _metadata_contribution(tampering)
    face_pts, face_facs = _face_contribution(face, person_provided)

    # ── Score ─────────────────────────────────────────────────────────────────
    raw_score = ocr_pts + val_pts + mrz_pts + for_pts + meta_pts + face_pts
    score = min(100, max(0, raw_score))

    # ── Base decision ─────────────────────────────────────────────────────────
    if score <= THRESHOLD_PASS:
        base = "PASS"
    elif score <= THRESHOLD_HIGH:
        base = "REVIEW_REQUIRED"
    else:
        base = "HIGH_RISK"

    decision, override_reason = _apply_overrides(
        score, base, ocr, doc_type, face, person_provided, validation)
    color = {
        "PASS":            "#16a34a",
        "REVIEW_REQUIRED": "#ca8a04",
        "HIGH_RISK":       "#dc2626",
    }.get(decision, "#ca8a04")

    # ── Separate risk factors from analysis limitations ───────────────────────
    all_factors  = ocr_facs + val_facs + mrz_facs + for_facs + meta_facs + face_facs
    risk_factors = [f for f in all_factors if not f.get("is_limitation", False)]
    limitations  = [f for f in all_factors if f.get("is_limitation", False)]

    # ── Breakdown ─────────────────────────────────────────────────────────────
    breakdown = {
        "ocr":        {"points": ocr_pts,  "cap": CAP_OCR},
        "validation": {"points": val_pts,  "cap": CAP_VALIDATION},
        "mrz":        {"points": mrz_pts,  "cap": CAP_MRZ},
        "forensics":  {"points": for_pts,  "cap": CAP_FORENSICS},
        "metadata":   {"points": meta_pts, "cap": CAP_METADATA},
        "face":       {"points": face_pts, "cap": CAP_FACE},
        "total":      score,  # clamped final score
        "raw_total":  raw_score,  # pre-clamp sum
    }

    # ── Verify: breakdown sum must equal UNCLAMPED score (clamping is expected) ─
    bd_sum = ocr_pts + val_pts + mrz_pts + for_pts + meta_pts + face_pts
    # Note: score = min(100, bd_sum) — clamping is valid, not a bug

    # ── Narrative (WHY FLAGGED) ───────────────────────────────────────────────
    narrative = _build_narrative(score, decision, override_reason, risk_factors, limitations)

    # ── Analysis completeness ─────────────────────────────────────────────────
    has_limitations = len(limitations) > 0
    completeness = "INCOMPLETE" if has_limitations else "COMPLETE"

    # ── Signals for UI WHY-FLAGGED panel ─────────────────────────────────────
    signals = [
        {
            "label":        f["label"],
            "module":       _module_for(f["label"]),
            "contribution": f["points"],
            "reason":       f["description"],
            "ok":           f["points"] == 0,
            "is_limitation": f.get("is_limitation", False),
        }
        for f in all_factors
    ]

    return {
        "score":             score,
        "decision":          decision,
        "color":             color,
        "factors":           risk_factors,        # risk indicators only
        "analysis_limitations": limitations,      # module failures / missing inputs
        "all_factors":       all_factors,         # combined (for detailed views)
        "breakdown":         breakdown,
        "override_reason":   override_reason,
        "completeness":      completeness,
        "evidence_fusion": {
            "narrative": narrative,
            "signals":   signals,
        },
    }


def _build_narrative(
    score: int, decision: str, override_reason: str | None,
    risk_factors: list[dict], limitations: list[dict],
) -> str:
    if override_reason:
        lim_labels = [l["label"] for l in limitations[:3]]
        suffix = (f" Analysis limitations: {'; '.join(lim_labels)}." if lim_labels else "")
        return f"Automated screening decision overridden to REVIEW. {override_reason}{suffix}"

    positive = [f for f in risk_factors if f["points"] > 0]

    if not positive:
        lim_note = ""
        if limitations:
            lim_labels = [l["label"] for l in limitations[:2]]
            lim_note = f" Note: analysis limitations — {'; '.join(lim_labels)}."
        return ("No significant risk indicators were detected. "
                "Validation rules passed, forensics found no anomalies, "
                "and MRZ checks are valid where applicable." + lim_note)

    sources = {}
    for f in positive:
        ll = f["label"].lower()
        if "mrz" in ll:                              sources["MRZ"] = sources.get("MRZ",0) + f["points"]
        elif "forensic" in ll or "anomaly" in ll:    sources["forensics"] = sources.get("forensics",0) + f["points"]
        elif "expired" in ll or "expir" in ll:       sources["expiry"] = sources.get("expiry",0) + f["points"]
        elif "validation" in ll or "rule" in ll:     sources["validation"] = sources.get("validation",0) + f["points"]
        elif "face" in ll:                           sources["face"] = sources.get("face",0) + f["points"]

    desc_map = {
        "MRZ":        "MRZ integrity checks raised concerns",
        "forensics":  "image forensic analysis detected indicators of possible manipulation",
        "expiry":     "the document has expired",
        "validation": "document validation rules were violated",
        "face":       "face comparison similarity was below the configured threshold",
    }
    reasons = [desc_map[k] for k in sources if k in desc_map]

    if not reasons:
        return f"Risk score {score}/100 — review based on combined module analysis."

    n = len(reasons)
    if n >= 3:
        prefix = "HEIMDALL flagged this document because multiple independent modules produced corroborating evidence: "
        body   = "; ".join(reasons[:-1]) + "; and " + reasons[-1] + "."
        close  = " Agreement between independent modules increases assessment reliability."
    elif n == 2:
        prefix = "Two independent verification modules raised concerns: "
        body   = reasons[0] + "; and " + reasons[1] + "."
        close  = " Human officer review is required before any consequential decision."
    else:
        prefix = "The following concern was identified: "
        body   = reasons[0] + "."
        close  = " Human officer review is required before any consequential decision."

    lim_note = ""
    if limitations:
        lim_labels = [l["label"] for l in limitations[:2]]
        lim_note = f" Note: {'; '.join(lim_labels)} (analysis limitation, not a risk indicator)."

    return prefix + body + close + lim_note


def _module_for(label: str) -> str:
    ll = label.lower()
    if "ocr" in ll:                              return "OCR"
    if "mrz" in ll:                              return "MRZ"
    if "forensic" in ll or "region" in ll or "anomaly" in ll: return "Forensics"
    if "metadata" in ll:                         return "Metadata"
    if "face" in ll:                             return "Face"
    return "Validation"
