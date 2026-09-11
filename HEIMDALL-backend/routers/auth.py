"""
HEIMDALL — Authentication Router (additive; does not modify existing logic)
Flow: register (email+password) -> login -> OTP emailed -> verify OTP -> session token.
Google sign-in endpoint returns a clear "not configured" response unless OAuth env vars are set.
Storage: separate tables in the same SQLite file (users, otps, sessions).
"""
from __future__ import annotations
import os, re, sqlite3, hashlib, secrets, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("heimdall.auth")

DB_PATH = Path(__file__).resolve().parent.parent / "heimdall.db"

# ── SMTP configuration (from .env) ──
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "ku2407u1032@karnavatiuniversity.edu.in")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

OTP_TTL_MIN = 10
SESSION_TTL_H = 24


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS auth_users (
        email TEXT PRIMARY KEY,
        pw_hash TEXT NOT NULL,
        name TEXT,
        created_at TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS auth_otps (
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        expires_at TEXT NOT NULL)""")
    return con


def _hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"{salt.hex()}${dk.hex()}"


def _verify_pw(pw: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── OTP email template ──
OTP_EMAIL_TMPL = """\
<!doctype html>
<html><body style="margin:0;padding:0;background:#F4F6F0;font-family:'Segoe UI',Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F6F0;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="520" cellpadding="0" cellspacing="0"
             style="background:#FFFFFF;border-radius:16px;overflow:hidden;
                    box-shadow:0 8px 30px rgba(31,36,32,0.12);border:1px solid #E3E7DD;">
        <!-- header -->
        <tr><td style="background:#3F4A32;padding:26px 36px;">
          <table width="100%"><tr>
            <td>
              <div style="font-size:22px;font-weight:700;letter-spacing:4px;color:#F8F9F6;">HEIMDALL</div>
              <div style="font-size:11px;letter-spacing:2px;color:#C9D1C0;margin-top:3px;">IDENTITY &amp; DOCUMENT SCREENING</div>
            </td>
            <td align="right">
              <div style="width:38px;height:38px;border-radius:10px;background:#F8F9F6;text-align:center;line-height:38px;
                          font-size:19px;">&#128737;</div>
            </td>
          </tr></table>
        </td></tr>
        <!-- body -->
        <tr><td style="padding:34px 36px 8px 36px;">
          <div style="font-size:19px;font-weight:600;color:#1F2420;">Verify your email</div>
          <div style="font-size:14px;color:#5A6153;line-height:1.6;margin-top:8px;">
            Hello{ name_html },<br/>
            Use the one-time code below to complete your sign-in to HEIMDALL.
            This code is valid for <strong>{ttl} minutes</strong>.
          </div>
          <!-- OTP box -->
          <div style="text-align:center;margin:26px 0;">
            <div style="display:inline-block;background:#F8F9F6;border:1px solid #DDE2D6;border-radius:12px;
                        padding:16px 34px;letter-spacing:12px;font-size:34px;font-weight:700;color:#3F4A32;">{otp}</div>
          </div>
          <div style="font-size:12.5px;color:#8A9080;line-height:1.6;text-align:center;">
            If you did not request this code, you can safely ignore this email.<br/>
            Never share this code with anyone.
          </div>
        </td></tr>
        <!-- footer -->
        <tr><td style="padding:22px 36px 26px 36px;">
          <div style="border-top:1px solid #E3E7DD;padding-top:16px;font-size:11px;color:#8A9080;line-height:1.6;">
            HEIMDALL &middot; AI-Powered Identity &amp; Document Screening<br/>
            SIH 2026 &middot; PS 26188 &middot; Ministry of Home Affairs / SSB
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>
"""


def _send_otp_email(to: str, otp: str, name: str | None) -> bool:
    """Send the OTP via SMTP. Returns False when SMTP is not configured."""
    if not SMTP_PASSWORD:
        logger.warning("SMTP_PASSWORD not set — OTP for %s not emailed (dev mode).", to)
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"HEIMDALL verification code: {otp}"
    msg["From"] = f"HEIMDALL Security <{SMTP_FROM}>"
    msg["To"] = to
    html = OTP_EMAIL_TMPL.replace("{otp}", otp).replace("{ttl}", str(OTP_TTL_MIN)) \
                         .replace("{name_html}", f" <strong>{name}</strong>" if name else "")
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        logger.info("OTP email sent to %s", to)
        return True
    except Exception as e:
        logger.error("OTP email failed: %s", e)
        return False


def _new_otp(email: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    exp = (_utcnow() + timedelta(minutes=OTP_TTL_MIN)).isoformat()
    con = _db()
    con.execute("INSERT INTO auth_otps (email, code, expires_at) VALUES (?,?,?)", (email, code, exp))
    con.commit(); con.close()
    return code


# ── Schemas ──
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class OtpIn(BaseModel):
    email: EmailStr
    code: str

class GoogleIn(BaseModel):
    credential: str | None = None


# ── Endpoints ──
@router.post("/register")
def register(body: RegisterIn):
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    email = body.email.lower().strip()
    con = _db()
    if con.execute("SELECT 1 FROM auth_users WHERE email=?", (email,)).fetchone():
        con.close()
        raise HTTPException(409, "An account with this email already exists. Please sign in.")
    con.execute("INSERT INTO auth_users (email, pw_hash, name, created_at) VALUES (?,?,?,?)",
                (email, _hash_pw(body.password), body.name, _utcnow().isoformat()))
    con.commit(); con.close()
    code = _new_otp(email)
    sent = _send_otp_email(email, code, body.name)
    return {"ok": True, "otp_sent": sent, "dev_otp": None if sent else code,
            "message": "Account created. A verification code was sent to your email."
                       if sent else
                       "Account created. SMTP is not configured, so the code is shown here for demo."}


@router.post("/login")
def login(body: LoginIn):
    email = body.email.lower().strip()
    con = _db()
    row = con.execute("SELECT pw_hash, name FROM auth_users WHERE email=?", (email,)).fetchone()
    con.close()
    if not row or not _verify_pw(body.password, row["pw_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    code = _new_otp(email)
    sent = _send_otp_email(email, code, row["name"])
    return {"ok": True, "otp_sent": sent, "dev_otp": None if sent else code,
            "message": "A verification code was sent to your email." if sent else
                       "SMTP is not configured, so the code is shown here for demo."}


@router.post("/verify-otp")
def verify_otp(body: OtpIn):
    email = body.email.lower().strip()
    con = _db()
    row = con.execute(
        "SELECT rowid FROM auth_otps WHERE email=? AND code=? AND consumed=0 AND expires_at > ? "
        "ORDER BY rowid DESC LIMIT 1", (email, body.code.strip(), _utcnow().isoformat())
    ).fetchone()
    if not row:
        con.close()
        raise HTTPException(401, "Invalid or expired code.")
    con.execute("UPDATE auth_otps SET consumed=1 WHERE rowid=?", (row["rowid"],))
    token = secrets.token_hex(32)
    exp = (_utcnow() + timedelta(hours=SESSION_TTL_H)).isoformat()
    con.execute("INSERT INTO auth_sessions (token, email, expires_at) VALUES (?,?,?)", (token, email, exp))
    user = con.execute("SELECT name FROM auth_users WHERE email=?", (email,)).fetchone()
    con.commit(); con.close()
    return {"ok": True, "token": token, "email": email, "name": user["name"] if user else None}


@router.get("/me")
def me(token: str):
    con = _db()
    row = con.execute("SELECT email, expires_at FROM auth_sessions WHERE token=? AND expires_at > ?",
                      (token, _utcnow().isoformat())).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "Session expired.")
    return {"email": row["email"]}


@router.get("/google-client-id")
def google_client_id():
    """Frontend asks for the OAuth client id (empty string = not configured)."""
    return {"client_id": GOOGLE_CLIENT_ID}


@router.post("/google")
def google(body: GoogleIn):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(501,
            "Google sign-in is not configured on this deployment. "
            "Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in the backend .env to enable it.")
    if not body.credential:
        raise HTTPException(400, "Missing Google credential.")
    # Verify the Google ID token against Google's tokeninfo endpoint.
    import json as _json
    from urllib.request import urlopen
    from urllib.parse import urlencode
    try:
        with urlopen("https://oauth2.googleapis.com/tokeninfo?" +
                     urlencode({"id_token": body.credential}), timeout=15) as resp:
            info = _json.loads(resp.read().decode())
    except Exception:
        raise HTTPException(401, "Could not verify the Google credential.")
    if info.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(401, "Google credential was issued for a different app.")
    if info.get("email_verified", "").lower() != "true":
        raise HTTPException(401, "Google account email is not verified.")
    exp = int(info.get("exp", "0"))
    if exp and exp < _utcnow().timestamp():
        raise HTTPException(401, "Google credential has expired.")
    email = info["email"].lower().strip()
    name = info.get("name") or info.get("given_name")
    # Upsert the user (Google accounts get an unusable random password hash).
    con = _db()
    if not con.execute("SELECT 1 FROM auth_users WHERE email=?", (email,)).fetchone():
        con.execute("INSERT INTO auth_users (email, pw_hash, name, created_at) VALUES (?,?,?,?)",
                    (email, _hash_pw(secrets.token_urlsafe(32)), name, _utcnow().isoformat()))
    elif name:
        con.execute("UPDATE auth_users SET name=? WHERE email=? AND (name IS NULL OR name='')",
                    (name, email))
    token = secrets.token_hex(32)
    exp_at = (_utcnow() + timedelta(hours=SESSION_TTL_H)).isoformat()
    con.execute("INSERT INTO auth_sessions (token, email, expires_at) VALUES (?,?,?)",
                (token, email, exp_at))
    con.commit(); con.close()
    return {"ok": True, "token": token, "email": email, "name": name}
