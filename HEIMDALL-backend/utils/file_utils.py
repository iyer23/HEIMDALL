import os, uuid, re, mimetypes
from pathlib import Path

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))

def ensure_upload_dir():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(name))
    return name[:120]

async def save_upload(file_bytes: bytes, original_name: str, subfolder: str = "") -> Path:
    ensure_upload_dir()
    ext = Path(original_name).suffix.lower() or ".bin"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    folder = UPLOAD_DIR / subfolder if subfolder else UPLOAD_DIR
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / safe_name
    dest.write_bytes(file_bytes)
    return dest

def validate_upload(content_type: str, size: int) -> str | None:
    if content_type not in ALLOWED_TYPES:
        return f"Unsupported file type: {content_type}. Use JPG, PNG, or PDF."
    if size > MAX_SIZE_BYTES:
        return f"File too large ({size // 1024} KB). Max is 10 MB."
    return None

def delete_file(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass
