"""文件存储抽象（本地磁盘；生产可替换为 MinIO/S3，接口保持不变）。"""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from app.core.config import UPLOAD_DIR
from app.services.text_utils import content_hash


def save_upload(filename: str, raw: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    name = f"{int(time.time())}-{uuid.uuid4().hex[:8]}{suffix}"
    target = UPLOAD_DIR / name
    target.write_bytes(raw)
    return {
        "file_name": filename,
        "file_path": str(target),
        "file_size": len(raw),
        "mime_type": suffix.lstrip("."),
    }


def read_text(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return ""
    for encoding in ("utf-8", "gb18030"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return file_path.read_text(encoding="utf-8", errors="ignore")


def remove_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def hash_of_file(path: str) -> str:
    return content_hash(read_text(path))
