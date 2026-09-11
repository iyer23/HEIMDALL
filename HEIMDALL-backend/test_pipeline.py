"""Quick smoke test — runs all 7 demo cases through the full pipeline."""
import sys
sys.path.insert(0, '.')

from services.ocr_service        import run_ocr
from services.validation_service import run_validation
from services.mrz_service        import run_mrz
from services.tampering_service  import run_tampering
from services.face_service       import run_face_verification
from services.risk_service       import compute_risk

CASES = [
    'valid_passport',
    'expired_document',
    'tampered_text',
    'face_mismatch',
    'multiple_flags',
    'aadhaar_valid',
    'aadhaar_tampered',
]

EXPECTED = {
    'valid_passport':   'PASS',
    'expired_document': 'REVIEW_REQUIRED',
    'tampered_text':    'HIGH_RISK',
    'face_mismatch':    'HIGH_RISK',
    'multiple_flags':   'HIGH_RISK',
    'aadhaar_valid':    'PASS',
    'aadhaar_tampered': 'HIGH_RISK',
}

errors = []
print(f"{'Case':<22} {'Score':>5}  {'Decision':<20}  {'MRZ':^7}  {'Narrative snippet'}")
print("-" * 100)

for case in CASES:
    try:
        o = run_ocr(None, case)
        v = run_validation(o, case)
        m = run_mrz(o, case)
        t = run_tampering(None, case)
        f = run_face_verification(None, None, case)
        r = compute_risk(o, v, m, t, f)

        ef        = r.get('evidence_fusion', {})
        narrative = ef.get('narrative', '')[:60] + '…' if ef.get('narrative') else '—'
        mrz_str   = 'present' if m['mrz_present'] else 'absent '
        score     = r['score']
        decision  = r['decision']
        expected  = EXPECTED[case]

        status = '✓' if decision == expected else f'✗ (expected {expected})'
        print(f"{case:<22} {score:>5}  {decision:<20}  {mrz_str}  {narrative}")
        if decision != expected:
            errors.append(f"{case}: got {decision}, expected {expected}")

        # Also verify evidence_fusion has narrative + signals
        assert ef.get('narrative'), f"{case}: missing narrative"
        assert len(ef.get('signals', [])) > 0, f"{case}: no signals"

    except Exception as e:
        errors.append(f"{case}: EXCEPTION — {e}")
        print(f"  ERROR: {e}")

print("-" * 100)
if errors:
    print(f"\n✗ {len(errors)} failure(s):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"\n✓ All {len(CASES)} cases passed.")
