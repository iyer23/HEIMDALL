"""
HEIMDALL — Final Bug Audit
Verifies all 12 known bugs are fixed.
"""
import sys
sys.path.insert(0, '.')

from services.ocr_service import run_ocr
from services.validation_service import run_validation
from services.mrz_service import run_mrz
from services.tampering_service import run_tampering
from services.face_service import run_face_verification
from services.risk_service import compute_risk, THRESHOLD_PASS, THRESHOLD_HIGH

def pipeline(case):
    o = run_ocr(None, case)
    v = run_validation(o, case)
    m = run_mrz(o, case)
    t = run_tampering(None, case)
    f = run_face_verification(None, None, case)
    r = compute_risk(o, v, m, t, f)
    return o, v, m, t, f, r

results = {}
for case in ["valid_passport","expired_document","tampered_text","face_mismatch",
             "multiple_flags","aadhaar_valid","aadhaar_tampered"]:
    o,v,m,t,f,r = pipeline(case)
    results[case] = (o,v,m,t,f,r)

bugs = []

def check(num, desc, condition):
    icon = "FIXED" if condition else "STILL BROKEN"
    sym  = "[+]" if condition else "[X]"
    print(f"  {sym} BUG {num:>2}: {desc[:60]:<60} -> {icon}")
    if not condition:
        bugs.append(f"BUG {num}: {desc}")

print()
print("=" * 75)
print("HEIMDALL — FINAL BUG AUDIT")
print("=" * 75)

# BUG 1: Aadhaar classified as Passport
check(1, "Aadhaar NOT classified as Passport",
      results["aadhaar_valid"][0]["document_type"] == "national_id" and
      results["aadhaar_tampered"][0]["document_type"] == "national_id")

# BUG 2: MRZ running on Aadhaar
check(2, "MRZ NOT_APPLICABLE for Aadhaar",
      results["aadhaar_valid"][2]["status"] == "NOT_APPLICABLE" and
      results["aadhaar_tampered"][2]["status"] == "NOT_APPLICABLE")

# BUG 3: MRZ says unrecognized format but checksum valid
check(3, "MRZ VALID status -> all checksums pass (no contradiction)",
      all(
          c["status"] != "FAIL"
          for c in results["valid_passport"][2].get("checks", [])
          if results["valid_passport"][2]["status"] == "VALID"
      ))

# BUG 4: MRZ says checksum failed AND all checks valid simultaneously
check(4, "MRZ checksums_valid consistent with checks list",
      not (results["valid_passport"][2]["checksums_valid"] is True and
           any(c["status"] == "FAIL" for c in results["valid_passport"][2].get("checks", []))))

# BUG 5: Risk score does not match breakdown
check(5, "Risk score == breakdown sum for all cases",
      all(
          abs(sum(v["points"] for k,v in r["breakdown"].items() if k != "total") - r["score"]) <= 1
          for _,_,_,_,_,r in results.values()
      ))

# BUG 6: WHY FLAGGED says "all checks passed" while showing anomalies
check(6, "Non-PASS cases do NOT have 'no significant risk' in narrative",
      all(
          "no significant risk" not in r["evidence_fusion"]["narrative"].lower()
          for case,(o,v,m,t,f,r) in results.items()
          if r["decision"] != "PASS"
      ))

# BUG 7: Metadata absence interpreted as forgery
tamp_valid = results["valid_passport"][3]
check(7, "EXIF absence contributes 0 metadata risk points",
      results["valid_passport"][5]["breakdown"]["metadata"]["points"] == 0)

# BUG 8: ELA alone interpreted as forgery
check(8, "ELA interpretation does not say 'document is forged'",
      not any(
          "document is forged" in t.get("interpretation","").lower() or
          "proven fake" in t.get("interpretation","").lower()
          for _,_,_,t,_,_ in results.values()
      ))

# BUG 9: Face score treated as absolute identity proof
check(9, "Face messages do not claim identity proof",
      not any(
          any(phrase in f.get("message","").lower()
              for phrase in ["identity confirmed","identity proven","100% identity"])
          for _,_,_,_,f,_ in results.values()
      ))

# BUG 10: Hardcoded/random AI scores
o1,_,_,_,_,r1 = pipeline("tampered_text")
o2,_,_,_,_,r2 = pipeline("tampered_text")
check(10, "Risk scores are deterministic (same case = same score)",
      r1["score"] == r2["score"])

# BUG 11: Frontend/report calculate separate results
from services.report_service import _check_consistency
for case,(o,v,m,t,f,r) in results.items():
    from routers.screening import _build_result
    import time, uuid
    full = _build_result(f"HM-AUDIT-{case}", case, None, None, time.time()*1000, True)
    viols = _check_consistency(full)
    if viols:
        bugs.append(f"BUG 11 {case}: {viols}")
check(11, "Report consistency validator passes for all demo cases",
      not any(f"BUG 11" in b for b in bugs))

# BUG 12: Unknown/failed analysis becomes PASS
ocr_fail = {"document_type":"unknown","document_type_confidence":0.0,"overall_confidence":0.0,
            "ocr_available":False,"fields":[],"raw_mrz":None,"demo_mode":False}
v_fail  = run_validation(ocr_fail)
m_fail  = run_mrz(ocr_fail)
t_clean = {"forensics_available":False,"status":"INCONCLUSIVE","is_suspicious":False,
           "overall_confidence":0,"regions":[],"metadata_flags":[],"metadata_status":"ABSENT",
           "analysis_types":{},"interpretation":""}
f_skip  = run_face_verification(None, None, None)
r_fail  = compute_risk(ocr_fail, v_fail, m_fail, t_clean, f_skip)
check(12, "Unknown doc type / OCR unavailable does NOT become PASS",
      r_fail["decision"] != "PASS")

print()
print("=" * 75)
if bugs:
    print(f"AUDIT RESULT: {len(bugs)} REMAINING ISSUE(S):")
    for b in bugs: print(f"  - {b}")
    sys.exit(1)
else:
    print("AUDIT RESULT: ALL 12 BUGS FIXED")
    print("=" * 75)
    print()
    print("Scores summary:")
    for case,(o,v,m,t,f,r) in results.items():
        print(f"  {case:<22}  score={r['score']:>3}/100  {r['decision']}")
