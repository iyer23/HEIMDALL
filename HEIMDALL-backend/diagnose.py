import sys; sys.path.insert(0, '.')
from services.ocr_service import run_ocr
from services.validation_service import run_validation
from services.mrz_service import run_mrz
from services.tampering_service import run_tampering
from services.face_service import run_face_verification
from services.risk_service import compute_risk, THRESHOLD_PASS, THRESHOLD_HIGH

print("=== DIAGNOSIS: Real upload with OCR unavailable + moderate forensics ===")
print(f"THRESHOLD_PASS={THRESHOLD_PASS}  THRESHOLD_HIGH={THRESHOLD_HIGH}")
print()

# Simulate what happens with a real upload where OCR is unavailable
o = run_ocr(None, None)   # no demo_case, no path => INCONCLUSIVE
v = run_validation(o)
m = run_mrz(o)
t_suspicious = {
    'forensics_available': True,
    'status': 'SUSPICIOUS',
    'is_suspicious': True,
    'overall_confidence': 57.0,
    'regions': [
        {'label': 'R1', 'confidence': 60, 'bbox': [0,0,0.1,0.1], 'reason': 'ELA anomaly 1'},
        {'label': 'R2', 'confidence': 58, 'bbox': [0,0,0.1,0.1], 'reason': 'ELA anomaly 2'},
        {'label': 'R3', 'confidence': 55, 'bbox': [0,0,0.1,0.1], 'reason': 'ELA anomaly 3'},
        {'label': 'R4', 'confidence': 52, 'bbox': [0,0,0.1,0.1], 'reason': 'ELA anomaly 4'},
        {'label': 'R5', 'confidence': 50, 'bbox': [0,0,0.1,0.1], 'reason': 'ELA anomaly 5'},
    ],
    'metadata_flags': [],
    'metadata_status': 'ABSENT',
    'analysis_types': {'ela': True, 'metadata': True},
    'interpretation': 'Moderate ELA anomaly. Can arise from JPEG recompression.',
}
f = run_face_verification(None, None, None)

r = compute_risk(o, v, m, t_suspicious, f)

print("Input state:")
print("  OCR available:", o.get('ocr_available'))
print("  doc_type:", o.get('document_type'))
print("  face status:", f.get('status'))
print("  forensics status:", t_suspicious['status'], "confidence:", t_suspicious['overall_confidence'])
print()
print("Risk breakdown:")
bd = r['breakdown']
for k, val in bd.items():
    if k != 'total':
        pts = val['points']
        cap = val['cap']
        print(f"  {k:<12}: {pts:>3}/{cap}")
print(f"  {'TOTAL':<12}: {r['score']:>3}/100")
print()
print(f"Decision: {r['decision']}")
print(f"Override: {r.get('override_reason')}")
print()
print("Positive factors:")
for fac in r['factors']:
    if fac['points'] > 0:
        print(f"  +{fac['points']:>2} {fac['label']}")
print()

# The bug: 19 pts (8+3+8) → THRESHOLD_HIGH=17 → HIGH_RISK!
print(f"BUG CONFIRMED: score={r['score']} > THRESHOLD_HIGH={THRESHOLD_HIGH} → {r['decision']}")
print(f"THRESHOLD semantics: ≤{THRESHOLD_PASS}=PASS, {THRESHOLD_PASS+1}-{THRESHOLD_HIGH}=REVIEW, >{THRESHOLD_HIGH}=HIGH_RISK")
print(f"19 > 17 → HIGH_RISK  ← THIS IS WRONG for this scenario")
