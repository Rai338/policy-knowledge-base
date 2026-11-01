"""政策知识块切分（ING-005：以"条"为基准粒度，超长或含多款独立事项时按"款"细分）。

输出 RawBlock 列表，含结构路径、条/款号、父子关系与上下文。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.config import MAX_BLOCK_CHARS, MIN_BLOCK_CHARS
from app.core.logging import logger

# 章 / 节 / 条 / 款 / 项
RE_CHAPTER = re.compile(r"^\s*第[一二三四五六七八九十百千]+章")
RE_SECTION = re.compile(r"^\s*第[一二三四五六七八九十百千]+节")
RE_ARTICLE = re.compile(r"^\s*第[一二三四五六七八九十百千〇零\d]{1,8}条")
RE_ARTICLE_NO = re.compile(r"第([一二三四五六七八九十百千〇零\d]{1,8})条")
# 无“第X条”时的等价条级编号：一、 / （一） / 1．
RE_ARTICLE_CN = re.compile(r"^\s*[一二三四五六七八九十]{1,3}、")
RE_ARTICLE_NO_CN = re.compile(r"^([一二三四五六七八九十]{1,3})、")
RE_ARTICLE_PAREN = re.compile(r"^\s*（[一二三四五六七八九十]{1,3}）")
RE_ARTICLE_NO_PAREN = re.compile(r"^（([一二三四五六七八九十]{1,3})）")
RE_ARTICLE_DOT = re.compile(r"^\s*\d{1,2}\s*[．.、](?=\S)")
RE_ARTICLE_NO_DOT = re.compile(r"^(\d{1,2})\s*[．.、](?=\S)")
RE_CLAUSE = re.compile(r"(?:^|\s)((?:（|\()[一二三四五六七八九十]{1,3}(?:）|\)))")
RE_CLAUSE_NUM = re.compile(r"(?:^|\s)(\d{1,2})[\.、](?=\S)")
# 条级候选：名称 → (行首匹配, 编号提取, 小节级匹配)
ARTICLE_CANDIDATES = [
    ("ARTICLE", RE_ARTICLE, RE_ARTICLE_NO, None),
    ("CN_DOT", RE_ARTICLE_DOT, RE_ARTICLE_NO_DOT, RE_ARTICLE_CN),
    ("CN_PAREN", RE_ARTICLE_PAREN, RE_ARTICLE_NO_PAREN, RE_ARTICLE_CN),
    ("CN", RE_ARTICLE_CN, RE_ARTICLE_NO_CN, None),
]
CN_NUM = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class RawBlock:
    text: str = ""
    title: str = ""
    article_number: str = ""
    clause_number: str = ""
    granularity: str = "ARTICLE"      # ARTICLE | CLAUSE
    structure_path: List[str] = field(default_factory=list)
    parent_index: Optional[int] = None  # 父块在列表中的下标（款 → 条）
    page_start: int = 0
    page_end: int = 0


def _cn_to_int(text: str) -> int:
    if text.isdigit():
        return int(text)
    total = 0
    for ch in text:
        total = total * 10 + CN_NUM.get(ch, 0)
    return total


def _detect_page(pages: List[str], needle: str) -> int:
    """按文本片段定位页码（1-based）。"""
    if not pages or not needle:
        return 0
    key = needle[:12]
    for idx, page in enumerate(pages, start=1):
        if key and key in page:
            return idx
    return 0


def _pick_article(lines: List[str]):
    """挑选条级编号模式。

    优先“第X条”；若全文没有“第X条”，则在 1．/（一）/一、 三种常见编号中
    取出现次数最多的一种作为条级粒度，其余更粗的编号降级为章节路径。
    返回 (名称, 行首正则, 编号提取正则, 中间层正则列表)。
    """
    counts = []
    for name, m_re, no_re, sec_re in ARTICLE_CANDIDATES:
        cnt = sum(1 for line in lines if m_re.match(line))
        counts.append((name, m_re, no_re, sec_re, cnt))
    for item in counts:
        if item[0] == "ARTICLE" and item[4] >= 2:
            return item[0], item[1], item[2], []
    usable = [c for c in counts if c[4] >= 2 and c[0] != "ARTICLE"]
    if not usable:
        return None, None, None, []
    name, m_re, no_re, _, _ = max(usable, key=lambda c: c[4])
    if name == "CN_DOT":
        return name, m_re, no_re, [RE_ARTICLE_CN, RE_ARTICLE_PAREN]
    if name == "CN_PAREN":
        return name, m_re, no_re, [RE_ARTICLE_CN]
    return name, m_re, no_re, []


def _article_label(kind: str, number: str) -> str:
    if kind == "ARTICLE":
        return f"第{number}条"
    if kind == "CN_DOT":
        return f"{number}."
    if kind == "CN_PAREN":
        return f"（{number}）"
    return f"{number}、"


def split_clauses(text: str, prefer_num: bool = False) -> List[tuple]:
    """在条内按"款"切分，返回 [(款号, 文本), ...]。"""
    pattern = RE_CLAUSE_NUM if prefer_num else RE_CLAUSE
    marks = [(m.start(), m.end(), m.group(1)) for m in pattern.finditer(text)]
    if len(marks) < 2:
        pattern = RE_CLAUSE if prefer_num else RE_CLAUSE_NUM
        marks = [(m.start(), m.end(), m.group(1)) for m in pattern.finditer(text)]
    if len(marks) < 2:
        return []
    items = []
    head = text[: marks[0][0]].strip()
    if head:
        items.append(("", head))
    for i, (start, end, label) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        items.append((label, text[start:stop].strip()))
    return [(label.strip("（）()"), body) for label, body in items if body]


def chunk_text(text: str, pages: Optional[List[str]] = None) -> List[RawBlock]:
    """把政策全文切分为知识块。"""
    pages = pages or []
    lines = [line.strip() for line in text.splitlines()]
    blocks: List[RawBlock] = []

    kind, art_re, art_no_re, section_res = _pick_article(lines)
    blocks: List[RawBlock] = []

    chapter, section = "", ""
    buffer: List[str] = []
    current_article = ""

    def flush():
        nonlocal buffer
        body = "\n".join(buffer).strip()
        buffer = []
        if len(body) < MIN_BLOCK_CHARS:
            return
        blocks.append(
            RawBlock(
                text=body,
                article_number=current_article,
                granularity="ARTICLE",
                structure_path=[p for p in (chapter, section) if p],
                page_start=_detect_page(pages, body[:12]),
                page_end=_detect_page(pages, body[-12:]) or _detect_page(pages, body[:12]),
            )
        )

    for line in lines:
        if not line:
            continue
        # 中间层（章/节）：第X章、第X节，或 一、/（一）
        hit_section = False
        if kind == "ARTICLE":
            if RE_CHAPTER.match(line):
                flush()
                chapter, section = line[:40], ""
                hit_section = True
            elif RE_SECTION.match(line):
                flush()
                section = line[:40]
                hit_section = True
        else:
            for idx, sec_re in enumerate(section_res):
                if sec_re.match(line):
                    flush()
                    if idx == 0:
                        chapter, section = line[:40], ""
                    else:
                        section = line[:40]
                    hit_section = True
                    break
        if hit_section:
            continue
        if art_re is not None and art_re.match(line):
            flush()
            m = art_no_re.match(line) if art_no_re else None
            current_article = _article_label(kind, m.group(1)) if m else line[:10]
            buffer = [line]
            continue
        buffer.append(line)
    flush()

    if not blocks:
        # 兜底：按段落聚合
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= MIN_BLOCK_CHARS]
        blocks = [
            RawBlock(
                text=p,
                granularity="ARTICLE",
                page_start=_detect_page(pages, p[:12]),
                page_end=_detect_page(pages, p[-12:]) or _detect_page(pages, p[:12]),
            )
            for p in paras
        ]

    # 超长或多款 → 按款细分（父块保留为条级块）
    final: List[RawBlock] = []
    prefer_num = kind == "CN_PAREN"        # 条级已是“（一）”时，款级改用数字编号
    clause_re = RE_CLAUSE_NUM if prefer_num else RE_CLAUSE
    for block in blocks:
        need_split = len(block.text) > MAX_BLOCK_CHARS or len(clause_re.findall(block.text)) >= 2
        clauses = split_clauses(block.text, prefer_num=prefer_num) if need_split else []
        if not clauses:
            block.title = _make_title(block)
            final.append(block)
            continue
        parent_idx = len(final)
        final.append(block)
        block.granularity = "ARTICLE"
        block.title = _make_title(block)
        for clause_no, clause_text in clauses:
            if len(clause_text) < MIN_BLOCK_CHARS:
                continue
            final.append(
                RawBlock(
                    text=clause_text,
                    article_number=block.article_number,
                    clause_number=clause_no,
                    granularity="CLAUSE",
                    structure_path=list(block.structure_path),
                    parent_index=parent_idx,
                    page_start=_detect_page(pages, clause_text[:12]) or block.page_start,
                    page_end=_detect_page(pages, clause_text[-12:]) or block.page_end,
                    title=_make_title(block, clause_no),
                )
            )
    logger.info("切分完成：%s 个知识块（含款级 %s）",
                len(final), sum(1 for b in final if b.granularity == "CLAUSE"))
    return final


RE_LEAD_NUMBER = re.compile(
    r"^(?:第[一二三四五六七八九十百千〇零\d]{1,8}条"
    r"|[一二三四五六七八九十]{1,3}、"
    r"|（[一二三四五六七八九十]{1,3}）"
    r"|\d{1,2}\s*[．.、])\s*"
)


def _make_title(block: RawBlock, clause_no: str = "") -> str:
    parts = [p for p in block.structure_path if p]
    if block.article_number:
        parts.append(block.article_number)
    if clause_no:
        parts.append(f"第{clause_no}款")
    head = block.text.splitlines()[0][:24] if block.text else ""
    # 条号已在标题前缀中体现，正文开头的重复编号不再展示
    if block.article_number:
        head = RE_LEAD_NUMBER.sub("", head, count=1)
    title = " / ".join(parts)
    return f"{title}｜{head}" if title and head else (title or head)
