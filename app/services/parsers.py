"""文件解析（ING-001 多格式导入）：PDF / DOCX / TXT / MD / HTML。

统一输出 ParsedDocument：全文 + 分页文本（用于页码定位与来源锚点）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from app.core.logging import logger
from app.services.text_utils import normalize


@dataclass
class ParsedDocument:
    text: str
    pages: List[str] = field(default_factory=list)
    page_count: int = 0

    @property
    def is_empty(self) -> bool:
        return len(normalize(self.text)) < 10


def parse_plain_text(raw: str) -> ParsedDocument:
    text = normalize(raw)
    pages = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    return ParsedDocument(text=text, pages=pages, page_count=max(1, len(pages)))


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("未安装 PyMuPDF（pip install pymupdf），无法解析 PDF") from exc

    doc = fitz.open(str(path))
    pages: List[str] = []
    try:
        for page in doc:
            pages.append(normalize(page.get_text("text")))
    finally:
        doc.close()
    text = "\n".join(pages)
    return ParsedDocument(text=text, pages=pages, page_count=len(pages))


def parse_docx(path: Path) -> ParsedDocument:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("未安装 python-docx，无法解析 DOCX") from exc

    document = docx.Document(str(path))
    paragraphs = [normalize(p.text) for p in document.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    # docx 无稳定页码，按段落分组为虚拟页（每 20 段一页）
    pages = ["\n".join(paragraphs[i : i + 20]) for i in range(0, len(paragraphs), 20)]
    return ParsedDocument(text=text, pages=pages or [text], page_count=len(pages) or 1)


def parse_html(raw: str) -> ParsedDocument:
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        raw = re.sub(r"<[^>]+>", " ", raw)
        return parse_plain_text(raw)

    soup = BeautifulSoup(raw, "lxml" if _has_lxml() else "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = normalize(soup.get_text("\n"))
    pages = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    return ParsedDocument(text=text, pages=pages, page_count=max(1, len(pages)))


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401

        return True
    except ImportError:
        return False


def parse_file(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        return parse_docx(path)
    raw = _read_text(path)
    if suffix in (".html", ".htm"):
        return parse_html(raw)
    return parse_plain_text(raw)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "utf-8-sig"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="ignore")
