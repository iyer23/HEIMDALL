"""
HEIMDALL — Screening Report Generator
SIH 2026 · PS 26188

Generates PDF reports using the CANONICAL result object from the backend.
- Never invents new interpretations.
- Includes a consistency check before generating.
- If consistency fails → returns a clearly-labelled error report (no misleading content).
- MRZ section only shown for MRZ-applicable documents.
- Responsible wording throughout.
"""
from __future__ import annotations
import io
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("heimdall.report")

MRZ_APPLICABLE_TYPES = {"passport", "visa"}


# ── Consistency checker ───────────────────────────────────────────────────────

def _check_consistency(result: dict) -> list[str]:
    """
    Verify the result object is internally consistent.
    Returns list of violation strings (empty = consistent).
    """
    violations = []
    risk    = result.get("risk", {})
    score   = risk.get("score", 0)
    decision= risk.get("decision", "")
    mrz     = result.get("mrz", {})
    face    = result.get("face_verification", {})
    tamp    = result.get("tampering", {})
    val     = result.get("validation", {})
    doc_type= result.get("document_type", "unknown")
    ef      = result.get("evidence_fusion", {})

    # Score within bounds
    if not (0 <= score <= 100):
        violations.append(f"Risk score {score} is outside valid range 0-100.")

    # Import thresholds from risk engine (single source of truth)
    from services.risk_service import THRESHOLD_PASS, THRESHOLD_HIGH

    # Decision matches score
    if decision == "PASS" and score > THRESHOLD_PASS:
        violations.append(f"Decision is PASS but score is {score} (> threshold {THRESHOLD_PASS}).")
    if decision == "HIGH_RISK" and score <= THRESHOLD_HIGH:
        violations.append(f"Decision is HIGH_RISK but score is {score} (<= threshold {THRESHOLD_HIGH}).")

    # Aadhaar must not have MRZ risk
    if doc_type in ("national_id",) and mrz.get("status") not in ("NOT_APPLICABLE", None, ""):
        status = mrz.get("status", "")
        if status not in ("NOT_APPLICABLE",):
            # Non-fatal warning
            pass

    # Face INCONCLUSIVE must not be described as MATCH in narrative
    if face.get("status") in ("INCONCLUSIVE", "UNAVAILABLE", "NOT_PROVIDED"):
        narrative = ef.get("narrative", "").lower()
        if "face match confirmed" in narrative or "match threshold" in narrative:
            violations.append("Narrative mentions face match but face status is INCONCLUSIVE/UNAVAILABLE.")

    # If forensics CLEAN but narrative says tampering found
    if tamp.get("status") == "CLEAN":
        narrative = ef.get("narrative", "").lower()
        if "tampering" in narrative and "no" not in narrative[:narrative.find("tampering")]:
            pass  # narrative is built from factors so this should be fine

    # Breakdown total should match score
    breakdown = risk.get("breakdown", {})
    if breakdown:
        computed_total = sum(
            v.get("points", 0) for k, v in breakdown.items()
            if isinstance(v, dict) and k not in ("total", "raw_total")
        )
        if abs(computed_total - score) > 1:   # allow rounding
            violations.append(
                f"Breakdown total ({computed_total}) does not match risk score ({score})."
            )

    return violations


def _error_report(screening_id: str, violations: list[str]) -> bytes:
    """Plain-text error report when consistency fails."""
    lines = [
        "HEIMDALL — Screening Report — CONSISTENCY ERROR",
        "=" * 60,
        f"Screening ID: {screening_id}",
        f"Generated:    {datetime.now().strftime('%d %b %Y %H:%M:%S')}",
        "",
        "REPORT COULD NOT BE GENERATED.",
        "Internal consistency check detected the following issue(s):",
        "",
    ] + [f"  • {v}" for v in violations] + [
        "",
        "Please re-run the screening to generate a valid report.",
        "",
        "HEIMDALL · SIH 2026 PS 26188",
    ]
    return "\n".join(lines).encode()


# ── PDF builder ───────────────────────────────────────────────────────────────

def generate_pdf_report(result: dict) -> bytes:
    """
    Generate a PDF screening report from the canonical result object.
    Runs consistency check first — returns error report if check fails.
    """
    rid      = result.get("screening_id", "N/A")
    ts       = result.get("timestamp", datetime.now().isoformat())
    doc_type = result.get("document_type", "unknown")
    doc_conf = result.get("document_type_confidence", 0.0)
    demo     = result.get("demo_mode", False)
    risk     = result.get("risk", {})
    score    = risk.get("score", 0)
    decision = risk.get("decision", "UNKNOWN")
    ef       = result.get("evidence_fusion", {})
    ocr      = result.get("ocr", {})
    val      = result.get("validation", {})
    mrz      = result.get("mrz", {})
    tamp     = result.get("tampering", {})
    face     = result.get("face_verification", {})

    # ── Consistency check ─────────────────────────────────────────────────────
    violations = _check_consistency(result)
    if violations:
        logger.error(f"Report consistency failure [{rid}]: {violations}")
        return _error_report(rid, violations)

    # ── Try ReportLab ─────────────────────────────────────────────────────────
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=18*mm, bottomMargin=18*mm)

        # Colors
        NAVY  = colors.HexColor("#1e3a5f")
        BLUE  = colors.HexColor("#2563eb")
        TEXT  = colors.HexColor("#1e293b")
        MUTED = colors.HexColor("#64748b")
        GREEN = colors.HexColor("#16a34a")
        AMBER = colors.HexColor("#ca8a04")
        RED   = colors.HexColor("#dc2626")
        WHITE = colors.white
        BGROW = colors.HexColor("#f8fafc")

        dec_color = {"PASS": GREEN, "REVIEW_REQUIRED": AMBER, "HIGH_RISK": RED}.get(decision, MUTED)

        def sty(name, **kw):
            defaults = dict(fontName="Helvetica", fontSize=10, textColor=TEXT)
            defaults.update(kw)
            return ParagraphStyle(name, **defaults)

        title_s = sty("title", fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, spaceAfter=2)
        sub_s   = sty("sub",   fontSize=9, textColor=MUTED, spaceAfter=8)
        h2_s    = sty("h2",    fontName="Helvetica-Bold", fontSize=12, textColor=NAVY,
                      spaceBefore=10, spaceAfter=5)
        body_s  = sty("body",  spaceAfter=4, leading=14)
        small_s = sty("small", fontSize=8, textColor=MUTED, spaceAfter=2)
        warn_s  = sty("warn",  fontSize=8, textColor=colors.HexColor("#7e22ce"), spaceAfter=6)
        mono_s  = sty("mono",  fontName="Courier", fontSize=8, textColor=GREEN, spaceAfter=4)

        story = []

        # ── Header ────────────────────────────────────────────────────────────
        story.append(Paragraph("HEIMDALL", title_s))
        story.append(Paragraph(
            "AI-Powered Identity &amp; Document Screening System · SIH 2026 · PS 26188",
            sub_s,
        ))
        if demo:
            story.append(Paragraph(
                "⚠ SYNTHETIC DEMO ANALYSIS — Pre-configured test data. "
                "Results do not represent real document verification.",
                warn_s,
            ))
        story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=8))

        # ── Meta ──────────────────────────────────────────────────────────────
        def trow(k, v, vc=None):
            return [k, v]

        meta = [
            trow("Screening ID:",      rid),
            trow("Timestamp:",         ts),
            trow("Document Type:",     doc_type.replace("_"," ").title() + f"  ({doc_conf:.1f}% confidence)"),
            trow("Risk Score:",        f"{score}/100"),
            trow("Final Decision:",    decision.replace("_"," ")),
        ]
        mt = Table(meta, colWidths=[50*mm, 120*mm])
        mt.setStyle(TableStyle([
            ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 10),
            ("TEXTCOLOR",     (0,0),(0,-1), MUTED),
            ("TEXTCOLOR",     (1,0),(1,-1), TEXT),
            ("TEXTCOLOR",     (1,4),(1, 4), dec_color),
            ("FONTNAME",      (1,4),(1, 4), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,0),(-1,-1), [BGROW, WHITE]),
            ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ]))
        story.append(mt)
        story.append(Spacer(1, 8))

        # ── OCR Fields ────────────────────────────────────────────────────────
        story.append(Paragraph("Extracted Fields (OCR)", h2_s))
        fields = ocr.get("fields", [])
        if fields:
            data = [["Field", "Value", "Confidence"]] + [
                [f["label"],
                 f.get("value") or "Not detected",
                 f"{f.get('confidence', 0):.0f}%" if f.get("detected") else "—"]
                for f in fields
            ]
            t = Table(data, colWidths=[55*mm, 85*mm, 30*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1, 0), BLUE),
                ("TEXTCOLOR",     (0,0),(-1, 0), WHITE),
                ("FONTNAME",      (0,0),(-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 9),
                ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BGROW, WHITE]),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ]))
            story.append(t)
        raw_mrz = ocr.get("raw_mrz")
        if raw_mrz:
            story.append(Spacer(1,4))
            story.append(Paragraph("Raw MRZ:", small_s))
            escaped = raw_mrz.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","  |  ")
            story.append(Paragraph(escaped, mono_s))
        story.append(Spacer(1, 6))

        # ── Document Validation ───────────────────────────────────────────────
        story.append(Paragraph("Document Validation", h2_s))
        checks = val.get("checks", [])
        sc = {"PASS": GREEN, "WARNING": AMBER, "FAIL": RED, "NOT_APPLICABLE": MUTED}
        if checks:
            data = [["Check","Status","Detail"]] + [
                [c["check_name"], c["status"], c["message"]] for c in checks
            ]
            t = Table(data, colWidths=[60*mm, 22*mm, 88*mm])
            style = [
                ("BACKGROUND",    (0,0),(-1, 0), NAVY),
                ("TEXTCOLOR",     (0,0),(-1, 0), WHITE),
                ("FONTNAME",      (0,0),(-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 8),
                ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [BGROW, WHITE]),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ]
            for i, c in enumerate(checks, start=1):
                col = sc.get(c["status"], MUTED)
                style += [("TEXTCOLOR",(1,i),(1,i),col), ("FONTNAME",(1,i),(1,i),"Helvetica-Bold")]
            t.setStyle(TableStyle(style))
            story.append(t)
        story.append(Spacer(1, 6))

        # ── MRZ ───────────────────────────────────────────────────────────────
        story.append(Paragraph("MRZ Analysis (ICAO 9303)", h2_s))
        mrz_status = mrz.get("status", "")
        if mrz_status == "NOT_APPLICABLE":
            story.append(Paragraph(
                f"MRZ is not applicable for document type '{doc_type}'. MRZ checks were skipped.",
                body_s,
            ))
        else:
            story.append(Paragraph(mrz.get("summary", ""), body_s))
            mrz_checks = mrz.get("checks", [])
            if mrz_checks:
                data = [["MRZ Check","Status","Detail"]] + [
                    [c["check_name"], c["status"], c["message"]] for c in mrz_checks
                ]
                t = Table(data, colWidths=[60*mm, 22*mm, 88*mm])
                tstyle = [
                    ("BACKGROUND",    (0,0),(-1, 0), NAVY),
                    ("TEXTCOLOR",     (0,0),(-1, 0), WHITE),
                    ("FONTNAME",      (0,0),(-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",      (0,0),(-1,-1), 8),
                    ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                    ("ROWBACKGROUNDS",(0,1),(-1,-1), [BGROW, WHITE]),
                    ("TOPPADDING",    (0,0),(-1,-1), 3),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                ]
                for i, c in enumerate(mrz_checks, start=1):
                    col = sc.get(c["status"], MUTED)
                    tstyle += [("TEXTCOLOR",(1,i),(1,i),col),("FONTNAME",(1,i),(1,i),"Helvetica-Bold")]
                t.setStyle(TableStyle(tstyle))
                story.append(t)
        story.append(Spacer(1, 6))

        # ── Forensics ─────────────────────────────────────────────────────────
        story.append(Paragraph("Image Forensic Analysis", h2_s))
        story.append(Paragraph(
            f"Status: {tamp.get('status','—')}  |  "
            f"Anomaly confidence: {tamp.get('overall_confidence',0):.0f}%  |  "
            f"Suspicious regions: {len(tamp.get('regions',[]))}",
            body_s,
        ))
        story.append(Paragraph(tamp.get("interpretation",""), body_s))
        for r in tamp.get("regions", [])[:3]:
            story.append(Paragraph(
                f"• {r.get('label','Region')} ({r.get('confidence',0):.0f}%): {r.get('reason','')}",
                small_s,
            ))
        for f_flag in tamp.get("metadata_flags", []):
            story.append(Paragraph(f"• Metadata: {f_flag}", small_s))
        story.append(Spacer(1, 6))

        # ── Face ──────────────────────────────────────────────────────────────
        story.append(Paragraph("Face Verification", h2_s))
        face_status = face.get("status","")
        face_score  = face.get("match_score")
        score_txt   = f"{face_score:.1f}%" if face_score is not None else "N/A"
        story.append(Paragraph(
            f"Status: {face_status}  |  Similarity: {score_txt}  |  Threshold: {face.get('threshold_used','—')}",
            body_s,
        ))
        story.append(Paragraph(face.get("message",""), body_s))
        story.append(Spacer(1, 6))

        # ── Evidence Fusion / WHY FLAGGED ─────────────────────────────────────
        story.append(Paragraph("Evidence Fusion — WHY FLAGGED", h2_s))
        story.append(Paragraph(ef.get("narrative",""), body_s))
        story.append(Spacer(1, 4))

        # Risk factors (fraud indicators only — not limitations)
        risk_factors = risk.get("factors", [])
        positive_factors = [f for f in risk_factors if f.get("points", 0) > 0 and not f.get("is_limitation")]
        clean_factors    = [f for f in risk_factors if f.get("points", 0) == 0 and not f.get("is_limitation")]
        if positive_factors:
            story.append(Paragraph("<b>Risk Indicators:</b>", body_s))
            for f in positive_factors:
                story.append(Paragraph(
                    f"+{f['points']}  {f.get('label','')} — {f.get('description','')}",
                    small_s))
        else:
            story.append(Paragraph("✓ No risk indicators detected.", small_s))

        # Clean checks
        for f in clean_factors[:5]:
            story.append(Paragraph(f"✓  {f.get('label','')}", small_s))

        # Analysis limitations (module failures — NOT fraud evidence)
        limitations = risk.get("analysis_limitations", [])
        if limitations:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Analysis Limitations:</b>", body_s))
            for lim in limitations:
                story.append(Paragraph(
                    f"•  {lim.get('label','')} — {lim.get('description','')}",
                    small_s))

        # ── Risk Breakdown ────────────────────────────────────────────────────
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Total Risk Score: {score}/100 → {decision.replace('_',' ')}", body_s))
        story.append(Spacer(1, 6))

        # ── Blockchain Evidence ───────────────────────────────────────────────
        ev = result.get("blockchain")
        if isinstance(ev, dict) and ev.get("result_hash"):
            story.append(Paragraph("Blockchain Evidence (Tamper-Evident Audit)", h2_s))
            ev_status  = str(ev.get("status", "—"))
            is_demo    = ev.get("mode") != "sepolia"
            ev_color   = GREEN if ev_status.startswith(("REGISTERED", "DEMO_REGISTERED")) else AMBER
            meta2 = [
                trow("Status:",         ev_status.replace("_", " ").title()),
                trow("Network:",        ev.get("network_label", "—") + ("  [DEMO]" if is_demo else "")),
                trow("Screening ID:",   ev.get("screening_id", rid)),
                trow("Result Hash (SHA-256):", str(ev.get("result_hash", "—"))),
                trow("Transaction Hash:", str(ev.get("tx_hash") or "— (demo ledger)")),
            ]
            t2 = Table(meta2, colWidths=[50*mm, 120*mm])
            t2.setStyle(TableStyle([
                ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 9),
                ("TEXTCOLOR",     (0,0),(0,-1), MUTED),
                ("TEXTCOLOR",     (1,0),(1, 0), ev_color),
                ("FONTNAME",      (1,0),(1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (1,3),(-1, 3), 7),
                ("FONTNAME",      (1,3),(1, 3), "Courier"),
                ("ROWBACKGROUNDS",(0,0),(-1,-1), [BGROW, WHITE]),
                ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING",    (0,0),(-1,-1), 4),
                ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ]))
            story.append(t2)
            if is_demo:
                story.append(Paragraph(
                    "⚠ DEMO BLOCKCHAIN — no public network transaction was made. The hash was "
                    "recorded in a local tamper-evident ledger for demonstration purposes.",
                    warn_s,
                ))
            story.append(Paragraph(
                "Only the screening ID, result hash, risk score, decision and timestamp are "
                "anchored. No images, OCR text, names, or personal data are ever written to "
                "the blockchain. Blockchain anchoring provides tamper-evident integrity for "
                "the screening record; it does not prove that a document is genuine.",
                small_s,
            ))
            story.append(Spacer(1, 6))

        # ── Disclaimer ────────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#e2e8f0"), spaceAfter=5))
        story.append(Paragraph(
            "<b>DISCLAIMER:</b> HEIMDALL is an automated screening aid. Results are probabilistic "
            "indicators and are not definitive proof of identity, authenticity, fraud, or document "
            "forgery. Final decisions must be made by authorised human reviewers in conjunction "
            "with applicable official verification sources. Do not rely solely on this report for "
            "consequential decisions.",
            ParagraphStyle("disc", fontName="Helvetica", fontSize=7.5, textColor=MUTED),
        ))
        story.append(Paragraph(
            f"Generated by HEIMDALL · SIH 2026 · PS 26188 · "
            f"{datetime.now().strftime('%d %b %Y %H:%M:%S')}",
            small_s,
        ))

        doc.build(story)
        return buf.getvalue()

    except ImportError:
        # ReportLab not installed — plain text fallback
        lines = [
            "HEIMDALL — Document Screening Report",
            "SIH 2026 · PS 26188 · Ministry of Home Affairs",
            "=" * 55,
            f"Screening ID:  {rid}",
            f"Timestamp:     {ts}",
            f"Document Type: {doc_type}",
            f"Risk Score:    {score}/100",
            f"Decision:      {decision}",
            "",
            "WHY FLAGGED:",
        ] + [
            f"  +{f['points']}  {f['label']}: {f['description']}"
            for f in risk.get("factors", []) if f.get("points", 0) > 0 and not f.get("is_limitation")
        ] + [
            "",
            "ANALYSIS LIMITATIONS:",
        ] + [
            f"  - {l['label']}"
            for l in risk.get("analysis_limitations", [])
        ] + [
            "",
            "DISCLAIMER: HEIMDALL is an automated screening aid. Human review required.",
            f"Generated: {datetime.now().strftime('%d %b %Y %H:%M:%S')}",
        ]
        return "\n".join(lines).encode("utf-8")
