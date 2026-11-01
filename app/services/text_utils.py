"""文本基础工具：归一化、中文切词（字符 2-gram + 英文词）、SimHash。

不依赖 jieba 等外部词典，保证离线可用；中文以 2-gram 作为检索单元。
"""
from __future__ import annotations

import hashlib
import re
from typing import List

_PUNCT = re.compile(r"[^\u4e00-\u9fa5A-Za-z0-9]+")
_EN = re.compile(r"[A-Za-z0-9]+")


def normalize(text: str) -> str:
    """去除多余空白与控制字符，统一全角标点中的换行。"""
    if not text:
        return ""
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    """中文 2-gram + 英文/数字词。"""
    text = (text or "").lower()
    tokens: List[str] = []
    for seg in _PUNCT.split(text):
        if not seg:
            continue
        if re.match(r"^[\u4e00-\u9fa5]+$", seg):
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
        else:
            tokens.extend(_EN.findall(seg))
    return tokens


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def _hash64(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:16], 16)


def simhash(text: str) -> str:
    """64 位 SimHash，用于采集增量识别与近似去重。"""
    tokens = tokenize(text)
    if not tokens:
        return "0" * 16
    bits = [0] * 64
    for token in tokens:
        h = _hash64(token)
        weight = 1
        for i in range(64):
            bits[i] += weight if (h >> i) & 1 else -weight
    value = 0
    for i in range(64):
        if bits[i] > 0:
            value |= 1 << i
    return format(value, "016x")


def hamming_distance(h1: str, h2: str) -> int:
    if not h1 or not h2 or len(h1) != len(h2):
        return 64
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def truncate(text: str, limit: int = 120, suffix: str = "…") -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + suffix


def extract_dates(text: str) -> List[str]:
    """抽取形如 2024年3月1日 / 2024-03-01 / 2024/3/1 的日期。"""
    if not text:
        return []
    patterns = [
        r"(19|20)\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日",
        r"(19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}",
    ]
    out: List[str] = []
    for pattern in patterns:
        out.extend(m.group(0).strip() for m in re.finditer(pattern, text))
    return out


def normalize_date(text: str) -> str:
    """统一为 YYYY-MM-DD。"""
    if not text:
        return ""
    m = re.search(r"((19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return f"{m.group(1)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
    m = re.search(r"((19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
    return text.strip()
