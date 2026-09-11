"""
HEIMDALL — MRZ Service
SIH 2026 · PS 26188

ICAO 9303 Machine Readable Zone parsing and validation.

KEY RULES:
- MRZ is ONLY attempted for passport and visa document types.
- Aadhaar / national_id / driving_licence → status = NOT_APPLICABLE (0 risk).
- checksums_valid and checks[] must always be internally consistent.
- Never say "all checksums valid" while any check has status FAIL.
- status field: NOT_APPLICABLE | NOT_DETECTED | UNREADABLE | VALID | PARTIAL | INVALID
"""
from __future__ import annotations
import re
import logging
from datetime import date

logger = logging.getLogger("heimdall.mrz")

# Document types that use ICAO MRZ
MRZ_APPLICABLE_TYPES = {"passport", "visa"}


# ── ICAO check-digit algorithm (7-3-1 weighting) ─────────────────────────────

def _char_val(c: str) -> int:
    if c == "<":    return 0
    if c.isdigit(): return int(c)
    if c.isalpha(): return ord(c.upper()) - ord("A") + 10
    return 0

def _checksum(field: str) -> int:
    weights = [7, 3, 1]
    return sum(_char_val(ch) * weights[i % 3] for i, ch in enumerate(field)) % 10

def _chk_valid(field: str, digit: str) -> bool:
    try:
        return str(_checksum(field)) == str(digit)
    except Exception:
        return False

# Common OCR confusions that must be digits inside an MRZ numeric field.
# Only ever applied as a repair candidate — a correction is accepted only if
# the ICAO check digit then validates, so a wrong substitution cannot slip through.
_DIGIT_FIX = str.maketrans({
    "O": "0", "D": "0", "Q": "0", "U": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6", "T": "7",
    "B": "8",
})

def _fix_digits(field: str) -> str:
    return field.translate(_DIGIT_FIX)


# ── Date helpers ──────────────────────────────────────────────────────────────

def _mrz_date(yymmdd: str, pivot: int = 60) -> str:
    """
    YYMMDD → DD/MM/YYYY string.
    DOB uses a century pivot (yy < 60 → 20xx, else 19xx);
    expiry dates are always 20xx (pass pivot=100).
    """
    try:
        yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
        year = (2000 + yy) if yy < pivot else (1900 + yy)
        return f"{dd:02d}/{mm:02d}/{year}"
    except Exception:
        return yymmdd

def _parse_name(raw: str) -> tuple[str, str]:
    parts = raw.split("<<", 1)
    surname    = re.sub(r"\s+", " ", parts[0].replace("<", " ")).strip()
    given      = re.sub(r"\s+", " ", parts[1].replace("<", " ")).strip() if len(parts) > 1 else ""
    return surname, given


# ── OCR-confusion repair (validated by ICAO check digit) ─────────────────────

def _resolve_check(field: str, digit: str):
    """
    Try the raw field/digit, then OCR-confusion-repaired variants.
    A repair is accepted ONLY if the ICAO check digit validates with it.
    Returns (corrected_field, corrected_digit, ok, was_repaired).
    """
    fixed_f = _fix_digits(field)
    fixed_d = _fix_digits(digit)
    for f in dict.fromkeys([field, fixed_f]):
        for d in dict.fromkeys([digit, fixed_d]):
            if _chk_valid(f, d):
                return f, d, True, (f != field or d != digit)
    # No valid combination — caller decides which representative to display.
    return field, digit, False, False


# ── TD3 parser (passport — 2×44) ─────────────────────────────────────────────

def _parse_td3(line1: str, line2: str) -> dict:
    l1 = line1.ljust(44, "<")[:44]
    l2 = line2.ljust(44, "<")[:44]

    surname, given = _parse_name(l1[5:44])

    doc_num, doc_cd, doc_ok, doc_rep = _resolve_check(l2[0:9], l2[9])
    # Dates are strictly numeric — always prefer the digit-repaired read.
    dob_raw, dob_cd, dob_ok, dob_rep = _resolve_check(l2[13:19], l2[19])
    dob_raw = _fix_digits(dob_raw)
    exp_raw, exp_cd, exp_ok, exp_rep = _resolve_check(l2[21:27], l2[27])
    exp_raw = _fix_digits(exp_raw)
    sex        = l2[20]
    optional   = l2[28:43]   # 14-char personal number + its check digit (ICAO TD3: 44-char line)
    comp_cd    = l2[43]      # composite check digit is the LAST character (0-based 43)
    comp_field = doc_num + l2[9] + dob_raw + dob_cd + exp_raw + exp_cd + optional
    comp_field, comp_cd2, comp_ok, comp_rep = _resolve_check(comp_field, comp_cd)
    comp_cd = comp_cd2

    checks = []
    n_fail = 0

    def chk(name: str, field: str, digit: str, label: str, ok: bool, repaired: bool):
        nonlocal n_fail
        if not ok:
            n_fail += 1
        repair_note = " (auto-corrected OCR character confusion)" if repaired else ""
        checks.append({
            "check_name": name,
            "status":     "PASS" if ok else "FAIL",
            "message":    (
                f"Check digit '{digit}' valid for {label}{repair_note}"
                if ok else
                f"Check digit '{digit}' INVALID (expected '{_checksum(field)}') for {label}"
            ),
            "field":    field,
            "digit":    digit,
            "expected": _checksum(field),
        })
        return ok

    chk("Document Number Check Digit", doc_num,    doc_cd, f"document number '{doc_num.replace('<','')}'", doc_ok, doc_rep)
    chk("Date of Birth Check Digit",   dob_raw,    dob_cd, f"DOB '{_mrz_date(dob_raw)}'", dob_ok, dob_rep)
    chk("Expiry Date Check Digit",     exp_raw,    exp_cd, f"expiry '{_mrz_date(exp_raw, pivot=100)}'", exp_ok, exp_rep)
    chk("Composite Check Digit",       comp_field, comp_cd,"composite field", comp_ok, comp_rep)

    checksums_valid = (n_fail == 0)
    status = "VALID" if checksums_valid else ("PARTIAL" if n_fail < len(checks) else "INVALID")

    return {
        "format": "TD3",
        "issuing_state":   l1[2:5].replace("<", "").strip(),
        "surname":         surname,
        "given_names":     given,
        "full_name":       f"{given} {surname}".strip(),
        "document_number": doc_num.replace("<", "").strip(),
        "nationality":     l2[10:13].replace("<", "").strip(),
        "date_of_birth":   _mrz_date(dob_raw),
        "sex":             sex if sex in ("M", "F") else "UNSPECIFIED",
        "expiry_date":     _mrz_date(exp_raw, pivot=100),
        "checksums_valid": checksums_valid,
        "checks":          checks,
        "status":          status,
    }


# ── TD1 parser (ID cards — 3×30) ─────────────────────────────────────────────

def _parse_td1(line1: str, line2: str, line3: str) -> dict:
    l1 = line1.ljust(30, "<")[:30]
    l2 = line2.ljust(30, "<")[:30]
    l3 = line3.ljust(30, "<")[:30]

    doc_num, doc_cd, doc_ok, doc_rep = _resolve_check(l1[5:14], l1[14])
    # Dates are strictly numeric — always prefer the digit-repaired read.
    dob_raw, dob_cd, dob_ok, dob_rep = _resolve_check(l2[0:6], l2[6])
    dob_raw = _fix_digits(dob_raw)
    exp_raw, exp_cd, exp_ok, exp_rep = _resolve_check(l2[8:14], l2[14])
    exp_raw = _fix_digits(exp_raw)
    sex     = l2[7]
    comp_cd = l2[29]
    comp_field = doc_num + l1[14] + l1[15:30] + dob_raw + dob_cd + exp_raw + exp_cd + l2[18:29]
    comp_field, comp_cd, comp_ok, comp_rep = _resolve_check(comp_field, comp_cd)
    surname, given = _parse_name(l3[0:30])

    checks = []
    n_fail = 0

    def chk(name: str, field: str, digit: str, label: str, ok: bool, repaired: bool):
        nonlocal n_fail
        if not ok: n_fail += 1
        repair_note = " (auto-corrected OCR character confusion)" if repaired else ""
        checks.append({
            "check_name": name, "status": "PASS" if ok else "FAIL",
            "message": (f"Check digit '{digit}' valid for {label}{repair_note}" if ok
                        else f"Check digit '{digit}' INVALID (expected '{_checksum(field)}') for {label}"),
            "field": field, "digit": digit, "expected": _checksum(field),
        })
        return ok

    chk("Document Number Check Digit", doc_num, doc_cd, f"'{doc_num.replace('<','')}'", doc_ok, doc_rep)
    chk("Date of Birth Check Digit",   dob_raw, dob_cd, f"'{_mrz_date(dob_raw)}'", dob_ok, dob_rep)
    chk("Expiry Date Check Digit",     exp_raw, exp_cd, f"'{_mrz_date(exp_raw, pivot=100)}'", exp_ok, exp_rep)
    chk("Composite Check Digit",       comp_field, comp_cd, "composite", comp_ok, comp_rep)

    checksums_valid = (n_fail == 0)
    status = "VALID" if checksums_valid else ("PARTIAL" if n_fail < len(checks) else "INVALID")

    return {
        "format": "TD1",
        "issuing_state":   l1[2:5].replace("<","").strip(),
        "surname":         surname,
        "given_names":     given,
        "full_name":       f"{given} {surname}".strip(),
        "document_number": doc_num.replace("<","").strip(),
        "nationality":     l2[15:18].replace("<","").strip(),
        "date_of_birth":   _mrz_date(dob_raw),
        "sex":             sex if sex in ("M","F") else "UNSPECIFIED",
        "expiry_date":     _mrz_date(exp_raw, pivot=100),
        "checksums_valid": checksums_valid,
        "checks":          checks,
        "status":          status,
    }


# ── Cross-validation: OCR visual zone vs MRZ ─────────────────────────────────

def _cross_validate(parsed: dict, ocr_fields: list[dict]) -> list[dict]:
    field_map = {f["label"].lower(): (f.get("value") or "").strip().upper()
                 for f in ocr_fields if f.get("detected")}

    comparisons = [
        ("date of birth",    "date_of_birth",   "Date of Birth"),
        ("date of expiry",   "expiry_date",      "Expiry Date"),
        ("nationality",      "nationality",      "Nationality"),
        ("passport number",  "document_number",  "Document Number"),
    ]
    findings = []
    for ocr_key, mrz_key, label in comparisons:
        mrz_val = (parsed.get(mrz_key) or "").strip().upper()
        ocr_val = field_map.get(ocr_key, "")
        if not mrz_val or not ocr_val:
            continue
        # Normalize dates
        if "date" in ocr_key:
            ocr_n = re.sub(r"[/\-\.]", "", ocr_val)
            mrz_n = re.sub(r"[/\-\.]", "", mrz_val)
            match = (ocr_n == mrz_n)
        elif ocr_key in ("nationality",):
            # "INDIAN" (OCR visual zone) vs "IND" (ISO 3166 in MRZ) are consistent.
            match = (ocr_val.replace("<","") == mrz_val.replace("<","")
                     or ocr_val.startswith(mrz_val) or mrz_val.startswith(ocr_val))
        else:
            match = (ocr_val.replace("<","") == mrz_val.replace("<",""))

        findings.append({
            "field":   label,
            "ocr_val": ocr_val or "—",
            "mrz_val": mrz_val or "—",
            "match":   match,
            "status":  "PASS" if match else "FAIL",
            "message": (f"OCR '{ocr_val}' matches MRZ '{mrz_val}'" if match
                        else f"MISMATCH — OCR '{ocr_val}' vs MRZ '{mrz_val}'"),
        })
    return findings


# ── DEMO fixtures (only used when demo_case is explicit) ──────────────────────

DEMO_MRZ: dict[str, dict] = {
    "valid_passport": {
        "status": "VALID",
        "mrz_present": True,
        "format": "TD3",
        "parsed": {
            "full_name": "RAJESH KUMAR SHARMA",
            "document_number": "P8472613",
            "nationality": "IND",
            "date_of_birth": "12/05/1990",
            "sex": "M",
            "expiry_date": "14/03/2030",
            "checksums_valid": True,
        },
        "checks": [
            {"check_name":"Document Number Check Digit","status":"PASS","message":"Check digit '2' valid for document number 'P8472613'"},
            {"check_name":"Date of Birth Check Digit",  "status":"PASS","message":"Check digit '6' valid for DOB '12/05/1990'"},
            {"check_name":"Expiry Date Check Digit",    "status":"PASS","message":"Check digit '7' valid for expiry '14/03/2030'"},
            {"check_name":"Composite Check Digit",      "status":"PASS","message":"Composite check digit valid"},
        ],
        "cross_validation": [
            {"field":"Document Number","ocr_val":"P8472613","mrz_val":"P8472613","match":True,"status":"PASS","message":"Match"},
            {"field":"Date of Birth",  "ocr_val":"12/05/1990","mrz_val":"12/05/1990","match":True,"status":"PASS","message":"Match"},
            {"field":"Nationality",    "ocr_val":"INDIAN","mrz_val":"IND","match":True,"status":"PASS","message":"Consistent"},
            {"field":"Expiry Date",    "ocr_val":"14/03/2030","mrz_val":"14/03/2030","match":True,"status":"PASS","message":"Match"},
        ],
        "checksums_valid": True,
        "cross_valid": True,
        "summary": "MRZ present (TD3). All 4 ICAO check digits valid. OCR and MRZ fields are consistent.",
        "demo_mode": True,
    },
    "expired_document": {
        "status": "VALID",
        "mrz_present": True,
        "format": "TD3",
        "parsed": {
            "full_name": "PRIYA SINGH",
            "document_number": "Z1234567",
            "nationality": "IND",
            "date_of_birth": "22/11/1985",
            "sex": "F",
            "expiry_date": "09/06/2024",
            "checksums_valid": True,
        },
        "checks": [
            {"check_name":"Document Number Check Digit","status":"PASS","message":"Check digit '4' valid for document number 'Z1234567'"},
            {"check_name":"Date of Birth Check Digit",  "status":"PASS","message":"Check digit '2' valid for DOB '22/11/1985'"},
            {"check_name":"Expiry Date Check Digit",    "status":"PASS","message":"Check digit '1' valid for expiry '09/06/2024'"},
            {"check_name":"Composite Check Digit",      "status":"PASS","message":"Composite check digit valid"},
        ],
        "cross_validation": [
            {"field":"Document Number","ocr_val":"Z1234567","mrz_val":"Z1234567","match":True,"status":"PASS","message":"Match"},
            {"field":"Expiry Date","ocr_val":"09/06/2024","mrz_val":"09/06/2024","match":True,"status":"PASS","message":"Match — document is expired"},
        ],
        "checksums_valid": True,
        "cross_valid": True,
        "summary": "MRZ valid. Note: document is expired. The MRZ integrity is intact — expiry is an operational issue, not a forgery indicator.",
        "demo_mode": True,
    },
    "tampered_text": {
        "status": "NOT_DETECTED",
        "mrz_present": False,
        "format": None,
        "parsed": {},
        "checks": [
            {"check_name":"MRZ Detection","status":"FAIL",
             "message":"No MRZ lines detected. Genuine TD3 passports always contain a 2-line MRZ. Absence in a document identified as passport is a significant anomaly."},
        ],
        "cross_validation": [],
        "checksums_valid": False,
        "cross_valid": False,
        "summary": "MRZ not detected in this passport document. Absence is a significant anomaly requiring review.",
        "demo_mode": True,
    },
    "face_mismatch": {
        "status": "VALID",
        "mrz_present": True,
        "format": "TD3",
        "parsed": {
            "full_name": "AMIT VERMA",
            "document_number": "K5678901",
            "nationality": "IND",
            "date_of_birth": "30/07/1988",
            "sex": "M",
            "expiry_date": "04/01/2031",
            "checksums_valid": True,
        },
        "checks": [
            {"check_name":"Document Number Check Digit","status":"PASS","message":"Check digit '6' valid for document number 'K5678901'"},
            {"check_name":"Date of Birth Check Digit",  "status":"PASS","message":"Check digit '5' valid for DOB '30/07/1988'"},
            {"check_name":"Expiry Date Check Digit",    "status":"PASS","message":"Check digit '4' valid for expiry '04/01/2031'"},
            {"check_name":"Composite Check Digit",      "status":"PASS","message":"Composite check digit valid"},
        ],
        "cross_validation": [
            {"field":"Document Number","ocr_val":"K5678901","mrz_val":"K5678901","match":True,"status":"PASS","message":"Match"},
            {"field":"Date of Birth",  "ocr_val":"30/07/1988","mrz_val":"30/07/1988","match":True,"status":"PASS","message":"Match"},
        ],
        "checksums_valid": True,
        "cross_valid": True,
        "summary": "MRZ valid. Document integrity is intact. Risk comes from face mismatch only.",
        "demo_mode": True,
    },
    "multiple_flags": {
        "status": "NOT_DETECTED",
        "mrz_present": False,
        "format": None,
        "parsed": {},
        "checks": [
            {"check_name":"MRZ Detection","status":"WARNING",
             "message":"No MRZ detected. Some visa formats include MRZ; absence may indicate a non-standard format or image quality issue."},
        ],
        "cross_validation": [],
        "checksums_valid": False,
        "cross_valid": False,
        "summary": "MRZ not detected. Visa documents do not always include MRZ; absence alone is not a strong indicator for visa documents.",
        "demo_mode": True,
    },
    # Aadhaar cases — NOT_APPLICABLE
    "aadhaar_valid": {
        "status": "NOT_APPLICABLE",
        "mrz_present": False,
        "format": None,
        "parsed": {},
        "checks": [],
        "cross_validation": [],
        "checksums_valid": True,
        "cross_valid": True,
        "summary": "MRZ is not applicable for Aadhaar / national identity documents. QR code verification is the equivalent integrity check for Aadhaar cards.",
        "demo_mode": True,
    },
    "aadhaar_tampered": {
        "status": "NOT_APPLICABLE",
        "mrz_present": False,
        "format": None,
        "parsed": {},
        "checks": [],
        "cross_validation": [],
        "checksums_valid": True,
        "cross_valid": True,
        "summary": "MRZ is not applicable for Aadhaar / national identity documents.",
        "demo_mode": True,
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def run_mrz(ocr_result: dict, demo_case: str | None = None) -> dict:
    """
    Parse and validate MRZ.

    Returns a consistent result dict with a 'status' field that is always
    one of: NOT_APPLICABLE | NOT_DETECTED | UNREADABLE | VALID | PARTIAL | INVALID
    and never contradicts the 'checks' list.
    """
    # ── Demo mode ─────────────────────────────────────────────────────────────
    if demo_case:
        data = DEMO_MRZ.get(demo_case, DEMO_MRZ["valid_passport"])
        return {**data, "demo_mode": True}

    doc_type   = ocr_result.get("document_type", "unknown")
    ocr_fields = ocr_result.get("fields", [])
    raw_mrz    = ocr_result.get("raw_mrz")

    # ── Not applicable ────────────────────────────────────────────────────────
    if doc_type not in MRZ_APPLICABLE_TYPES:
        return {
            "status":          "NOT_APPLICABLE",
            "mrz_present":     False,
            "format":          None,
            "parsed":          {},
            "checks":          [],
            "cross_validation":[],
            "checksums_valid": True,   # N/A → not failing
            "cross_valid":     True,
            "summary":         (
                f"MRZ is not applicable for document type '{doc_type}'. "
                "MRZ checks are skipped."
            ),
            "demo_mode": False,
        }

    # ── MRZ not detected ─────────────────────────────────────────────────────
    if not raw_mrz:
        is_passport = doc_type == "passport"
        sev = "FAIL" if is_passport else "WARNING"
        return {
            "status":           "NOT_DETECTED",
            "mrz_present":      False,
            "format":           None,
            "parsed":           {},
            "checks":           [{
                "check_name": "MRZ Detection",
                "status":     sev,
                "message":    (
                    "No MRZ detected. Genuine ICAO TD3 passports always contain a two-line MRZ. "
                    "Absence in a passport document is a significant anomaly."
                    if is_passport else
                    "No MRZ detected. Some visa formats include MRZ; absence may indicate "
                    "a non-standard format or image quality issue."
                ),
            }],
            "cross_validation": [],
            "checksums_valid":  False,
            "cross_valid":      False,
            "summary":          (
                "MRZ not detected in this document."
            ),
            "demo_mode": False,
        }

    # ── Try parsing ───────────────────────────────────────────────────────────
    # Normalize lines: uppercase, strip everything outside the MRZ charset
    # (OCR often injects spaces, punctuation or lowercase characters).
    def _clean_mrz_line(l: str) -> str:
        return re.sub(r"[^A-Z0-9<]", "", l.strip().upper())

    lines = [_clean_mrz_line(l) for l in raw_mrz.strip().split("\n")]
    lines = [l for l in lines if l]
    try:
        if len(lines) >= 2 and lines[0].startswith("P<"):
            # TD3 passport: line 1 always starts with P< + issuing state.
            parsed = _parse_td3(lines[0], lines[1])
        elif len(lines) >= 3 and re.match(r"^[ACI]<", lines[0]):
            # TD1 ID card: line 1 starts with a TD1 document code.
            parsed = _parse_td1(lines[0], lines[1], lines[2])
        elif len(lines) == 1 and len(lines[0]) >= 60:
            # Both MRZ lines merged into one by OCR — split at 44 chars.
            parsed = _parse_td3(lines[0][:44], lines[0][44:])
        elif len(lines) >= 2 and len(lines[0]) >= 40:
            parsed = _parse_td3(lines[0], lines[1])
        elif len(lines) >= 3:
            parsed = _parse_td1(lines[0], lines[1], lines[2])
        elif len(lines) == 1 and len(lines[0]) >= 30:
            return {
                "status":           "UNREADABLE",
                "mrz_present":      True,
                "format":           "UNKNOWN",
                "parsed":           {},
                "checks":           [{
                    "check_name": "MRZ Format",
                    "status":     "WARNING",
                    "message":    f"Only one MRZ line detected ({len(lines[0])} chars). "
                                  "The second MRZ line is missing or unreadable — likely a scan-quality issue. "
                                  "Expected 2×44 (TD3) or 3×30 (TD1) characters.",
                }],
                "cross_validation": [],
                "checksums_valid":  False,
                "cross_valid":      False,
                "summary":          "MRZ detected but incomplete (only one line readable).",
                "demo_mode": False,
            }
        else:
            return {
                "status":           "UNREADABLE",
                "mrz_present":      True,
                "format":           "UNKNOWN",
                "parsed":           {},
                "checks":           [{
                    "check_name": "MRZ Format",
                    "status":     "WARNING",
                    "message":    f"MRZ detected but format not recognised (line lengths: {[len(l) for l in lines]}). "
                                  "Expected 2×44 (TD3) or 3×30 (TD1) characters.",
                }],
                "cross_validation": [],
                "checksums_valid":  False,
                "cross_valid":      False,
                "summary":          "MRZ detected but its format could not be recognised.",
                "demo_mode": False,
            }
    except Exception as e:
        logger.warning(f"MRZ parsing error: {e}")
        return {
            "status":           "UNREADABLE",
            "mrz_present":      True,
            "format":           "ERROR",
            "parsed":           {},
            "checks":           [{"check_name":"MRZ Parse","status":"WARNING","message":f"MRZ parse error: {e}"}],
            "cross_validation": [],
            "checksums_valid":  False,
            "cross_valid":      False,
            "summary":          "MRZ detected but parsing failed.",
            "demo_mode": False,
        }

    cross       = _cross_validate(parsed, ocr_fields)
    cross_valid = all(c["match"] for c in cross) if cross else True
    chk_valid   = parsed.get("checksums_valid", False)
    status      = parsed.get("status", "VALID")

    # Build consistent summary that MATCHES the checks list
    failed_chks = [c for c in parsed.get("checks",[]) if c["status"] == "FAIL"]
    mismatches  = [c for c in cross if not c["match"]]

    if status == "VALID" and cross_valid:
        summary = f"MRZ ({parsed.get('format')}) present and valid. All check digits pass. OCR/MRZ fields are consistent."
    elif status != "VALID":
        names = ", ".join(c["check_name"] for c in failed_chks[:3])
        summary = f"MRZ check digit failure(s): {names}. This indicates one or more fields may have been altered."
    else:
        flds = ", ".join(m["field"] for m in mismatches[:3])
        summary = f"MRZ checksums valid but OCR/MRZ mismatch in: {flds}. Visible text may differ from machine-readable data."

    return {
        "status":           status,
        "mrz_present":      True,
        "format":           parsed.get("format"),
        "parsed":           {k: v for k, v in parsed.items() if k not in ("checks","checksums_valid","status")},
        "checks":           parsed.get("checks", []),
        "cross_validation": cross,
        "checksums_valid":  chk_valid,
        "cross_valid":      cross_valid,
        "summary":          summary,
        "demo_mode":        False,
    }
