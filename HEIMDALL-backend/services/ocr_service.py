"""
HEIMDALL — OCR Service
SIH 2026 · PS 26188

KEY RULES:
- NEVER return fabricated data for real uploaded documents.
- Demo fixtures are ONLY used when demo_case is explicitly set.
- On real OCR failure → return INCONCLUSIVE result (no invented values).
- Multi-signal document type scoring (not single keyword).
- Confidence reported as percentage (0-100) from engine average.
"""
from __future__ import annotations
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("heimdall.ocr")

# ── Lazy EasyOCR loader ───────────────────────────────────────────────────────
_reader     = None
_reader_tried = False

def _get_reader():
    global _reader, _reader_tried
    if not _reader_tried:
        _reader_tried = True
        try:
            import easyocr
            # "en" only: recognition runs once per box (en+hi ran it twice — 2x cost).
            # ID fields (names, numbers, dates) are latin/digits.
            _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR reader loaded (en).")
        except Exception as e:
            logger.warning(f"EasyOCR unavailable: {e}")
            _reader = None
    return _reader


def _preprocess(image_path: Path):
    """
    Preprocess for OCR: upscale small images 2x, grayscale + CLAHE contrast + deskew.
    Returns a numpy array (BGR/grayscale) ready for EasyOCR, or None on failure.
    """
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if max(h, w) < 1500:
            scale = max(2.0, 1500 / max(h, w))
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # Deskew: rotate slightly-skewed scans so text lines are horizontal.
        try:
            gray_d = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray_d, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                                    minLineLength=min(h, w) // 3, maxLineGap=10)
            if lines is not None:
                angles = []
                for x1, y1, x2, y2 in lines[:, 0]:
                    if x2 == x1:
                        continue
                    a = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                    if a < 15:  # only near-horizontal text lines
                        angles.append(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                if angles:
                    angle = float(np.median(angles))
                    if abs(angle) > 0.3:
                        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                                             borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            pass
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)
    except Exception as e:
        logger.warning(f"Preprocess failed ({e}); using original image.")
        return None


def _mrz_crop(image_path: Path):
    """
    Crop the bottom ~35% of the document (where the MRZ usually sits), upscale
    and enhance it. Used for a dedicated MRZ-targeted OCR pass, or None on failure.
    """
    try:
        import cv2
        img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        crop = img[int(h * 0.65):, :]
        if crop.size == 0:
            return None
        scale = max(2.0, 2000 / max(crop.shape[:2]))
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
    except Exception:
        return None


# ── INCONCLUSIVE result for real-upload failures ──────────────────────────────
def _inconclusive(reason: str) -> dict:
    return {
        "document_type":     "unknown",
        "document_type_confidence": 0.0,
        "overall_confidence": 0.0,
        "ocr_available":     False,
        "fields":            [],
        "raw_mrz":           None,
        "demo_mode":         False,
        "error":             reason,
    }


# ── Multi-signal document type scoring ───────────────────────────────────────

def _classify_document(text: str, raw_results: list) -> tuple[str, float]:
    """
    Score each document type using multiple independent signals.
    Returns (doc_type, confidence_0_to_1).
    Never relies on a single keyword.
    """
    t = text.upper()
    t_norm = t.replace(" ", "").replace("_", "")
    scores: dict[str, float] = {
        "passport":        0.0,
        "visa":            0.0,
        "driving_licence": 0.0,
        "national_id":     0.0,
        "pan_card":        0.0,
        "voter_id":        0.0,
    }

    # ── Passport signals ──────────────────────────────────────────────────────
    if "PASSPORT" in t:                        scores["passport"] += 0.45
    if re.search(r"P<[A-Z]{3}", t):            scores["passport"] += 0.40  # TD3 MRZ prefix
    if "P<" in t:                              scores["passport"] += 0.20  # MRZ prefix (partial OCR)
    if "MACHINE READABLE" in t:                scores["passport"] += 0.12
    if "TRAVEL DOCUMENT" in t:                 scores["passport"] += 0.15
    if "REPUBLIC OF INDIA" in t:               scores["passport"] += 0.15
    if "NATIONALITY" in t and "NATIONALITY" not in "NATIONAL IDENTITY": scores["passport"] += 0.12
    if re.search(r"\b[A-Z]\d{7,8}\b", t):     scores["passport"] += 0.12  # passport number pattern
    if "DATE OF ISSUE" in t:                   scores["passport"] += 0.08
    if "DATE OF EXPIRY" in t:                  scores["passport"] += 0.08
    if "PLACE OF BIRTH" in t:                  scores["passport"] += 0.06
    if "GIVEN NAME" in t or "SURNAME" in t:    scores["passport"] += 0.10

    # ── Visa signals ──────────────────────────────────────────────────────────
    if "VISA" in t:                            scores["visa"] += 0.50
    if "VALID FOR" in t:                       scores["visa"] += 0.18
    if "ENTRIES" in t:                         scores["visa"] += 0.18
    if "DURATION OF STAY" in t:               scores["visa"] += 0.18
    if "EMBASSY" in t or "CONSULATE" in t:    scores["visa"] += 0.12
    if "ISSUING POST" in t:                    scores["visa"] += 0.12
    if "VISA NUMBER" in t or "VISA NO" in t:  scores["visa"] += 0.15
    if re.search(r"V<[A-Z]{3}", t):            scores["visa"] += 0.35  # TD3 visa MRZ prefix

    # ── Driving Licence signals ───────────────────────────────────────────────
    if "DRIVING LICENCE" in t or "DRIVING LICENSE" in t:  scores["driving_licence"] += 0.55
    if re.search(r"\bDL[\s\-]?NO\b|\bDL\s*NUMBER\b", t): scores["driving_licence"] += 0.30
    if "TRANSPORT AUTHORITY" in t:                         scores["driving_licence"] += 0.18
    if "VEHICLE CLASS" in t or "COV" in t:                scores["driving_licence"] += 0.15
    if "MOTOR VEHICLE" in t:                               scores["driving_licence"] += 0.12
    if "LICENCE NO" in t or "LICENSE NO" in t:            scores["driving_licence"] += 0.12
    if "RTO" in t:                                         scores["driving_licence"] += 0.12
    if re.search(r"\bLMV\b|\bMCWG\b|\bMCWOG\b|\bLMV-NT\b", t): scores["driving_licence"] += 0.18
    # Indian DL number: e.g. MH12 20110001234 / KA-05-2019-0001234
    if re.search(r"\b[A-Z]{2}[\s\-]?\d{2}[\s\-]?(19|20)\d{2}[\s\-]?\d{6,8}\b", t):
        scores["driving_licence"] += 0.25

    # ── National ID / Aadhaar signals ─────────────────────────────────────────
    if "AADHAAR" in t or "AADHAR" in t or "EAADHAAR" in t:  scores["national_id"] += 0.55
    if "UIDAI" in t:                                       scores["national_id"] += 0.55
    if "UNIQUE IDENTIFICATION" in t:                      scores["national_id"] += 0.45
    if "GOVERNMENT OF INDIA" in t:                         scores["national_id"] += 0.15
    if re.search(r"\b\d{4}\s+\d{4}\s+\d{4}\b", t):       scores["national_id"] += 0.35  # 12-digit pattern
    if "YEAR OF BIRTH" in t:                               scores["national_id"] += 0.12
    if re.search(r"\b\d{16}\b", t):                        scores["national_id"] += 0.15
    if "ENROLLMENT" in t or "ENROLMENT" in t:             scores["national_id"] += 0.12
    if "MY AADHAAR" in t or "E-AADHAAR" in t:             scores["national_id"] += 0.25
    # Fuzzy fragments: OCR garbles of "Aadhaar"/"UIDAI"/"Adhar" on low-quality scans
    if re.search(r"A[A-Z]{0,1}D[H]?A{1,2}[RSA]{1,2}", t): scores["national_id"] += 0.35
    if "UIDAI" in t_norm or "UIDAI" in t:                  scores["national_id"] += 0.15
    if "INDIA" in t and re.search(r"\b(MALE|FEMALE)\b", t) and re.search(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", t):
        scores["national_id"] += 0.15  # layout: Indian gov card with DOB + gender

    # ── PAN card signals ──────────────────────────────────────────────────────
    if "PERMANENT ACCOUNT" in t or "PERMANENTACCOUNT" in t_norm: scores["pan_card"] += 0.60
    if "INCOME TAX" in t or "INCOMETAX" in t_norm:               scores["pan_card"] += 0.50
    if "INCOME TAX DEPARTMENT" in t:                             scores["pan_card"] += 0.30
    if "PERMANENT ACCOUNT NUMBER" in t:                          scores["pan_card"] += 0.30
    # PAN number pattern: ABCDE1234F
    if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", t):              scores["pan_card"] += 0.40
    if "FATHER" in t:                                            scores["pan_card"] += 0.15
    if "FATHER'S NAME" in t or "FATHERS NAME" in t:             scores["pan_card"] += 0.20
    if "Date of Birth" in text.upper() and "INCOME" in t:        scores["pan_card"] += 0.15
    if "अपना" in text or "APNA" in t_norm:                      scores["pan_card"] += 0.15
    if "स्थायी" in text:                                        scores["pan_card"] += 0.20

    # ── Voter ID (EPIC) signals ───────────────────────────────────────────────
    if "ELECTION COMMISSION" in t or "ELECTIONCOMMISSION" in t_norm: scores["voter_id"] += 0.60
    if "ELECTION" in t:                                              scores["voter_id"] += 0.40
    if "ELECTOR" in t or "ELECTORAL" in t:                          scores["voter_id"] += 0.40
    if "EPIC" in t_norm and "EPIC" in t:                             scores["voter_id"] += 0.40
    if "PHOTO IDENTITY" in t or "PHOTOIDENTITY" in t_norm:          scores["voter_id"] += 0.30
    if "IDENTITY CARD" in t or "IDENTITYCARD" in t_norm:            scores["voter_id"] += 0.20
    if "CONSTITUENCY" in t:                                          scores["voter_id"] += 0.25
    if "POLLING" in t or "BOOTH" in t:                              scores["voter_id"] += 0.20
    if re.search(r"\b[A-Z]{3}[0-9]{7}\b", t):                       scores["voter_id"] += 0.40  # EPIC number
    if "चुनाव" in text:                                             scores["voter_id"] += 0.25

    best_type  = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    # Minimum signal threshold — below 0.25 = unknown
    if best_score < 0.25:
        return "unknown", round(min(0.20, best_score), 3)

    # Confidence: cap at 0.99, scale so 0.5 → ~0.70, 1.0 → 0.99
    confidence = round(min(0.99, best_score * 0.85 + 0.15), 3)
    return best_type, confidence


# ── Field extraction per document type ───────────────────────────────────────

def _field(label: str, value: Optional[str], confidence: float, flagged: bool = False) -> dict:
    return {
        "label":     label,
        "value":     value if value else None,
        "confidence": round(confidence, 1),
        "detected":  value is not None and value.strip() != "",
        "flagged":   flagged,
    }


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


# ── Robust date handling ─────────────────────────────────────────────────────
MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "SEPT": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

def _date_corpus(text: str) -> str:
    """Join digits/dates split across line breaks or stray spaces (common OCR artifact)."""
    c = re.sub(r"(\d)[\s\n]+(\d)", r"\1\2", text)
    c = re.sub(r"([/\-.])\s*\n\s*(\d)", r"\1\2", c)
    return c

DATE_PAT = (
    r"(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4}"          # 14/03/2030, 14-03-30, 14.03.2030
    r"|\d{4}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{1,2}"            # 2030-03-14 (ISO-ish)
    r"|\d{1,2}\s*[ ]?(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?\s*[ ]?\d{2,4}"
    r"|\d{4})"                                                  # bare year (YYYY of birth)
)

def _norm_date(raw: str) -> str:
    """Normalise any detected date to DD/MM/YYYY (or YYYY for bare years)."""
    s = re.sub(r"\s+", "", raw).upper()
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s)
    if m:
        d, mo, y = m.groups()
        y = int(y)
        y += 2000 if y < 100 else 0
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    m = re.match(r"^(\d{1,2})[ ]?(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?[ ]?(\d{2,4})$", s)
    if m:
        d, mon, y = m.groups()
        y = int(y)
        y += 2000 if y < 100 else 0
        return f"{int(d):02d}/{MONTHS[mon]}/{y}"
    if re.match(r"^\d{4}$", s):
        return s
    return raw.strip()

def _find_date(text: str) -> Optional[str]:
    """Find and normalise the first date-like string in text."""
    corpus = _date_corpus(text)
    m = re.search(DATE_PAT, corpus, re.IGNORECASE)
    return _norm_date(m.group(1)) if m else None

def _find_full_date(text: str) -> Optional[str]:
    """Find the first complete DD/MM/YYYY date, even when its label is garbled."""
    corpus = _date_corpus(text)
    for m in re.finditer(r"\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4}", corpus):
        return _norm_date(m.group(0))
    return None

def _labelled_date(text: str, labels: str) -> Optional[str]:
    """Find a date following one of the given pipe-separated labels."""
    corpus = _date_corpus(text)
    m = re.search(rf"(?:{labels})\s*[:\-]?\s*({DATE_PAT[1:-1]})", corpus, re.IGNORECASE)
    if not m:
        return None
    return _norm_date(m.group(1))


# Non-name header/footer lines that OCR often picks up as "Full Name"
_NAME_BLOCKLIST = (
    "GOVERNMENT", "INDIA", "BHARAT", "UIDAI", "AADHAAR", "AADHAR", "आधार",
    "UNIQUE IDENTIFICATION", "ENROLLMENT", "ENROLMENT", "MALE", "FEMALE",
    "STATE", "REPUBLIC", "DOWNLOAD", "VALID", "DOB", "PRINT", "VID",
    # fuzzy fragments: OCR misreads of the Aadhaar logo / header words
    "ADHAA", "ADHAR", "SARKAR", "SERKAR",
    "ACCOUNT", "CARD", "PERMANENT", "DEPARTMENT", "TAX", "APNA", "EPIC",
)

def _clean_name_candidate(cand: Optional[str]) -> Optional[str]:
    """Reject OCR lines that are headers/labels rather than a person's name."""
    if not cand:
        return None
    s = cand.strip().strip(":").strip()
    up = s.upper()
    if len(s.split()) < 2:
        return None
    if any(b in up for b in _NAME_BLOCKLIST):
        return None
    return s


def _extract_aadhaar_fields(text: str, raw: list) -> list[dict]:
    """Extract Aadhaar/national ID specific fields only. No passport fields."""
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}

    def conf_for(value: Optional[str]) -> float:
        if not value:
            return 0.0
        return conf_map.get(value, 72.0)

    # Name: first person-name-like line, skipping government headers/labels.
    # NOTE: use [ ] not \s inside the class so a candidate can never span lines.
    name = None
    for cand in re.findall(r"(?:^|\n)\s*([A-Z][A-Za-z .]{3,40})(?=\n|$)", text):
        for line in cand.split("\n"):
            cleaned = _clean_name_candidate(line)
            if cleaned:
                name = cleaned
                break
        if name:
            break
    dob    = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH|YEAR\s*OF\s*BIRTH|YOB")
    if not dob:
        # Label often garbled by OCR on low-quality scans — fall back to any full date.
        dob = _find_full_date(text)
    gender = _search(r"\b(FEMALE|MALE)\b", text) or _search(r"(?:GENDER|SEX)\s*[:\-]?\s*([MF])\b", text)
    if gender:
        g = gender.upper()
        gender = "FEMALE" if g.startswith("F") else ("MALE" if g.startswith("M") else gender)
    # 12-digit Aadhaar number (or masked "XXXX XXXX 4821" as printed on many
    # cards): tolerant of OCR spacing variants, plus a per-line digit-squeeze
    # fallback when the groups are split across columns.
    aadhaar_raw = _search(
        r"\b((?:\d{4}|[Xx]{4})[\s\-]*[\s\n]*(?:\d{4}|[Xx]{4})[\s\-]*[\s\n]*\d{4})\b", text
    )
    if not aadhaar_raw:
        for line in text.split("\n"):
            tokens = re.findall(r"\d{4}|[Xx]{4}", line)
            if len(tokens) == 3:
                aadhaar_raw = " ".join(tokens)
                break
    # Hindi/Devanagari digits often sneak in from bilingual labels (e.g. ४२ -> 42)
    aadhaar_raw = aadhaar_raw.translate(str.maketrans("०१२३४५६७८९", "0123456789")) if aadhaar_raw else None
    aadhaar_masked = None
    if aadhaar_raw:
        parts = aadhaar_raw.split()
        aadhaar_masked = f"XXXX XXXX {parts[2]}" if len(parts) == 3 else aadhaar_raw
    vid        = _search(r"VID[:\s]*(\d{4}\s+\d{4}\s+\d{4}\s+\d{4})", text)
    authority  = _search(r"(UIDAI|Unique Identification Authority of India)", text)
    address    = _search(r"(?:Address|S/O|C/O|W/O|D/O|H/O)[:\s]*(.{10,100}?)(?=\n|$)", text, re.MULTILINE)

    return [
        _field("Full Name",        name,           conf_for(name) if name else 0.0),
        _field("Aadhaar Number",   aadhaar_masked, 95.0 if aadhaar_masked else 0.0),
        _field("Date of Birth",    dob,            conf_for(dob) if dob else 0.0),
        _field("Gender",           gender,         conf_for(gender) if gender else 0.0),
        _field("Address",          address,        conf_for(address) if address else 0.0),
        _field("VID",              vid,            90.0 if vid else 0.0),
        _field("Issuing Authority", authority,     99.0 if authority else 0.0),
    ]


def _extract_passport_fields(text: str, raw: list) -> list[dict]:
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}

    def conf_for(value: Optional[str]) -> float:
        if not value:
            return 0.0
        return conf_map.get(value, 75.0)

    # Name: label-anchored first; strip trailing label words that greedy regex may swallow.
    name = _search(r"(?:NAME|GIVEN\s+NAME|SURNAME)[:\s]+([A-Z][A-Z\s]{2,})", text)
    if name:
        name = re.split(r"\b(?:NATIONALITY|PASSPORT|DATE|SEX|GENDER|PLACE|BIRTH)\b", name)[0].strip()
    if not name:
        for cand in re.findall(r"(?:^|\n)\s*([A-Z][A-Z\s.]{3,40})(?=\n|$)", text):
            cleaned = _clean_name_candidate(cand)
            if cleaned:
                name = cleaned
                break
    pnum    = _search(r"\b([A-Z]\d{7,8})\b", text)
    nat     = _search(r"(?:NATIONALITY)[:\s]*([A-Z]{3,20})", text)
    dob     = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH|BIRTH\s*DATE")
    # NOTE: expiry labels deliberately excluded here so the issue date never
    # picks up the expiry date when the issue label is garbled.
    doi     = _labelled_date(text, r"DATE\s*OF\s*ISSUE|ISSUE\s*DATE|DATE\s*ISSUED")
    doe     = _labelled_date(text, r"DATE\s*OF\s*EXPIRY|EXPIRY|EXPIRATION|EXPIRES?|DATE\s*OF\s*EXPIRE|VALID\s*UNTIL|VALID\s*TILL|VALID\s*UPTO")
    gender  = _search(r"\b(?:SEX|GENDER)\s*[:\-/]*\s*([MF])\b", text) or _search(r"\b(FEMALE|MALE)\b", text)
    if gender:
        g = gender.upper()
        gender = "M" if g.startswith("M") else ("F" if g.startswith("F") else gender)
    country = _search(r"(?:COUNTRY OF BIRTH|ISSUING COUNTRY|ISSUED BY|COUNTRY)[:\s]*([A-Z]{3,20})", text)
    pob     = _search(r"(?:PLACE OF BIRTH)[:\s]*([A-Z][A-Z\s]{2,30})", text)

    return [
        _field("Full Name",       name,   conf_for(name) if name else 0.0),
        _field("Passport Number", pnum,   conf_for(pnum) if pnum else 0.0,  flagged=(bool(pnum) and conf_for(pnum) < 60)),
        _field("Nationality",     nat,    conf_for(nat) if nat else 0.0),
        _field("Date of Birth",   dob,    conf_for(dob) if dob else 0.0,    flagged=(bool(dob) and conf_for(dob) < 60)),
        _field("Date of Issue",   doi,    conf_for(doi) if doi else 0.0),
        _field("Date of Expiry",  doe,    conf_for(doe) if doe else 0.0),
        _field("Gender",          gender, conf_for(gender) if gender else 0.0),
        _field("Issuing Country", country,conf_for(country) if country else 0.0),
        _field("Place of Birth",  pob,    conf_for(pob) if pob else 0.0),
    ]


def _extract_visa_fields(text: str, raw: list) -> list[dict]:
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}
    def conf_for(v): return conf_map.get(v, 72.0) if v else 0.0

    vnum    = _search(r"(?:VISA\s*(?:NUMBER|NO))[:\s]*([A-Z0-9/\-]{4,20})", text)
    name    = _search(r"(?:NAME|SURNAME)[:\s]+([A-Z][A-Z\s]{2,})", text)
    nat     = _search(r"(?:NATIONALITY)[:\s]*([A-Z]{3,20})", text)
    dob     = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH")
    vfrom   = _labelled_date(text, r"VALID\s*FROM|FROM\s*DATE|DATE\s*OF\s*ISSUE|ISSUE\s*DATE")
    vuntil  = _labelled_date(text, r"VALID\s*UNTIL|VALID\s*TO|EXPIRY|EXPIRATION|EXPIRES?|VALID\s*TILL|VALID\s*UPTO")
    vtype   = _search(r"(?:VISA\s*TYPE|TYPE)[:\s]*([A-Z][A-Z\s]{1,20})", text)
    entries = _search(r"(?:ENTRIES|ENTRY)[:\s]*([A-Z0-9\s]{1,10})", text)
    dur     = _search(r"(?:DURATION|STAY)[:\s]*(\d+\s*DAYS?|\d+\s*MONTHS?)", text)

    return [
        _field("Visa Number",   vnum,    conf_for(vnum)),
        _field("Full Name",     name,    conf_for(name)),
        _field("Nationality",   nat,     conf_for(nat)),
        _field("Date of Birth", dob,     conf_for(dob)),
        _field("Valid From",    vfrom,   conf_for(vfrom)),
        _field("Valid Until",   vuntil,  conf_for(vuntil)),
        _field("Visa Type",     vtype,   conf_for(vtype)),
        _field("Entries",       entries, conf_for(entries)),
        _field("Stay Duration", dur,     conf_for(dur)),
    ]


def _extract_dl_fields(text: str, raw: list) -> list[dict]:
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}
    def conf_for(v): return conf_map.get(v, 72.0) if v else 0.0

    name    = _search(r"(?:NAME|S/O|D/O|W/O)[:\s]+([A-Z][A-Z\s]{2,})", text)
    dlnum   = _search(r"(?:DL\s*NO|DL\s*NUMBER|LICENCE\s*NO|LICENSE\s*NO)[:\s]*([A-Z0-9/\-]{8,20})", text)
    dob     = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH")
    doi     = _labelled_date(text, r"ISSUE\s*DATE|ISSUED\s*ON|DATE\s*OF\s*ISSUE")
    doe     = _labelled_date(text, r"VALID\s*TILL|EXPIRY|EXPIRATION|EXPIRES?|VALID\s*UPTO|VALID\s*UNTIL")
    cov     = _search(r"(?:COV|CLASS OF VEHICLE|VEHICLE CLASS)[:\s]*([A-Z0-9,\s]{2,30})", text)
    auth    = _search(r"(?:ISSUED BY|AUTHORITY|RTO|LICENSING AUTHORITY)[:\s]*([A-Z][A-Z\s]{2,40})", text)

    return [
        _field("Full Name",        name,  conf_for(name)),
        _field("Licence Number",   dlnum, conf_for(dlnum)),
        _field("Date of Birth",    dob,   conf_for(dob)),
        _field("Date of Issue",    doi,   conf_for(doi)),
        _field("Date of Expiry",   doe,   conf_for(doe)),
        _field("Vehicle Classes",  cov,   conf_for(cov)),
        _field("Issuing Authority",auth,  conf_for(auth)),
    ]


def _extract_generic_fields(text: str, raw: list) -> list[dict]:
    """Minimal extraction for unknown document type."""
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}
    def conf_for(v): return conf_map.get(v, 65.0) if v else 0.0

    name = _search(r"(?:NAME)[:\s]+([A-Z][A-Z\s]{2,})", text)
    dob  = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH|YEAR\s*OF\s*BIRTH")
    id_  = _search(r"(?:ID|NUMBER|NO)[:\s.]*([A-Z0-9]{6,20})", text)

    return [
        _field("Full Name",  name, conf_for(name)),
        _field("Date of Birth", dob, conf_for(dob)),
        _field("ID/Number",  id_,  conf_for(id_)),
    ]


def _extract_pan_fields(text: str, raw: list) -> list[dict]:
    """Extract PAN card specific fields only."""
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}
    def conf_for(v): return conf_map.get(v, 72.0) if v else 0.0

    # Name: label-anchored; strip greedy label words the regex may swallow.
    name = _search(r"(?:^|\n)\s*Name\s*[:\-]?\s*([A-Z][A-Za-z .]{2,40})(?=\n|$)", text, re.MULTILINE)
    if name:
        name = re.split(r"\b(?:FATHER|DATE|PAN|NUMBER|APNA|अपना|अपने)\b", name)[0].strip()
        if len(name.split()) < 2:
            name = None
    if not name:
        for cand in re.findall(r"(?:^|\n)\s*([A-Z][A-Za-z\s.]{3,40})(?=\n|$)", text):
            for line in cand.split("\n"):
                cleaned = _clean_name_candidate(line)
                if cleaned:
                    name = cleaned
                    break
            if name:
                break
    father = _search(r"(?:FATHER'?S?\s*NAME|FATHERS?\s*NAME)\s*[:\-]?\s*([A-Z][A-Za-z .]{2,40})(?=\n|$)", text)
    if father:
        father = re.split(r"\b(?:DATE|PAN|NUMBER)\b", father)[0].strip()
    pnum = _search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    dob  = _labelled_date(text, r"DOB|DATE\s*OF\s*BIRTH")

    return [
        _field("Full Name",     name,   conf_for(name)),
        _field("Father's Name", father, conf_for(father)),
        _field("PAN Number",    pnum,   conf_for(pnum)),
        _field("Date of Birth", dob,    conf_for(dob)),
    ]


def _extract_voter_voter(text: str, raw: list) -> list[dict]:
    """Extract Voter ID (EPIC) specific fields only."""
    conf_map = {item[1].strip(): item[2] * 100 for item in raw if len(item) == 3}
    def conf_for(v): return conf_map.get(v, 70.0) if v else 0.0

    name = _search(r"(?:^|\n)\s*Name\s*[:\-]?\s*([A-Z][A-Za-z .]{2,40})(?=\n|$)", text, re.MULTILINE)
    if name:
        name = re.split(r"\b(?:FATHER|DATE|CONSTITUENCY|NUMBER|APNA|EPIC)\b", name)[0].strip()
        if len(name.split()) < 2:
            name = None
    if not name:
        for cand in re.findall(r"(?:^|\n)\s*([A-Z][A-Za-z\s.]{3,40})(?=\n|$)", text):
            for line in cand.split("\n"):
                cleaned = _clean_name_candidate(line)
                if cleaned:
                    name = cleaned
                    break
            if name:
                break
    pnum  = _search(r"\b([A-Z]{3}[0-9]{7})\b", text)
    father = _search(r"(?:FATHER'?S?\s*NAME|FATHERS?\s*NAME)\s*[:\-]?\s*([A-Z][A-Za-z .]{2,40})(?=\n|$)", text)
    const  = _search(r"(?:CONSTITUENCY)\s*[:\-]?\s*([A-Z][A-Za-z .]{2,40})(?=\n|$)", text)
    const  = re.split(r"\b(?:DATE|NUMBER)\b", const)[0].strip() if const else None

    return [
        _field("Full Name",        name,   conf_for(name)),
        _field("Voter ID Number",  pnum,   conf_for(pnum)),
        _field("Father's Name",    father, conf_for(father)),
        _field("Constituency",     const,  conf_for(const)),
    ]


def _merge_passes(p1: list, p2: list) -> list:
    """Union of two OCR passes; keep the higher-confidence copy of duplicate texts."""
    merged: dict[str, tuple] = {}
    for bbox, text, conf in list(p1) + list(p2):
        key = re.sub(r"\s+", "", text).upper()
        if not key:
            continue
        if key not in merged or conf > merged[key][2]:
            merged[key] = (bbox, text, conf)
    return list(merged.values())


def _extract_mrz(text: str, mrz_pass_lines: Optional[list] = None) -> Optional[str]:
    """
    Locate ICAO MRZ lines in OCR output. `mrz_pass_lines` come from the dedicated
    high-magnification pass over the MRZ strip and are preferred when found.
    """
    def qualifies(l: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9<]{25,44}", l)) and l.count("<") >= 2

    # 1) Lines that are already pure MRZ charset, in document order.
    candidates = [l.strip().upper() for l in text.split("\n")]
    if mrz_pass_lines:
        candidates += [str(l).strip().upper() for l in mrz_pass_lines]
    pool = [l for l in candidates if qualifies(l)]

    # 2) Fallback: MRZ chars misread with spaces/punctuation — squeeze and retry.
    if not pool:
        squeezed = [re.sub(r"[^A-Z0-9<]", "", l) for l in candidates]
        pool = [l for l in squeezed if len(l) >= 25 and l.count("<") >= 2]

    if not pool:
        return None

    # De-duplicate while keeping document order.
    seen, ordered = set(), []
    for l in pool:
        if l not in seen:
            seen.add(l)
            ordered.append(l)

    # Line 1 of a TD3 MRZ starts with a doc-code prefix (P<, I<, C<, A<, V<).
    # If the first candidate is the data line (line 2), pull the prefixed line up.
    if len(ordered) >= 2 and not re.match(r"^[ACVIP]<", ordered[0]):
        idx = next((i for i, l in enumerate(ordered) if re.match(r"^[ACVIP]<", l)), None)
        if idx is not None:
            ordered.insert(0, ordered.pop(idx))

    # TD1 (3×30) when three ~30-char lines are present; otherwise TD3 (2×44).
    if len(ordered) >= 3 and all(25 <= len(l) <= 35 for l in ordered[:3]):
        return "\n".join(ordered[:3])
    if len(ordered) >= 2:
        return "\n".join(ordered[:2])
    return ordered[0]


# ── DEMO fixtures (explicitly labelled, never used for real uploads) ──────────
DEMO_OCR: dict[str, dict] = {
    "aadhaar_valid": {
        "document_type": "national_id",
        "document_type_confidence": 0.97,
        "overall_confidence": 95.2,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",        "value":"ARJUN MEHTA",                          "confidence":97.3,"detected":True, "flagged":False},
            {"label":"Aadhaar Number",   "value":"XXXX XXXX 4821",                       "confidence":98.1,"detected":True, "flagged":False},
            {"label":"Date of Birth",    "value":"14/08/1998",                            "confidence":96.4,"detected":True, "flagged":False},
            {"label":"Gender",           "value":"MALE",                                  "confidence":99.0,"detected":True, "flagged":False},
            {"label":"Address",          "value":"12, MG ROAD, PUNE, MAHARASHTRA 411001","confidence":91.5,"detected":True, "flagged":False},
            {"label":"VID",              "value":"9876 5432 1098 7654",                   "confidence":93.2,"detected":True, "flagged":False},
            {"label":"Issuing Authority","value":"UIDAI",                                 "confidence":99.0,"detected":True, "flagged":False},
        ],
        "raw_mrz": None,
        "demo_mode": True,
    },
    "aadhaar_tampered": {
        "document_type": "national_id",
        "document_type_confidence": 0.94,
        "overall_confidence": 63.8,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",        "value":"SURESH KUMAR",          "confidence":72.4,"detected":True, "flagged":False},
            {"label":"Aadhaar Number",   "value":"XXXX XXXX 0001",        "confidence":44.7,"detected":True, "flagged":True},
            {"label":"Date of Birth",    "value":"01/01/2000",             "confidence":51.3,"detected":True, "flagged":True},
            {"label":"Gender",           "value":"MALE",                   "confidence":96.0,"detected":True, "flagged":False},
            {"label":"Address",          "value":"UNKNOWN ADDRESS, DELHI", "confidence":55.8,"detected":True, "flagged":True},
            {"label":"VID",              "value":None,                     "confidence": 0.0,"detected":False,"flagged":True},
            {"label":"Issuing Authority","value":"UIDAI",                  "confidence":88.0,"detected":True, "flagged":False},
        ],
        "raw_mrz": None,
        "demo_mode": True,
    },
    "valid_passport": {
        "document_type": "passport",
        "document_type_confidence": 0.98,
        "overall_confidence": 96.4,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",       "value":"RAJESH KUMAR SHARMA","confidence":98.2,"detected":True, "flagged":False},
            {"label":"Passport Number", "value":"P8472613",           "confidence":97.1,"detected":True, "flagged":False},
            {"label":"Nationality",     "value":"INDIAN",             "confidence":99.0,"detected":True, "flagged":False},
            {"label":"Date of Birth",   "value":"12/05/1990",         "confidence":95.6,"detected":True, "flagged":False},
            {"label":"Date of Issue",   "value":"15/03/2020",         "confidence":94.8,"detected":True, "flagged":False},
            {"label":"Date of Expiry",  "value":"14/03/2030",         "confidence":96.3,"detected":True, "flagged":False},
            {"label":"Gender",          "value":"M",                  "confidence":99.5,"detected":True, "flagged":False},
            {"label":"Issuing Country", "value":"INDIA",              "confidence":98.7,"detected":True, "flagged":False},
            {"label":"Place of Birth",  "value":None,                 "confidence": 0.0,"detected":False,"flagged":False},
        ],
        "raw_mrz": "P<INDSHARMA<<RAJESH<<KUMAR<<<<<<<<<<<<<<<<<\nP8472613<2IND9005126M3003147<<<<<<<<<<<<<<<6",
        "demo_mode": True,
    },
    "expired_document": {
        "document_type": "passport",
        "document_type_confidence": 0.97,
        "overall_confidence": 94.1,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",       "value":"PRIYA SINGH", "confidence":96.8,"detected":True, "flagged":False},
            {"label":"Passport Number", "value":"Z1234567",    "confidence":95.2,"detected":True, "flagged":False},
            {"label":"Nationality",     "value":"INDIAN",      "confidence":99.0,"detected":True, "flagged":False},
            {"label":"Date of Birth",   "value":"22/11/1985",  "confidence":94.5,"detected":True, "flagged":False},
            {"label":"Date of Issue",   "value":"10/06/2014",  "confidence":93.1,"detected":True, "flagged":False},
            {"label":"Date of Expiry",  "value":"09/06/2024",  "confidence":95.0,"detected":True, "flagged":False},
            {"label":"Gender",          "value":"F",           "confidence":99.5,"detected":True, "flagged":False},
            {"label":"Issuing Country", "value":"INDIA",       "confidence":98.7,"detected":True, "flagged":False},
            {"label":"Place of Birth",  "value":None,          "confidence": 0.0,"detected":False,"flagged":False},
        ],
        "raw_mrz": "P<INDSINGH<<PRIYA<<<<<<<<<<<<<<<<<<<<<<<<<<<\nZ1234567<4IND8511222F2406091<<<<<<<<<<<<<<<2",
        "demo_mode": True,
    },
    "tampered_text": {
        "document_type": "passport",
        "document_type_confidence": 0.91,
        "overall_confidence": 71.3,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",       "value":"JOHN DOE",   "confidence":88.1,"detected":True, "flagged":False},
            {"label":"Passport Number", "value":"A9876543",   "confidence":51.4,"detected":True, "flagged":True},
            {"label":"Nationality",     "value":"INDIAN",     "confidence":90.0,"detected":True, "flagged":False},
            {"label":"Date of Birth",   "value":"01/01/1995", "confidence":62.3,"detected":True, "flagged":True},
            {"label":"Date of Issue",   "value":"20/08/2022", "confidence":85.0,"detected":True, "flagged":False},
            {"label":"Date of Expiry",  "value":"19/08/2032", "confidence":83.5,"detected":True, "flagged":False},
            {"label":"Gender",          "value":"M",          "confidence":97.0,"detected":True, "flagged":False},
            {"label":"Issuing Country", "value":"INDIA",      "confidence":90.2,"detected":True, "flagged":False},
            {"label":"Place of Birth",  "value":None,         "confidence": 0.0,"detected":False,"flagged":False},
        ],
        "raw_mrz": None,
        "demo_mode": True,
    },
    "face_mismatch": {
        "document_type": "passport",
        "document_type_confidence": 0.99,
        "overall_confidence": 95.8,
        "ocr_available": True,
        "fields": [
            {"label":"Full Name",       "value":"AMIT VERMA", "confidence":97.4,"detected":True, "flagged":False},
            {"label":"Passport Number", "value":"K5678901",   "confidence":96.8,"detected":True, "flagged":False},
            {"label":"Nationality",     "value":"INDIAN",     "confidence":99.0,"detected":True, "flagged":False},
            {"label":"Date of Birth",   "value":"30/07/1988", "confidence":96.2,"detected":True, "flagged":False},
            {"label":"Date of Issue",   "value":"05/01/2021", "confidence":95.8,"detected":True, "flagged":False},
            {"label":"Date of Expiry",  "value":"04/01/2031", "confidence":97.1,"detected":True, "flagged":False},
            {"label":"Gender",          "value":"M",          "confidence":99.5,"detected":True, "flagged":False},
            {"label":"Issuing Country", "value":"INDIA",      "confidence":98.9,"detected":True, "flagged":False},
            {"label":"Place of Birth",  "value":None,         "confidence": 0.0,"detected":False,"flagged":False},
        ],
        "raw_mrz": "P<INDVERMA<<AMIT<<<<<<<<<<<<<<<<<<<<<<<<<<<<\nK5678901<6IND8807305M3101044<<<<<<<<<<<<<<<8",
        "demo_mode": True,
    },
    "multiple_flags": {
        "document_type": "visa",
        "document_type_confidence": 0.85,
        "overall_confidence": 58.7,
        "ocr_available": True,
        "fields": [
            {"label":"Visa Number",   "value":"VIS-9999-XX", "confidence":38.6,"detected":True, "flagged":True},
            {"label":"Full Name",     "value":"UNKNOWN PERSON","confidence":45.2,"detected":True,"flagged":True},
            {"label":"Nationality",   "value":None,          "confidence": 0.0,"detected":False,"flagged":False},
            {"label":"Date of Birth", "value":None,          "confidence": 0.0,"detected":False,"flagged":False},
            {"label":"Valid From",    "value":"01/01/2020",  "confidence":65.0,"detected":True, "flagged":False},
            {"label":"Valid Until",   "value":"31/12/2021",  "confidence":63.4,"detected":True, "flagged":False},
            {"label":"Visa Type",     "value":"TOURIST",     "confidence":72.0,"detected":True, "flagged":False},
            {"label":"Entries",       "value":None,          "confidence": 0.0,"detected":False,"flagged":False},
            {"label":"Stay Duration", "value":"30 DAYS",     "confidence":70.0,"detected":True, "flagged":False},
        ],
        "raw_mrz": None,
        "demo_mode": True,
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def run_ocr(image_path: Optional[Path], demo_case: Optional[str] = None) -> dict:
    """
    Run OCR on a document image.

    demo_case set  → return labelled synthetic fixture only.
    image_path set → run real OCR; NEVER return fake data on failure.
    neither set    → return INCONCLUSIVE result.
    """
    # ── Demo mode: explicit fixtures only ────────────────────────────────────
    if demo_case:
        data = DEMO_OCR.get(demo_case, DEMO_OCR["valid_passport"])
        return {**data, "demo_mode": True}

    # ── No image provided ────────────────────────────────────────────────────
    if image_path is None:
        return _inconclusive("No image path provided.")

    # ── Real OCR ─────────────────────────────────────────────────────────────
    reader = _get_reader()
    if not reader:
        return _inconclusive(
            "OCR engine (EasyOCR) is not installed or could not load. "
            "Text extraction is unavailable. Install easyocr to enable real OCR."
        )

    try:
        pre = _preprocess(image_path)

        # All inference passes run in parallel (torch CPU releases the GIL in
        # its C ops) — wall time ~= one pass instead of three.
        from concurrent.futures import ThreadPoolExecutor

        def _scan_full():
            return reader.readtext(
                pre if pre is not None else str(image_path),
                text_threshold=0.3, low_text=0.3, mag_ratio=1.5,
            )

        def _scan_orig():
            return reader.readtext(str(image_path), text_threshold=0.3, low_text=0.3)

        def _scan_mrm():
            try:
                crop = _mrz_crop(image_path)
                if crop is None:
                    return []
                raw_mrm = reader.readtext(
                    crop, text_threshold=0.3, low_text=0.3, mag_ratio=1.0,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
                )
                return [t for _, t, c in raw_mrm if c >= 0.30]
            except Exception as e:
                logger.debug(f"MRZ-targeted pass skipped: {e}")
                return []

        with ThreadPoolExecutor(max_workers=3) as pool:
            f1, f2, fm = pool.submit(_scan_full), pool.submit(_scan_orig), pool.submit(_scan_mrm)
            raw_pass1 = f1.result()
            raw_pass2 = f2.result()
            mrz_pass_lines = fm.result()
        raw = _merge_passes(raw_pass1, raw_pass2)
    except Exception as e:
        logger.error(f"EasyOCR readtext failed: {e}")
        return _inconclusive(f"OCR processing failed: {e}")

    if not raw:
        return _inconclusive("No text was detected in the image.")

    # Filter low-confidence detections
    usable    = [(bbox, text, conf) for bbox, text, conf in raw if conf >= 0.25]
    all_lines = [text for _, text, _ in usable]
    conf_vals = [conf for _, _, conf in usable]
    full_text = "\n".join(all_lines)
    avg_conf  = (sum(conf_vals) / len(conf_vals) * 100) if conf_vals else 0.0

    # Classify document type
    doc_type, doc_conf = _classify_document(full_text, usable)

    # Extract document-specific fields
    if doc_type == "national_id":
        fields = _extract_aadhaar_fields(full_text, usable)
    elif doc_type == "passport":
        fields = _extract_passport_fields(full_text, usable)
    elif doc_type == "visa":
        fields = _extract_visa_fields(full_text, usable)
    elif doc_type == "driving_licence":
        fields = _extract_dl_fields(full_text, usable)
    elif doc_type == "pan_card":
        fields = _extract_pan_fields(full_text, usable)
    elif doc_type == "voter_id":
        fields = _extract_voter_voter(full_text, usable)
    else:
        fields = _extract_generic_fields(full_text, usable)

    # OCR confidence: blend engine average + field coverage
    detected = [f for f in fields if f.get("detected")]
    field_cov = len(detected) / max(len(fields), 1)
    combined  = round(avg_conf * 0.65 + field_cov * 100 * 0.35, 1)

    return {
        "document_type":            doc_type,
        "document_type_confidence": doc_conf,
        "overall_confidence":       combined,
        "ocr_available":            True,
        "fields":                   fields,
        "raw_mrz":                  _extract_mrz(full_text, mrz_pass_lines),
        "demo_mode":                False,
    }


# ── Boot-time warmup ──────────────────────────────────────────────────────────
# Loading the EasyOCR model takes ~10-15 s. Do it once in a background thread
# at server startup so the first real screening is fast.

def _warmup() -> None:
    reader = _get_reader()
    if reader:
        logger.info("OCR engine warmed up (EasyOCR ready).")

try:
    import threading as _threading
    _threading.Thread(target=_warmup, name="ocr-warmup", daemon=True).start()
except Exception:
    pass
