"""Upload validation and storage. Client-supplied filenames are never used as filesystem paths."""
import hashlib
import os
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

ALLOWED_EXT = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".csv": "csv"}
MIME = {"pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain; charset=utf-8", "csv": "text/csv; charset=utf-8"}
MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024  # zip-bomb guard


def safe_filename(name: str | None) -> str:
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:255] or "unnamed"


def detect_source_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Unsupported file type. Allowed: PDF, DOCX, TXT, CSV.")
    return ALLOWED_EXT[ext]


async def read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"File exceeds the {get_settings().max_upload_mb} MB limit.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    return data


def validate_content(data: bytes, source_type: str) -> None:
    """Checks the bytes really match the claimed type (extension alone is not trusted)."""
    bad = HTTPException(status.HTTP_400_BAD_REQUEST, "File content does not match its extension.")
    if source_type == "pdf":
        if b"%PDF-" not in data[:1024]:
            raise bad
    elif source_type == "docx":
        import io
        if not data.startswith(b"PK"):
            raise bad
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" not in names:
                    raise bad
                if sum(i.file_size for i in z.infolist()) > MAX_DOCX_UNCOMPRESSED:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "DOCX expands to an unsafe size.")
        except zipfile.BadZipFile:
            raise bad
    else:  # txt / csv
        if b"\x00" in data[:8192] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise bad  # binary content


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_file(owner_id: uuid.UUID, source_type: str, data: bytes) -> str:
    folder = Path(get_settings().storage_dir).resolve() / str(owner_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}.{source_type}"
    path.write_bytes(data)
    return str(path)


def delete_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
