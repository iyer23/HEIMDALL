"""
HEIMDALL End-to-End Smoke Test
Tests all 7 demo cases via the live API, then tests report generation.
"""
import sys, json, urllib.request, urllib.error

BASE = "http://localhost:8000"

EXPECTED = {
    "valid_passport":   ("PASS",            0,   10),
    "expired_document": ("REVIEW_REQUIRED", 11,  17),
    "tampered_text":    ("HIGH_RISK",       18, 100),
    "face_mismatch":    ("HIGH_RISK",       18, 100),
    "multiple_flags":   ("HIGH_RISK",       18, 100),
    "aadhaar_valid":    ("PASS",             0,  10),
    "aadhaar_tampered": ("HIGH_RISK",       18, 100),
}

def post_json(url, data):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()

errors = []
print("=" * 65)
print("HEIMDALL SMOKE TEST")
print("=" * 65)

# ── Root ─────────────────────────────────────────────────────────
try:
    root = json.loads(get(f"{BASE}/"))
    assert root["system"] == "HEIMDALL", f"Root system={root['system']}"
    print(f"[OK] Root  system={root['system']}  status={root['status']}")
except Exception as e:
    print(f"[FAIL] Root: {e}"); errors.append(str(e))

# ── Health ───────────────────────────────────────────────────────
try:
    h = json.loads(get(f"{BASE}/api/health"))
    print(f"[OK] Health  ocr={h['ocr_engine']}  tampering={h['tampering_engine']}  face={h['face_engine']}  db={h['database']}")
except Exception as e:
    print(f"[FAIL] Health: {e}"); errors.append(str(e))

# ── Demo cases ───────────────────────────────────────────────────
report_id = None
for case, (exp_dec, min_score, max_score) in EXPECTED.items():
    try:
        r = post_json(f"{BASE}/api/screening/demo", {"demo_case": case})

        # Basic structure checks
        assert "screening_id" in r,        "Missing screening_id"
        assert r["screening_id"].startswith("HM-"), f"ID prefix wrong: {r['screening_id']}"
        assert "risk" in r,                "Missing risk"
        assert "breakdown" in r["risk"],   "Missing risk.breakdown"
        assert "evidence_fusion" in r,     "Missing evidence_fusion"
        assert "signals" in r["evidence_fusion"], "Missing evidence_fusion.signals"
        assert "mrz" in r,                 "Missing mrz"
        assert "status" in r["mrz"],       "Missing mrz.status"
        assert "tampering" in r,           "Missing tampering"
        assert "status" in r["tampering"], "Missing tampering.status"
        assert "face_verification" in r,   "Missing face_verification"
        assert "status" in r["face_verification"], "Missing face_verification.status"

        score    = r["risk"]["score"]
        decision = r["risk"]["decision"]
        mrz_st   = r["mrz"]["status"]
        tamp_st  = r["tampering"]["status"]
        face_st  = r["face_verification"]["status"]
        bd       = r["risk"]["breakdown"]

        # Decision check
        assert decision == exp_dec, f"Expected {exp_dec}, got {decision}"

        # Score range check
        assert min_score <= score <= max_score, f"Score {score} outside [{min_score},{max_score}]"

        # Breakdown sum == score (score is capped at 100; breakdown sums raw contributions)
        bd_sum = sum(v["points"] for k, v in bd.items() if isinstance(v, dict))
        assert abs(min(bd_sum, 100) - score) <= 1, f"Breakdown sum {bd_sum} != score {score}"

        # Aadhaar must not have MRZ risk
        if case in ("aadhaar_valid", "aadhaar_tampered"):
            assert mrz_st == "NOT_APPLICABLE", f"Aadhaar mrz.status={mrz_st}"
            assert bd["mrz"]["points"] == 0, f"Aadhaar MRZ points={bd['mrz']['points']}"

        # Consistent narrative vs evidence
        # A PASS case may still mention minor concerns (e.g. "QR verification
        # not possible via image upload") — it must not claim serious risk.
        narrative = r["evidence_fusion"]["narrative"].lower()
        positive_signals = [s for s in r["evidence_fusion"]["signals"] if s["contribution"] > 0]
        if decision == "PASS":
            for bad in ("high risk", "forgery", "altered", "invalid check digit", "mismatch"):
                assert bad not in narrative, f"PASS narrative claims serious risk: '{bad}' in {narrative[:60]}"
        else:
            assert "no significant risk" not in narrative, \
                f"Non-PASS but narrative says no risk"

        # Report: EXIF absent flag = 0 metadata points for clean docs
        if case == "valid_passport":
            assert bd["metadata"]["points"] == 0, \
                f"Clean passport metadata points={bd['metadata']['points']}"

        print(f"[OK] {case:<22} score={score:>3}  {decision:<20}  mrz={mrz_st}  tamp={tamp_st}")
        if report_id is None:
            report_id = r["screening_id"]

    except AssertionError as e:
        print(f"[FAIL] {case}: {e}"); errors.append(f"{case}: {e}")
    except Exception as e:
        print(f"[FAIL] {case}: {e}"); errors.append(f"{case}: {e}")

# ── Report generation ────────────────────────────────────────────
if report_id:
    try:
        pdf = get(f"{BASE}/api/screening/{report_id}/report")
        assert len(pdf) > 200, f"Report too small: {len(pdf)} bytes"
        is_pdf  = pdf[:4] == b"%PDF"
        is_text = pdf[:6] == b"HEIMDA"
        assert is_pdf or is_text, f"Unexpected report format: {pdf[:10]}"
        fmt = "PDF" if is_pdf else "TEXT"
        print(f"[OK] Report  {fmt}  {len(pdf)} bytes  id={report_id}")
    except Exception as e:
        print(f"[FAIL] Report: {e}"); errors.append(f"Report: {e}")

# ── History ─────────────────────────────────────────────────────
try:
    hist = json.loads(get(f"{BASE}/api/screenings?limit=10"))
    assert "records" in hist
    assert "total" in hist
    assert hist["total"] >= 7, f"Expected >= 7 records, got {hist['total']}"
    print(f"[OK] History  total={hist['total']} records")
except Exception as e:
    print(f"[FAIL] History: {e}"); errors.append(f"History: {e}")

# ── Analytics ───────────────────────────────────────────────────
try:
    ana = json.loads(get(f"{BASE}/api/analytics"))
    assert "total_screened" in ana
    assert "risk_distribution" in ana
    print(f"[OK] Analytics  total={ana['total_screened']}  high={ana['high_risk']}  review={ana['review_required']}  pass={ana['passed']}")
except Exception as e:
    print(f"[FAIL] Analytics: {e}"); errors.append(f"Analytics: {e}")

# ── Frontend reachable ───────────────────────────────────────────
try:
    page = get("http://localhost:5173/")
    assert b"HEIMDALL" in page or b"root" in page, "Frontend page missing HEIMDALL/root"
    print(f"[OK] Frontend  http://localhost:5173/  ({len(page)} bytes)")
except Exception as e:
    print(f"[FAIL] Frontend: {e}"); errors.append(f"Frontend: {e}")

# ── Summary ─────────────────────────────────────────────────────
print("=" * 65)
if errors:
    print(f"RESULT: {len(errors)} FAILURE(S):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("RESULT: ALL SMOKE TESTS PASSED")
    print("=" * 65)
