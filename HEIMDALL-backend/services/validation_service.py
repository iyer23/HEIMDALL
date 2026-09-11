"""
HEIMDALL — Document Validation Service
SIH 2026 · PS 26188

KEY RULES:
- Validation is document-type specific (Aadhaar checks ≠ passport checks).
- Expiry is a separate, clearly labelled check (NOT a forgery indicator).
- Failed checks are rule violations, not proof of fraud.
- Statuses: PASS | WARNING | FAIL | NOT_APPLICABLE
- MRZ Checksum check is REMOVED from validation — it belongs to mrz_service.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = s.strip().replace(".", "/").replace("-", "/")
    # "14 MAR 2030" / "14MAR30" style month names
    m = re.match(r"^(\d{1,2})\s*([A-Za-z]{3,4})\s*(\d{2,4})$", s)
    if m:
        mon = m.group(2).upper()[:3]
        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        if mon in months:
            try:
                y = int(m.group(3))
                y += 2000 if y < 100 else 0
                return date(y, months[mon], int(m.group(1)))
            except ValueError:
                return None
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%y", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def _chk(name: str, status: str, message: str, detail: str = "") -> dict:
    return {"check_name": name, "status": status, "message": message, "detail": detail}

def _get_field(fields: list[dict], label: str) -> Optional[str]:
    for f in fields:
        if f.get("label", "").lower() == label.lower():
            return f.get("value")
    return None


# ── Demo fixtures ─────────────────────────────────────────────────────────────

DEMO_VALIDATION: dict[str, dict] = {
    "valid_passport": {
        "checks": [
            _chk("Required Fields",      "PASS", "All required passport fields present"),
            _chk("Passport Number Format","PASS", "P8472613 — matches standard passport format (1 letter + 7 digits)"),
            _chk("Date of Birth",        "PASS", "12/05/1990 — valid, person is adult age"),
            _chk("Date of Issue",        "PASS", "15/03/2020 — valid issue date"),
            _chk("Expiry Date",          "PASS", "14/03/2030 — document is not expired"),
            _chk("Expiry after Issue",   "PASS", "Expiry (2030) is after issue date (2020)"),
            _chk("Nationality Format",   "PASS", "INDIAN — recognised nationality value"),
            _chk("Gender Field",         "PASS", "M — valid gender code"),
        ],
        "passed": 8, "warnings": 0, "failed": 0, "demo_mode": True,
    },
    "expired_document": {
        "checks": [
            _chk("Required Fields",      "PASS", "All required passport fields present"),
            _chk("Passport Number Format","PASS", "Z1234567 — valid format"),
            _chk("Date of Birth",        "PASS", "22/11/1985 — valid"),
            _chk("Date of Issue",        "PASS", "10/06/2014 — valid issue date"),
            _chk("Expiry Date",          "FAIL", "09/06/2024 — Document is EXPIRED",
                 "Document expired on 09 June 2024. Expiry is an operational issue and does not by itself indicate forgery."),
            _chk("Expiry after Issue",   "PASS", "Expiry is after issue date"),
            _chk("Nationality Format",   "PASS", "INDIAN — recognised"),
            _chk("Gender Field",         "PASS", "F — valid"),
        ],
        "passed": 7, "warnings": 0, "failed": 1, "demo_mode": True,
    },
    "tampered_text": {
        "checks": [
            _chk("Required Fields",       "PASS",    "All fields present"),
            _chk("Passport Number Format","WARNING",  "A9876543 — format valid but OCR confidence is low (51%)",
                 "Low extraction confidence on this field. Could reflect poor print quality or image editing."),
            _chk("Date of Birth",         "WARNING",  "01/01/1995 — valid date but OCR confidence low (62%)",
                 "Date is parseable but OCR confidence is below normal. Field may be difficult to read."),
            _chk("Date of Issue",         "PASS",     "20/08/2022 — valid"),
            _chk("Expiry Date",           "PASS",     "19/08/2032 — not expired"),
            _chk("Expiry after Issue",    "PASS",     "Expiry after issue date"),
            _chk("Nationality Format",    "PASS",     "INDIAN — valid"),
            _chk("Gender Field",          "PASS",     "M — valid"),
        ],
        "passed": 6, "warnings": 2, "failed": 0, "demo_mode": True,
    },
    "face_mismatch": {
        "checks": [
            _chk("Required Fields",      "PASS", "All fields present"),
            _chk("Passport Number Format","PASS", "K5678901 — valid format"),
            _chk("Date of Birth",        "PASS", "30/07/1988 — valid"),
            _chk("Date of Issue",        "PASS", "05/01/2021 — valid"),
            _chk("Expiry Date",          "PASS", "04/01/2031 — not expired"),
            _chk("Expiry after Issue",   "PASS", "Expiry after issue date"),
            _chk("Nationality Format",   "PASS", "INDIAN — recognised"),
            _chk("Gender Field",         "PASS", "M — valid"),
        ],
        "passed": 8, "warnings": 0, "failed": 0, "demo_mode": True,
    },
    "aadhaar_valid": {
        "checks": [
            _chk("Required Fields",    "PASS",    "Name, DOB, Gender, Address, Issuing Authority all present"),
            _chk("Aadhaar Number",     "PASS",    "XXXX XXXX 4821 — masked 12-digit format valid"),
            _chk("Date of Birth",      "PASS",    "14/08/1998 — valid, person is adult"),
            _chk("Gender Field",       "PASS",    "MALE — valid"),
            _chk("Issuing Authority",  "PASS",    "UIDAI — Government of India authority"),
            _chk("Address Present",    "PASS",    "Address field detected"),
            _chk("VID Present",        "PASS",    "Virtual ID present and 16-digit format valid"),
            _chk("QR Code",            "WARNING", "QR code offline verification not possible via image upload",
                 "QR code scan requires an authorised scanner device. Visual document analysis only."),
        ],
        "passed": 7, "warnings": 1, "failed": 0, "demo_mode": True,
    },
    "aadhaar_tampered": {
        "checks": [
            _chk("Required Fields",    "WARNING", "VID field not detected in this document image"),
            _chk("Aadhaar Number",     "WARNING", "XXXX XXXX 0001 — low OCR confidence (44.7%) on number field",
                 "Aadhaar suffix unusually simple (0001). Very low OCR confidence may indicate image quality issue or editing."),
            _chk("Date of Birth",      "WARNING", "01/01/2000 — low OCR confidence (51.3%)",
                 "Date is parseable but OCR confidence is very low. Could reflect poor print quality."),
            _chk("Gender Field",       "PASS",    "MALE — valid"),
            _chk("Issuing Authority",  "PASS",    "UIDAI — present"),
            _chk("Address Present",    "FAIL",    "Address field contains non-specific value ('UNKNOWN ADDRESS, DELHI')",
                 "Address value does not match typical genuine Aadhaar address format."),
            _chk("VID Present",        "FAIL",    "VID field not detected — field may have been removed or cropped"),
            _chk("QR Code",            "FAIL",    "QR code region appears absent or unreadable",
                 "Genuine Aadhaar cards always contain a UIDAI QR code. Absence is a significant indicator."),
        ],
        "passed": 2, "warnings": 3, "failed": 3, "demo_mode": True,
    },
    "multiple_flags": {
        "checks": [
            _chk("Required Fields",    "FAIL",    "Multiple required visa fields are absent or unrecognised"),
            _chk("Visa Number Format", "FAIL",    "VIS-9999-XX — non-standard format; recognised visa number formats differ",
                 "Standard visa numbers use country-code + numeric sequence."),
            _chk("Valid From Date",    "PASS",    "01/01/2020 — parseable date"),
            _chk("Expiry Date",        "FAIL",    "31/12/2021 — Visa EXPIRED over 2 years ago",
                 "Visa expired 31 December 2021. This is an operational expiry issue, not necessarily forgery."),
            _chk("Issuing Country",    "FAIL",    "UNKNOWN — not a recognised ISO country code",
                 "Issuing country field contains an unrecognised value."),
        ],
        "passed": 1, "warnings": 0, "failed": 4, "demo_mode": True,
    },
}


# ── Real validation ───────────────────────────────────────────────────────────

def _validate_real(ocr_result: dict) -> dict:
    checks  = []
    fields  = ocr_result.get("fields", [])
    doc_type= ocr_result.get("document_type", "unknown")
    today   = date.today()

    # ── UNKNOWN document type: skip field-specific validation ─────────────────
    if doc_type in ("unknown", "unsupported"):
        checks.append(_chk(
            "Document type validation",
            "WARNING",
            "Document type could not be determined — document-specific field validation was not performed.",
            "Only generic checks are applied for unknown document types.",
        ))
        return {"checks": checks, "passed": 0, "warnings": 1, "failed": 0}

    # ── Required fields by type ───────────────────────────────────────────────
    required_map = {
        "passport":        ["Full Name", "Passport Number", "Nationality", "Date of Birth", "Date of Expiry"],
        "visa":            ["Full Name", "Visa Number", "Valid Until"],
        "national_id":     ["Full Name", "Date of Birth", "Gender"],
        "driving_licence": ["Full Name", "Date of Expiry"],
        "pan_card":        ["Full Name", "PAN Number", "Date of Birth"],
        "voter_id":        ["Full Name", "Voter ID Number"],
    }
    # Aadhaar-specific
    is_aadhaar = any(f.get("label") == "Aadhaar Number" for f in fields)
    if doc_type == "national_id" and is_aadhaar:
        required_map["national_id"] = ["Full Name", "Aadhaar Number", "Date of Birth", "Gender", "Issuing Authority"]

    required = required_map.get(doc_type, ["Full Name"])
    missing  = [r for r in required if not _get_field(fields, r)]
    if missing:
        checks.append(_chk("Required Fields", "WARNING",
                           f"Missing or undetected: {', '.join(missing)}",
                           "Some expected fields could not be extracted from the image."))
    else:
        checks.append(_chk("Required Fields", "PASS", "All required fields detected"))

    # ── Document-type-specific format checks ──────────────────────────────────
    if doc_type == "passport":
        pnum = _get_field(fields, "Passport Number")
        if pnum and re.match(r"^[A-Z]\d{7,8}$", pnum.strip()):
            checks.append(_chk("Passport Number Format", "PASS", f"{pnum} — standard format"))
        elif pnum:
            checks.append(_chk("Passport Number Format", "WARNING",
                               f"{pnum} — unexpected format (expected 1 letter + 7-8 digits)"))
        else:
            checks.append(_chk("Passport Number Format", "FAIL", "Passport number not detected"))

    if doc_type == "national_id" and is_aadhaar:
        anum = _get_field(fields, "Aadhaar Number")
        if anum and re.match(r"^(XXXX XXXX \d{4}|\d{4} \d{4} \d{4})$", anum.strip()):
            checks.append(_chk("Aadhaar Number Format", "PASS", f"{anum} — 12-digit masked format valid"))
        elif anum:
            checks.append(_chk("Aadhaar Number Format", "WARNING",
                               f"{anum} — unexpected format"))
        else:
            checks.append(_chk("Aadhaar Number Format", "FAIL", "Aadhaar number not detected"))

        authority = _get_field(fields, "Issuing Authority")
        if authority and "UIDAI" in authority.upper():
            checks.append(_chk("Issuing Authority", "PASS", "UIDAI — Government of India"))
        else:
            checks.append(_chk("Issuing Authority", "WARNING", "Issuing authority not detected or unrecognised"))

        address = _get_field(fields, "Address")
        if address:
            checks.append(_chk("Address Present", "PASS", "Address field detected"))
        else:
            checks.append(_chk("Address Present", "WARNING", "Address field not detected in image"))

        checks.append(_chk("QR Code", "WARNING",
                           "QR code offline verification not possible via image upload",
                           "QR verification requires an authorised scanner."))

    # ── Date of Birth ─────────────────────────────────────────────────────────
    dob_str = _get_field(fields, "Date of Birth")
    dob     = _parse_date(dob_str)
    if dob_str and not dob:
        checks.append(_chk("Date of Birth", "WARNING", f"Could not parse date: '{dob_str}'"))
    elif dob:
        if dob > today:
            checks.append(_chk("Date of Birth", "FAIL", f"{dob_str} — date is in the future (impossible)"))
        elif (today - dob).days < 365 * 1:
            checks.append(_chk("Date of Birth", "WARNING", f"{dob_str} — person would be under 1 year old"))
        else:
            checks.append(_chk("Date of Birth", "PASS", f"{dob_str} — valid"))

    # ── Expiry (clearly labelled as operational issue, not forgery) ───────────
    exp_str = _get_field(fields, "Date of Expiry") or _get_field(fields, "Valid Until")
    exp     = _parse_date(exp_str)
    if exp_str and not exp:
        checks.append(_chk("Expiry Date", "WARNING", f"Could not parse expiry date: '{exp_str}'"))
    elif exp:
        days_left = (exp - today).days
        if days_left < 0:
            checks.append(_chk("Expiry Date", "FAIL",
                               f"{exp_str} — document EXPIRED {abs(days_left)} day(s) ago",
                               "An expired document cannot be accepted for entry. "
                               "Expiry alone does not indicate forgery."))
        elif days_left < 30:
            checks.append(_chk("Expiry Date", "WARNING",
                               f"{exp_str} — expires in {days_left} day(s)",
                               "Document will expire very soon. Many authorities require 6 months' validity."))
        elif days_left < 180:
            checks.append(_chk("Expiry Date", "WARNING",
                               f"{exp_str} — expires in {days_left // 30} month(s)",
                               "Some authorities require at least 6 months of remaining validity."))
        else:
            checks.append(_chk("Expiry Date", "PASS", f"{exp_str} — valid, not expired"))

    # ── Issue before expiry ───────────────────────────────────────────────────
    issue_str = _get_field(fields, "Date of Issue")
    issue     = _parse_date(issue_str)
    if issue and exp:
        if exp <= issue:
            checks.append(_chk("Expiry after Issue", "FAIL",
                               "Expiry date is not after issue date — logically impossible"))
        elif issue > today:
            checks.append(_chk("Expiry after Issue", "FAIL",
                               f"Issue date {issue_str} is in the future — impossible"))
        else:
            checks.append(_chk("Expiry after Issue", "PASS", "Expiry is after issue date"))

    # ── Nationality / issuing country ─────────────────────────────────────────
    nat = _get_field(fields, "Nationality")
    if nat and re.match(r"^[A-Z]{2,20}$", nat.strip()):
        checks.append(_chk("Nationality Format", "PASS", f"{nat} — valid format"))

    passed   = sum(1 for c in checks if c["status"] == "PASS")
    warnings = sum(1 for c in checks if c["status"] == "WARNING")
    failed   = sum(1 for c in checks if c["status"] == "FAIL")

    return {"checks": checks, "passed": passed, "warnings": warnings, "failed": failed}


# ── Public API ────────────────────────────────────────────────────────────────

def run_validation(ocr_result: dict, demo_case: Optional[str] = None) -> dict:
    if demo_case:
        data = DEMO_VALIDATION.get(demo_case, DEMO_VALIDATION["valid_passport"])
        return {**data, "demo_mode": True}
    try:
        result = _validate_real(ocr_result)
        return {**result, "demo_mode": False}
    except Exception as e:
        return {
            "checks":   [_chk("Validation Engine", "WARNING", f"Validation error: {e}")],
            "passed":   0, "warnings": 1, "failed": 0,
            "demo_mode": False,
        }
