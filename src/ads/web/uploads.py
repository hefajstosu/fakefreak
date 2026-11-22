"""Files sent with an analysis: multipart parsing, safe names, one folder per analysis under data/uploads (gitignored)."""
import os
import re
import shutil
from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Dict, List, Tuple

from ..analysis import classify_files
from ..paths import DATA

UPLOADS = os.path.join(DATA, "uploads")
MAX_UPLOAD = int(os.environ.get("ADS_MAX_UPLOAD_MB", "200")) * 1_000_000  # one analysis with its files
File = Tuple[str, bytes]


def parse_multipart(content_type: str, body: bytes) -> Tuple[Dict[str, str], List[File]]:
    """Form fields and files of a multipart/form-data body (standard library email parser)."""
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ValueError("expected multipart/form-data")
    fields: Dict[str, str] = {}
    files: List[File] = []
    for part in msg.iter_parts():
        data = part.get_payload(decode=True) or b""
        if part.get_filename():
            files.append((part.get_filename(), data))
        elif part.get_param("name", header="content-disposition"):
            fields[part.get_param("name", header="content-disposition")] = data.decode("utf-8", "replace")
    return fields, files


def safe_name(name: str, used: set) -> str:
    """A file name that cannot leave the upload folder and does not collide with another upload."""
    base = re.sub(r"[^\w.\-]+", "_", os.path.basename(name.replace("\\", "/")))[-120:].lstrip(".") or "file"
    stem, ext = os.path.splitext(base)
    out, n = base, 1
    while out in used:
        n += 1
        out = f"{stem}_{n}{ext}"
    used.add(out)
    return out


def store(aid: str, files: List[File]) -> Tuple[Dict[str, List[str]], List[str]]:
    """Write the files to UPLOADS/<analysis id>/ and sort them by kind; unsupported ones become notes."""
    if not files:
        return {}, []
    d = os.path.join(UPLOADS, aid)
    os.makedirs(d, exist_ok=True)
    used: set = set()
    paths = []
    for name, data in files:
        path = os.path.join(d, safe_name(name, used))
        with open(path, "wb") as f:
            f.write(data)
        paths.append(path)
    kinds = classify_files(paths)
    return kinds, [f"skipped unsupported file {os.path.basename(p)}" for p in kinds.pop("unsupported", [])]


def folder(aid: str) -> str:
    return os.path.join(UPLOADS, aid)


def drop(aid: str) -> None:
    shutil.rmtree(folder(aid), ignore_errors=True)
