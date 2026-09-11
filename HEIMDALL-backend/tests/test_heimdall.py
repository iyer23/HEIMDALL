"""
HEIMDALL — Backend Test Suite
SIH 2026 · PS 26188

Tests every bug fix, invariant, and demo case.
Run: python -m pytest tests/test_heimdall.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from services.ocr_service        import run_ocr, DEMO_OCR
from services.validation_service import run_validation, DEMO_VALIDATION
from services.mrz_service        import run_mrz, DEMO_MRZ, MRZ_APPLICABLE_TYPES
from services.tampering_service  import run_tampering, DEMO_TAMPERING
from services.face_service       import run_face_verification, DEMO_FACE
from services.risk_service       import compute_risk, THRESHOLD_PASS, THRESHOLD_HIGH, CAP_OCR, CAP_VALIDATION, CAP_MRZ, CAP_FORENSICS, CAP_FACE, CAP_METADATA

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _pipeline(demo_case: str) -> dict:
    ocr  = run_ocr(None, demo_case)
    val  = run_validation(ocr, demo_case)
    mrz  = run_mrz(ocr, demo_case)
    tamp = run_tampering(None, demo_case)
    face = run_face_verification(None, None, demo_case)
    risk = compute_risk(ocr, val, mrz, tamp, face)
    return {"ocr": ocr, "val": val, "mrz": mrz, "tamp": tamp, "face": face, "risk": risk}


# ─────────────────────────────────────────────────────────────────────────────
# BUG 1 — Aadhaar must NOT be classified as Passport
# ─────────────────────────────────────────────────────────────────────────────

def test_aadhaar_not_classified_as_passport():
    ocr = run_ocr(None, "aadhaar_valid")
    assert ocr["document_type"] == "national_id", \
        f"Aadhaar classified as {ocr['document_type']}, expected national_id"


def test_aadhaar_tampered_not_classified_as_passport():
    ocr = run_ocr(None, "aadhaar_tampered")
    assert ocr["document_type"] == "national_id"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 2 — MRZ must NOT run on Aadhaar
# ─────────────────────────────────────────────────────────────────────────────

def test_aadhaar_mrz_not_applicable():
    mrz = run_mrz(run_ocr(None, "aadhaar_valid"), "aadhaar_valid")
    assert mrz["status"] == "NOT_APPLICABLE", f"Got {mrz['status']}"
    assert mrz["mrz_present"] is False


def test_aadhaar_tampered_mrz_not_applicable():
    mrz = run_mrz(run_ocr(None, "aadhaar_tampered"), "aadhaar_tampered")
    assert mrz["status"] == "NOT_APPLICABLE"


def test_aadhaar_mrz_contributes_zero_risk():
    r = _pipeline("aadhaar_valid")
    mrz_factors = [f for f in r["risk"]["factors"]
                   if "mrz" in f["label"].lower() and f["points"] > 0]
    assert len(mrz_factors) == 0, f"Aadhaar has non-zero MRZ risk: {mrz_factors}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 3+4 — MRZ internal consistency (never contradict itself)
# ─────────────────────────────────────────────────────────────────────────────

def test_mrz_valid_status_means_all_checksums_pass():
    mrz = run_mrz(run_ocr(None, "valid_passport"), "valid_passport")
    if mrz["status"] == "VALID":
        for chk in mrz.get("checks", []):
            assert chk["status"] != "FAIL", \
                f"Status=VALID but check '{chk['check_name']}' is FAIL"
        assert mrz["checksums_valid"] is True


def test_mrz_invalid_status_means_at_least_one_checksum_fails():
    # Use tampered_text which has no MRZ → NOT_DETECTED, checksum_valid=False
    mrz = run_mrz(run_ocr(None, "tampered_text"), "tampered_text")
    assert mrz["status"] in ("NOT_DETECTED", "INVALID", "PARTIAL", "UNREADABLE")
    if mrz["status"] in ("INVALID", "PARTIAL"):
        failed = [c for c in mrz.get("checks", []) if c["status"] == "FAIL"]
        assert len(failed) > 0, "Status INVALID/PARTIAL but no FAIL checks"


def test_mrz_no_simultaneous_valid_and_checksum_fail():
    """Never simultaneously claim 'all checksums valid' AND have a FAIL check."""
    for case in DEMO_MRZ:
        mrz = DEMO_MRZ[case]
        if mrz.get("checksums_valid") is True:
            failed = [c for c in mrz.get("checks", []) if c.get("status") == "FAIL"]
            assert len(failed) == 0, \
                f"Case {case}: checksums_valid=True but check(s) are FAIL: {[c['check_name'] for c in failed]}"
        if mrz.get("checksums_valid") is False and mrz.get("mrz_present") is True:
            # If present and checksums invalid, there should be at least one FAIL
            checks = mrz.get("checks", [])
            if checks:
                failed = [c for c in checks if c.get("status") == "FAIL"]
                assert len(failed) > 0, \
                    f"Case {case}: checksums_valid=False and present=True but no FAIL checks"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 5 — Risk score must match breakdown
# ─────────────────────────────────────────────────────────────────────────────

def test_risk_score_matches_breakdown_all_cases():
    for case in ["valid_passport","expired_document","tampered_text",
                 "face_mismatch","multiple_flags","aadhaar_valid","aadhaar_tampered"]:
        r    = _pipeline(case)
        risk = r["risk"]
        score = risk["score"]
        bd    = risk.get("breakdown", {})
        if bd:
            computed = sum(v["points"] for k, v in bd.items() if k != "total")
            assert abs(computed - score) <= 1, \
                f"Case {case}: breakdown sum {computed} != score {score}"


def test_risk_score_always_in_0_100():
    for case in ["valid_passport","expired_document","tampered_text",
                 "face_mismatch","multiple_flags","aadhaar_valid","aadhaar_tampered"]:
        r = _pipeline(case)
        s = r["risk"]["score"]
        assert 0 <= s <= 100, f"Case {case}: score {s} out of range"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 6 — WHY FLAGGED must not say "all checks passed" when evidence exists
# ─────────────────────────────────────────────────────────────────────────────

def test_why_flagged_does_not_contradict_evidence():
    for case in ["tampered_text","face_mismatch","multiple_flags","aadhaar_tampered"]:
        r         = _pipeline(case)
        factors   = r["risk"]["factors"]
        positive  = [f for f in factors if f["points"] > 0]
        narrative = r["risk"]["evidence_fusion"]["narrative"].lower()
        if positive:
            assert "no significant risk indicators" not in narrative, \
                f"Case {case}: has positive evidence but narrative says no risk indicators"


def test_why_flagged_clean_case_says_no_indicators():
    r = _pipeline("valid_passport")
    narrative = r["risk"]["evidence_fusion"]["narrative"].lower()
    assert ("no significant risk" in narrative or "all verification checks" in narrative), \
        f"Clean case narrative unexpected: {narrative[:100]}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 7 — Metadata absence must NOT be treated as forgery
# ─────────────────────────────────────────────────────────────────────────────

def test_metadata_absence_contributes_zero_risk():
    """Build a tampering result with only ABSENT metadata, no ELA anomalies."""
    tamp_absent = {
        "forensics_available": True,
        "status": "CLEAN",
        "is_suspicious": False,
        "overall_confidence": 0.0,
        "regions": [],
        "metadata_flags": [],
        "metadata_status": "ABSENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": "No anomalies. EXIF absent.",
        "demo_mode": False,
    }
    ocr  = run_ocr(None, "valid_passport")
    val  = run_validation(ocr, "valid_passport")
    mrz  = run_mrz(ocr, "valid_passport")
    face = run_face_verification(None, None, "valid_passport")
    risk = compute_risk(ocr, val, mrz, tamp_absent, face)

    meta_pts = risk.get("breakdown", {}).get("metadata", {}).get("points", 0)
    assert meta_pts == 0, f"Metadata absent contributes {meta_pts} risk points (should be 0)"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 8 — ELA alone must NOT claim forgery or dominate score
# ─────────────────────────────────────────────────────────────────────────────

def test_ela_moderate_alone_gives_review_not_high_risk():
    """Moderate ELA confidence (~60%) with clean everything else → REVIEW, not HIGH_RISK."""
    tamp_moderate = {
        "forensics_available": True,
        "status": "SUSPICIOUS",
        "is_suspicious": True,
        "overall_confidence": 60.0,
        "regions": [{"label":"Test Region","confidence":60.0,"bbox":[0,0,0.1,0.1],"reason":"Test"}],
        "metadata_flags": [],
        "metadata_status": "ABSENT",
        "analysis_types": {"ela": True, "metadata": True},
        "interpretation": "Moderate anomaly.",
        "demo_mode": False,
    }
    ocr  = run_ocr(None, "valid_passport")
    val  = run_validation(ocr, "valid_passport")
    mrz  = run_mrz(ocr, "valid_passport")
    face = run_face_verification(None, None, "valid_passport")
    risk = compute_risk(ocr, val, mrz, tamp_moderate, face)

    # Forensic cap is 25 pts max; for 60% → 14 pts
    for_pts = risk["breakdown"]["forensics"]["points"]
    assert for_pts <= CAP_FORENSICS, f"Forensics exceeded cap: {for_pts} > {CAP_FORENSICS}"
    # With only forensics contributing, total should be ≤ 25 → REVIEW not HIGH_RISK
    assert risk["score"] <= THRESHOLD_HIGH, \
        f"Moderate ELA alone gave HIGH_RISK ({risk['score']})"


def test_ela_interpretation_is_advisory():
    """Forensic interpretation must not say 'document is forged'."""
    for case in ["tampered_text","multiple_flags","aadhaar_tampered"]:
        tamp = run_tampering(None, case)
        interp = tamp.get("interpretation","").lower()
        assert "document is forged" not in interp, \
            f"Case {case}: interpretation contains forbidden phrase 'document is forged'"
        assert "proven fake" not in interp, \
            f"Case {case}: interpretation contains 'proven fake'"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 9 — Face score must not be described as identity proof
# ─────────────────────────────────────────────────────────────────────────────

def test_face_message_does_not_claim_identity_proof():
    forbidden = ["identity confirmed", "identity proven", "proves identity", "100% identity"]
    for case in DEMO_FACE:
        face = run_face_verification(None, None, case)
        msg  = face.get("message","").lower()
        for phrase in forbidden:
            assert phrase not in msg, \
                f"Case {case}: face message contains '{phrase}'"


def test_face_mismatch_decision_correct():
    face = run_face_verification(None, None, "face_mismatch")
    assert face["status"] == "MISMATCH"
    assert face["match_score"] < 60


def test_face_match_decision_correct():
    face = run_face_verification(None, None, "valid_passport")
    assert face["status"] == "MATCH"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 10 — No hardcoded/random scores
# ─────────────────────────────────────────────────────────────────────────────

def test_no_randomness_in_risk_deterministic():
    """Running the same case twice must give identical scores."""
    for case in ["valid_passport","tampered_text","aadhaar_tampered"]:
        r1 = _pipeline(case)["risk"]["score"]
        r2 = _pipeline(case)["risk"]["score"]
        assert r1 == r2, f"Case {case}: risk score is non-deterministic ({r1} vs {r2})"


# ─────────────────────────────────────────────────────────────────────────────
# BUG 11 — Frontend/report must use same result (validated via breakdown field)
# ─────────────────────────────────────────────────────────────────────────────

def test_result_has_breakdown_field():
    """risk.breakdown must be present for frontend to render correctly."""
    for case in ["valid_passport","aadhaar_valid","face_mismatch"]:
        r  = _pipeline(case)
        bd = r["risk"].get("breakdown")
        assert bd is not None, f"Case {case}: risk.breakdown missing"
        assert "total" in bd


def test_result_has_evidence_fusion():
    for case in ["valid_passport","tampered_text"]:
        r  = _pipeline(case)
        ef = r["risk"].get("evidence_fusion")
        assert ef is not None
        assert "narrative" in ef
        assert "signals" in ef


# ─────────────────────────────────────────────────────────────────────────────
# BUG 12 — Unknown/failed analysis must not become PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_unknown_doc_type_is_not_pass():
    """An unknown document type should trigger REVIEW override."""
    ocr_unknown = {
        "document_type": "unknown",
        "document_type_confidence": 0.1,
        "overall_confidence": 40.0,
        "ocr_available": True,
        "fields": [],
        "raw_mrz": None,
        "demo_mode": False,
    }
    val  = run_validation(ocr_unknown)
    mrz  = run_mrz(ocr_unknown)
    tamp = {"forensics_available": True, "status": "CLEAN", "is_suspicious": False,
            "overall_confidence": 0, "regions": [], "metadata_flags": [],
            "metadata_status": "ABSENT", "analysis_types": {}, "interpretation": ""}
    face = run_face_verification(None, None)
    risk = compute_risk(ocr_unknown, val, mrz, tamp, face)
    assert risk["decision"] != "PASS", \
        f"Unknown document type resulted in PASS (score={risk['score']})"


def test_ocr_unavailable_is_not_pass():
    """OCR unavailable must trigger REVIEW override."""
    ocr_unavail = {
        "document_type": "unknown",
        "document_type_confidence": 0.0,
        "overall_confidence": 0.0,
        "ocr_available": False,
        "fields": [],
        "raw_mrz": None,
        "demo_mode": False,
        "error": "OCR engine unavailable",
    }
    val  = run_validation(ocr_unavail)
    mrz  = run_mrz(ocr_unavail)
    tamp = {"forensics_available": False, "status": "INCONCLUSIVE", "is_suspicious": False,
            "overall_confidence": 0, "regions": [], "metadata_flags": [],
            "metadata_status": "ABSENT", "analysis_types": {}, "interpretation": ""}
    face = run_face_verification(None, None)
    risk = compute_risk(ocr_unavail, val, mrz, tamp, face)
    assert risk["decision"] != "PASS", \
        f"OCR unavailable resulted in PASS (score={risk['score']})"


# ─────────────────────────────────────────────────────────────────────────────
# RISK ENGINE INVARIANTS
# ─────────────────────────────────────────────────────────────────────────────

def test_risk_zero_evidence_equals_zero_score():
    ocr  = run_ocr(None, "valid_passport")
    val  = run_validation(ocr, "valid_passport")
    mrz  = run_mrz(ocr, "valid_passport")
    tamp = run_tampering(None, "valid_passport")
    face = run_face_verification(None, None, "valid_passport")
    risk = compute_risk(ocr, val, mrz, tamp, face)
    assert risk["score"] == 0, f"Clean passport score should be 0, got {risk['score']}"
    assert risk["decision"] == "PASS"


def test_risk_high_case_is_high_risk():
    risk = _pipeline("multiple_flags")["risk"]
    assert risk["decision"] == "HIGH_RISK", \
        f"multiple_flags should be HIGH_RISK, got {risk['decision']} (score={risk['score']})"
    assert risk["score"] >= 60


def test_risk_caps_respected():
    for case in ["valid_passport","expired_document","tampered_text",
                 "face_mismatch","multiple_flags","aadhaar_valid","aadhaar_tampered"]:
        r  = _pipeline(case)
        bd = r["risk"]["breakdown"]
        assert bd["ocr"]["points"]        <= CAP_OCR,        f"{case} OCR exceeded cap"
        assert bd["validation"]["points"] <= CAP_VALIDATION, f"{case} Validation exceeded cap"
        assert bd["mrz"]["points"]        <= CAP_MRZ,        f"{case} MRZ exceeded cap"
        assert bd["forensics"]["points"]  <= CAP_FORENSICS,  f"{case} Forensics exceeded cap"
        assert bd["face"]["points"]       <= CAP_FACE,       f"{case} Face exceeded cap"
        assert bd["metadata"]["points"]   <= CAP_METADATA,   f"{case} Metadata exceeded cap"


def test_pass_decision_never_above_threshold():
    for case in ["valid_passport","aadhaar_valid"]:
        r = _pipeline(case)
        if r["risk"]["decision"] == "PASS":
            assert r["risk"]["score"] <= THRESHOLD_PASS, \
                f"Case {case}: PASS decision but score {r['risk']['score']} > {THRESHOLD_PASS}"


def test_high_risk_decision_never_below_threshold():
    for case in ["multiple_flags","face_mismatch"]:
        r = _pipeline(case)
        if r["risk"]["decision"] == "HIGH_RISK":
            assert r["risk"]["score"] > THRESHOLD_HIGH, \
                f"Case {case}: HIGH_RISK decision but score {r['risk']['score']} <= {THRESHOLD_HIGH}"


def test_all_evidence_points_non_negative():
    for case in ["valid_passport","expired_document","tampered_text",
                 "face_mismatch","multiple_flags","aadhaar_valid","aadhaar_tampered"]:
        r = _pipeline(case)
        for f in r["risk"]["factors"]:
            assert f["points"] >= 0, \
                f"Case {case}: factor '{f['label']}' has negative points {f['points']}"


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT-SPECIFIC FIELD TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_aadhaar_has_no_passport_fields():
    ocr    = run_ocr(None, "aadhaar_valid")
    labels = [f["label"] for f in ocr["fields"]]
    assert "Passport Number" not in labels, "Aadhaar has Passport Number field"
    assert "Nationality"     not in labels, "Aadhaar has Nationality field"


def test_passport_has_no_aadhaar_fields():
    ocr    = run_ocr(None, "valid_passport")
    labels = [f["label"] for f in ocr["fields"]]
    assert "Aadhaar Number"   not in labels, "Passport has Aadhaar Number field"
    assert "Issuing Authority" not in labels, "Passport has Issuing Authority field"


def test_aadhaar_validation_has_no_mrz_checksum_check():
    val    = run_validation(run_ocr(None, "aadhaar_valid"), "aadhaar_valid")
    checks = [c["check_name"] for c in val["checks"]]
    assert not any("MRZ" in c or "Checksum" in c for c in checks), \
        f"Aadhaar validation contains MRZ/checksum check: {checks}"


# ─────────────────────────────────────────────────────────────────────────────
# DEMO CASE EXPECTED DECISIONS
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_DECISIONS = {
    "valid_passport":   "PASS",
    "expired_document": "REVIEW_REQUIRED",
    "tampered_text":    "HIGH_RISK",
    "face_mismatch":    "HIGH_RISK",
    "multiple_flags":   "HIGH_RISK",
    "aadhaar_valid":    "PASS",
    "aadhaar_tampered": "HIGH_RISK",
}

@pytest.mark.parametrize("case,expected", EXPECTED_DECISIONS.items())
def test_demo_case_decision(case, expected):
    r = _pipeline(case)
    d = r["risk"]["decision"]
    assert d == expected, \
        f"Case {case}: expected {expected}, got {d} (score={r['risk']['score']})"


# ─────────────────────────────────────────────────────────────────────────────
# REPORT CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────

def test_report_generates_without_error():
    from services.report_service import generate_pdf_report
    from routers.screening import _build_result
    import time, uuid

    for case in ["valid_passport","aadhaar_valid","tampered_text"]:
        sid    = f"HM-TEST-{uuid.uuid4().hex[:6].upper()}"
        result = _build_result(sid, case, None, None, time.time()*1000, True)
        pdf    = generate_pdf_report(result)
        assert len(pdf) > 100, f"Case {case}: empty report"
        # Should be valid PDF or UTF-8 text
        assert pdf[:4] == b"%PDF" or pdf[:6] == b"HEIMDA", \
            f"Case {case}: unexpected report format"


def test_report_no_contradiction_aadhaar():
    """Report for Aadhaar must not mention MRZ checksums as failures."""
    from services.report_service import generate_pdf_report
    from routers.screening import _build_result
    import time, uuid

    result = _build_result("HM-T-AADHAAR", "aadhaar_valid", None, None, time.time()*1000, True)
    pdf    = generate_pdf_report(result)
    text   = pdf.decode("latin-1").lower() if pdf[:4] == b"%PDF" else pdf.decode("utf-8").lower()
    # Should not say MRZ checksum failure for an Aadhaar card
    assert "mrz checksum failure" not in text, \
        "Aadhaar report contains 'MRZ checksum failure'"


def test_report_score_in_content():
    """Verify the score appears in the report."""
    from services.report_service import generate_pdf_report
    from routers.screening import _build_result
    import time, uuid

    result = _build_result("HM-T-SCORE", "expired_document", None, None, time.time()*1000, True)
    score  = result["risk"]["score"]
    pdf    = generate_pdf_report(result)
    # Score should appear somewhere in report
    assert str(score) in pdf.decode("latin-1") or str(score) in pdf.decode("utf-8","replace"), \
        f"Score {score} not found in report"


# ─────────────────────────────────────────────────────────────────────────────
# OCR REAL UPLOAD — must never return fake passport data on failure
# ─────────────────────────────────────────────────────────────────────────────

def test_ocr_real_upload_failure_returns_inconclusive_not_passport():
    """With no image path and no demo_case, result must be INCONCLUSIVE."""
    result = run_ocr(None, None)
    assert result["document_type"] == "unknown", \
        f"OCR with None path returned doc_type={result['document_type']}"
    assert result.get("ocr_available") is False, \
        "OCR with None path should have ocr_available=False"
    # Must not have fake passport fields
    passport_vals = [f["value"] for f in result.get("fields", []) if f.get("value")]
    assert len(passport_vals) == 0, \
        f"OCR failure returned fake field values: {passport_vals}"


def test_ocr_no_demo_case_no_path_has_no_passport_number():
    result = run_ocr(None, None)
    labels = [f["label"] for f in result.get("fields", [])]
    assert "Passport Number" not in labels


# ─────────────────────────────────────────────────────────────────────────────
# FACE — INCONCLUSIVE when engine unavailable
# ─────────────────────────────────────────────────────────────────────────────

def test_face_no_reference_returns_not_provided():
    face = run_face_verification(None, None, None)
    assert face["status"] == "NOT_PROVIDED"
    assert face.get("match_score") is None


def test_face_not_provided_contributes_zero_risk():
    ocr  = run_ocr(None, "valid_passport")
    val  = run_validation(ocr, "valid_passport")
    mrz  = run_mrz(ocr, "valid_passport")
    tamp = run_tampering(None, "valid_passport")
    face = run_face_verification(None, None, None)  # no reference
    risk = compute_risk(ocr, val, mrz, tamp, face)
    face_pts = risk["breakdown"]["face"]["points"]
    assert face_pts == 0, f"No-reference face contributed {face_pts} risk points"


# ─────────────────────────────────────────────────────────────────────────────
# ALL SIGNALS SUM == SCORE
# ─────────────────────────────────────────────────────────────────────────────

def test_signals_contribution_sum_matches_score():
    """
    Each signal contribution in evidence_fusion.signals represents
    the points of its factor. The sum of ALL factor points (from factors list)
    should equal the score (after caps).
    """
    for case in ["valid_passport","expired_document","tampered_text",
                 "face_mismatch","multiple_flags","aadhaar_valid","aadhaar_tampered"]:
        r  = _pipeline(case)
        bd = r["risk"]["breakdown"]
        total_from_breakdown = sum(v["points"] for k, v in bd.items() if k != "total")
        assert abs(total_from_breakdown - r["risk"]["score"]) <= 1, \
            f"Case {case}: breakdown points {total_from_breakdown} != score {r['risk']['score']}"
