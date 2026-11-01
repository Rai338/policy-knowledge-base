"""序列化：ORM 对象 → API 出参字典（统一字段命名与空值处理）。"""
from __future__ import annotations

import datetime as dt
import html
import re
from typing import List, Optional

from app.core.constants import (
    DOC_CATEGORY_NAME,
    EFFECT_LEVEL_NAME,
    EFFECT_LEVEL_RANK,
    VALIDITY_STATUS,
)


def _category(block_or_doc) -> str:
    """兼容旧数据：缺失 doc_category 时按位阶推断。"""
    value = getattr(block_or_doc, "doc_category", "") or ""
    if value:
        return value
    from app.core.constants import category_of_level

    return category_of_level(getattr(block_or_doc, "effect_level", "OTHER"))


def _fmt_time(value) -> str:
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def highlight(text: str, keywords: List[str], width: int = 220) -> str:
    """生成命中片段：转义 HTML 后用 <em> 标记关键词。"""
    if not text:
        return ""
    safe = html.escape(text)
    for keyword in [k for k in keywords if k and len(k) >= 1]:
        safe = re.sub(
            f"({re.escape(html.escape(keyword))})",
            r'<em class="hl">\1</em>',
            safe,
            flags=re.IGNORECASE,
        )
    if len(safe) <= width:
        return safe
    idx = safe.find('<em class="hl">')
    start = max(0, idx - 60) if idx >= 0 else 0
    return ("…" if start > 0 else "") + safe[start : start + width] + "…"


def block_to_dict(block, document_title: str = "", score: float = 0.0,
                  keywords: Optional[List[str]] = None) -> dict:
    return {
        "block_id": block.block_id,
        "document_id": block.document_id,
        "document_title": document_title or block.title or "",
        "title": block.title,
        "article_number": block.article_number,
        "clause_number": block.clause_number,
        "granularity": block.granularity,
        "structure_path": list(block.structure_path or []),
        "effect_level": block.effect_level,
        "effect_level_name": EFFECT_LEVEL_NAME.get(block.effect_level, block.effect_level),
        "doc_category": _category(block),
        "doc_category_name": DOC_CATEGORY_NAME.get(_category(block), "政策文件"),
        "hierarchy_rank": block.hierarchy_rank,
        "topics": list(block.topics or []),
        "jurisdiction": list(block.jurisdiction or []),
        "applicable_subjects": list(block.applicable_subjects or []),
        "validity_status": block.validity_status,
        "validity_status_name": VALIDITY_STATUS.get(block.validity_status, block.validity_status),
        "publish_date": block.publish_date,
        "effective_date": block.effective_date,
        "expiry_date": block.expiry_date,
        "issuing_authority": list(block.issuing_authority or []),
        "document_number": block.document_number,
        "institution_level": block.institution_level,
        "source_url": block.source_url,
        "page_start": block.page_start,
        "page_end": block.page_end,
        "source_anchor": block.source_anchor,
        "original_text": block.original_text,
        "context_before": block.context_before,
        "context_after": block.context_after,
        "review_status": block.review_status,
        "higher_law_refs": list(block.higher_law_refs or []),
        "related_blocks": list(block.related_blocks or []),
        "content_hash": block.content_hash,
        "score": round(float(score), 6),
        "highlight": highlight(block.original_text, keywords or []),
        "created_at": _fmt_time(block.created_at),
    }


def document_to_dict(doc, block_count: int = 0) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "document_number": doc.document_number,
        "issuing_authority": list(doc.issuing_authority or []),
        "effect_level": doc.effect_level,
        "effect_level_name": EFFECT_LEVEL_NAME.get(doc.effect_level, doc.effect_level),
        "doc_category": _category(doc),
        "doc_category_name": DOC_CATEGORY_NAME.get(_category(doc), "政策文件"),
        "institution_level": doc.institution_level,
        "jurisdiction": list(doc.jurisdiction or []),
        "topics": list(doc.topics or []),
        "applicable_subjects": list(doc.applicable_subjects or []),
        "publish_date": doc.publish_date,
        "effective_date": doc.effective_date,
        "expiry_date": doc.expiry_date,
        "validity_status": doc.validity_status,
        "validity_status_name": VALIDITY_STATUS.get(doc.validity_status, doc.validity_status),
        "level_reason": getattr(doc, "level_reason", "") or "",
        "validity_reason": getattr(doc, "validity_reason", "") or "",
        "hierarchy_rank": EFFECT_LEVEL_RANK.get(doc.effect_level, 10),
        "summary": doc.summary,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "status": doc.status,
        "error_message": doc.error_message,
        "block_count": block_count if block_count else doc.block_count,
        "view_count": doc.view_count,
        "created_at": _fmt_time(doc.created_at),
        "updated_at": _fmt_time(doc.updated_at),
    }
