"""Quick test of all demo cases"""
import urllib.request, json

cases = ['valid_passport','expired_document','tampered_text','face_mismatch','multiple_flags','aadhaar_valid','aadhaar_tampered']
for case in cases:
    data = json.dumps({'demo_case': case}).encode()
    req = urllib.request.Request('http://localhost:8000/api/screening/demo', data=data, headers={'Content-Type':'application/json'}, method='POST')
    resp = urllib.request.urlopen(req).read().decode()
    result = json.loads(resp)
    risk = result['risk']
    tamp = result['tampering']
    face = result['face_verification']
    mrz = result['mrz']
    doc_type = result['document_type']
    score = risk['score']
    decision = risk['decision']
    nregions = len(tamp.get('regions', []))
    mrz_status = mrz.get('status','?')
    face_status = face.get('status','?')
    print(f"{case:25} type={doc_type:15} score={score:3}  decision={decision:20}  mrz={mrz_status:15}  face={face_status:15}  regions={nregions}")
