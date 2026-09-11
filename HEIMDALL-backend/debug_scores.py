import sys; sys.path.insert(0,'.')
from services.ocr_service import run_ocr
from services.validation_service import run_validation
from services.mrz_service import run_mrz
from services.tampering_service import run_tampering
from services.face_service import run_face_verification
from services.risk_service import compute_risk

for case in ['valid_passport','aadhaar_valid','face_mismatch','expired_document','tampered_text','aadhaar_tampered','multiple_flags']:
    o = run_ocr(None, case)
    v = run_validation(o, case)
    m = run_mrz(o, case)
    t = run_tampering(None, case)
    f = run_face_verification(None, None, case)
    r = compute_risk(o, v, m, t, f)
    bd = r['breakdown']
    total_from_bd = sum(val['points'] for k,val in bd.items() if isinstance(val, dict))
    print(case, 'score='+str(r['score']), r['decision'], 'bd_sum='+str(total_from_bd))
    for k, val in bd.items():
        if isinstance(val, dict) and val['points'] > 0:
            print('   ', k, str(val['points']))
