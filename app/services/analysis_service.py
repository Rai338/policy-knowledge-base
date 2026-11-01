"""解读与知识关联（ANA-001～007）：摘要、要点解读、术语解释、关联推荐、修订对照、适用性判定。

大模型不可用时自动切换为基于规则的抽取式实现，保证功能可用。
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.constants import EFFECT_LEVEL_NAME
from app.core.logging import logger
from app.db.models import Document, DocumentVersion, PolicyBlock
from app.services import audit_service
from app.services.indexer import get_index
from app.services.llm import LLMError, get_llm
from app.services.serializer import block_to_dict, document_to_dict

KEY_PATTERNS = [
    ("适用对象", r"(适用于|适用对象|申报主体|支持对象|面向)"),
    ("支持措施", r"(给予|补贴|奖励|支持|资助|减免|补助|奖补)"),
    ("申报条件", r"(应当符合|须满足|条件|资格|要求)"),
    ("时间节点", r"(自.{0,12}起施行|有效期|截止|申报时间|受理时间)"),
    ("责任部门", r"(负责|组织实施|主管部门|牵头)"),
]


def _document_blocks(db: Session, document_id: str) -> List[PolicyBlock]:
    return (
        db.query(PolicyBlock)
        .filter(PolicyBlock.document_id == document_id)
        .order_by(PolicyBlock.article_number, PolicyBlock.block_id)
        .all()
    )


def _rule_based_summary(document: Document, blocks: List[PolicyBlock]) -> Dict:
    """抽取式摘要：从命中政策关键词的条款中抽取要点，拼接为可读摘要。"""
    highlights = []
    for block in blocks[:80]:
        text = " ".join((block.original_text or "").split())
        if re.search(r"(应当|不得|给予|支持|补贴|奖励|减免|补助|条件|比例|期限|申报|对象|享受|鼓励|培育|打造)", text) and len(text) > 20:
            highlights.append(
                {
                    "block_id": block.block_id,
                    "article_number": block.article_number,
                    "text": text[:160],
                }
            )
        if len(highlights) >= 6:
            break
    if highlights:
        summary = "；".join(
            f"{h['article_number']} {h['text'][:70]}" for h in highlights[:4]
        )
    else:
        # 关键词未命中时，退而取前几条内容作为概览，避免“共切分 N 块”这类无效摘要
        preview = []
        for block in blocks[:3]:
            t = " ".join((block.original_text or "").split())
            if t:
                preview.append(f"{block.article_number} {t[:70]}")
        summary = "；".join(preview) if preview else f"《{document.title}》共切分 {len(blocks)} 个知识块。"
    return {
        "summary": summary,
        "highlights": highlights,
    }


def summarize(db: Session, document_id: str, operator: str = "user") -> Dict:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError("文件不存在")
    blocks = _document_blocks(db, document_id)
    base = _rule_based_summary(document, blocks)
    result = {
        "document": document_to_dict(document, len(blocks)),
        "summary": base["summary"],
        "highlights": base["highlights"],
        "block_count": len(blocks),
        "mode": "rule",
    }
    context = "\n".join(
        f"{b.article_number or ''} {' '.join((b.original_text or '').split())[:200]}" for b in blocks[:40]
    )
    try:
        import json

        content = get_llm().chat(
            [
                {"role": "system", "content": "你是政策分析助手，只依据给定材料概括，输出严格 JSON，不得虚构。"},
                {
                    "role": "user",
                    "content": (
                        f"材料：\n{context}\n\n"
                        "请输出 JSON：{\"summary\": \"200字以内摘要\", \"points\": [\"要点1\", \"要点2\", \"要点3\"]}"
                    ),
                },
            ],
            temperature=0.2,
        )
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", content.strip()).strip())
    except (LLMError, ValueError) as exc:
        logger.info("摘要未使用大模型（%s），采用规则抽取结果", exc)
        data = None
    if isinstance(data, dict) and data.get("summary"):
        result["summary"] = data["summary"]
        result["points"] = data.get("points", [])
        result["mode"] = "llm"
    else:
        result["points"] = [h["text"] for h in base["highlights"][:5]]
    _save_summary(db, document, result["summary"])
    audit_service.log_operation(db, "ANALYZE", "DOCUMENT", document_id, operator, {"type": "summary"})
    return result


def _save_summary(db: Session, document: Document, summary: str) -> None:
    if summary and not document.summary:
        document.summary = summary[:500]
        db.commit()


def interpret(db: Session, document_id: str, operator: str = "user") -> Dict:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError("文件不存在")
    blocks = _document_blocks(db, document_id)
    dimensions = []
    for name, pattern in KEY_PATTERNS:
        hits = []
        for block in blocks:
            text = " ".join((block.original_text or "").split())
            if re.search(pattern, text):
                hits.append(
                    {
                        "block_id": block.block_id,
                        "article_number": block.article_number,
                        "text": text[:200],
                    }
                )
            if len(hits) >= 5:
                break
        dimensions.append({"dimension": name, "items": hits})
    audit_service.log_operation(db, "ANALYZE", "DOCUMENT", document_id, operator, {"type": "interpret"})
    return {
        "document": document_to_dict(document, len(blocks)),
        "dimensions": dimensions,
        "mode": "rule",
    }


def explain_term(db: Session, term: str, operator: str = "user") -> Dict:
    term = (term or "").strip()
    if not term:
        raise ValueError("术语不能为空")
    blocks = (
        db.query(PolicyBlock)
        .filter(PolicyBlock.original_text.like(f"%{term}%"))
        .limit(8)
        .all()
    )
    evidence = [
        {
            "block_id": b.block_id,
            "document_title": b.title,
            "article_number": b.article_number,
            "text": " ".join((b.original_text or "").split())[:200],
        }
        for b in blocks
    ]
    explanation = ""
    mode = "rule"
    if evidence:
        first = evidence[0]
        idx = first["text"].find(term)
        snippet = first["text"][max(0, idx - 40) : idx + 120]
        explanation = f"在《{first['document_title']}》{first['article_number']}中出现：…{snippet}…"
    try:
        content = get_llm().chat(
            [
                {"role": "system", "content": "你是政策术语解释助手，只能依据材料解释，标注出处编号。"},
                {
                    "role": "user",
                    "content": f"材料：\n" + "\n".join(f"[{i+1}] {e['text']}" for i, e in enumerate(evidence))
                    + f"\n\n请解释术语“{term}”，不超过150字。",
                },
            ]
        )
        if content:
            explanation = content
            mode = "llm"
    except LLMError:
        pass
    audit_service.log_operation(db, "ANALYZE", "TERM", term, operator, {"hits": len(evidence)})
    return {"term": term, "explanation": explanation or "未检索到该术语的相关政策表述。", "evidence": evidence, "mode": mode}


def related(db: Session, document_id: str = "", block_id: str = "", top_k: int = 6) -> Dict:
    """关联政策：向量相似 + 同主题 + 上位法引用（ANA-004）。"""
    index = get_index()
    similar: List[Dict] = []
    higher_law: List[str] = []
    base_topics: List[str] = []

    if block_id:
        block = db.query(PolicyBlock).filter(PolicyBlock.block_id == block_id).first()
        if not block:
            raise ValueError("知识块不存在")
        similar = index.similar_blocks(block_id, top_k)
        higher_law = list(block.higher_law_refs or [])
        base_topics = list(block.topics or [])
        document_id = block.document_id
    elif document_id:
        blocks = _document_blocks(db, document_id)
        if not blocks:
            raise ValueError("该文件暂无知识块")
        higher_law = list(blocks[0].higher_law_refs or [])
        base_topics = list(blocks[0].topics or [])
        similar = index.similar_blocks(blocks[0].block_id, top_k)

    ids = [item["block_id"] for item in similar]
    blocks = {b.block_id: b for b in db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all()} if ids else {}
    docs = {}
    if blocks:
        doc_ids = {b.document_id for b in blocks.values()}
        docs = {d.id: d.title for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()}
    items = []
    for item in similar:
        block = blocks.get(item["block_id"])
        if not block:
            continue
        items.append(
            {
                **block_to_dict(block, docs.get(block.document_id, ""), item.get("score", 0.0)),
                "relation": "内容相似",
            }
        )

    # 同主题补充
    if base_topics:
        for block in (
            db.query(PolicyBlock)
            .filter(PolicyBlock.document_id != document_id)
            .limit(400)
            .all()
        ):
            if set(base_topics) & set(block.topics or []) and block.block_id not in blocks:
                items.append(
                    {
                        **block_to_dict(block, block.title, 0.0),
                        "relation": "同一主题",
                    }
                )
            if len(items) >= top_k + 4:
                break

    higher_matches = []
    if higher_law:
        for name in higher_law:
            matched = (
                db.query(Document).filter(Document.title.like(f"%{name}%")).limit(3).all()
            )
            for doc in matched:
                higher_matches.append(
                    {
                        "document_id": doc.id,
                        "title": doc.title,
                        "effect_level_name": EFFECT_LEVEL_NAME.get(doc.effect_level, doc.effect_level),
                        "relation": "上位法引用",
                    }
                )
    return {
        "items": items[: top_k + 4],
        "higher_law": higher_law,
        "higher_matches": higher_matches,
        "topics": base_topics,
    }


def compare_versions(db: Session, document_id: str) -> Dict:
    """修订对照（ANA-006）：版本列表 + 内容级差异统计。"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError("文件不存在")
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_no)
        .all()
    )
    blocks = _document_blocks(db, document_id)
    current_hashes = {b.content_hash for b in blocks}
    return {
        "document": document_to_dict(document, len(blocks)),
        "versions": [
            {
                "id": v.id,
                "version_no": v.version_no,
                "version_label": v.version_label,
                "is_current": v.is_current,
                "change_note": v.change_note,
                "revised_from": v.revised_from,
                "created_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S") if v.created_at else "",
            }
            for v in versions
        ],
        "diff": {
            "current_block_count": len(blocks),
            "current_hash_count": len(current_hashes),
            "note": "逐版本块级差异：以内容 hash 集合比对，未在上版出现的块即为新增/修订块。",
        },
    }


def _contains_any(values, query: str) -> bool:
    """双向子串匹配：query 命中任一标签，或任一标签是 query 的子串（如“中小微企业”命中“企业”）。"""
    q = (query or "").strip()
    if not q:
        return True
    for v in (values or []):
        if q in v or v in q:
            return True
    return False


def judge_applicability(db: Session, subject: str = "", region: str = "",
                        topic: str = "", page_size: int = 10) -> Dict:
    """适用主体判定（ANA-007）：按主体类型 / 地域 / 主题筛选适用条款。

    匹配策略：结构化标签双向子串命中，或条款正文包含关键词（兜底），
    避免“中小微企业”因标签只有“企业”而完全查不到。
    """
    candidates = db.query(PolicyBlock).limit(2000).all()
    blocks = []
    for b in candidates:
        text = b.original_text or ""
        if subject and not (_contains_any(b.applicable_subjects, subject) or subject in text):
            continue
        if topic and not (_contains_any(b.topics, topic) or topic in text):
            continue
        if region and not (region in (b.jurisdiction or []) or "全国" in (b.jurisdiction or [])):
            continue
        blocks.append(b)
    doc_ids = {b.document_id for b in blocks}
    docs = {d.id: d.title for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()} if doc_ids else {}
    items = [block_to_dict(b, docs.get(b.document_id, "")) for b in blocks[:page_size]]
    return {
        "filters": {"subject": subject, "region": region, "topic": topic},
        "total": len(blocks),
        "items": items,
    }
