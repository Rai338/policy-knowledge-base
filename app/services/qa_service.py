"""可追溯问答（QA-001～007）：召回 → 证据充分性判定 → 生成 → 引用解析 → 留痕。

核心约束：
- 仅使用检索到的现行有效依据；
- 每个结论句必须带引用编号，编号对应的知识块必须真实存在（不虚构）；
- 证据不足时直接拒答，不做推测。
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import MAX_CONTEXT_CHARS, TOP_K_RERANK
from app.db.models import QALog
from app.services import audit_service
from app.services.llm import LLMError, extractive_answer, get_llm
from app.services.retriever import is_evidence_enough, recall_for_qa

SYSTEM_PROMPT = (
    "你是政策知识库智能助手。只能依据【检索依据】中给出的材料作答，严禁使用材料之外的知识或进行推测。\n"
    "要求：\n"
    "1. 每个结论句末尾用 [编号] 标注依据，编号只能取自材料列表，如 [1][2]；\n"
    "2. 若材料不足以支撑结论，必须回答“依据不足，无法确定”，并说明缺少哪方面依据；\n"
    "3. 不得引用已废止或已失效的文件；\n"
    "4. 用简洁的中文分条作答，避免空话。"
)

REFUSE_TEXT = "知识库中未检索到足以支撑该问题的现行有效依据，暂不作答。"


def _build_context(evidence: List[Dict]) -> str:
    lines = []
    used = 0
    for idx, item in enumerate(evidence, start=1):
        text = " ".join((item.get("original_text") or "").split())
        title = item.get("document_title") or item.get("title") or "未命名文件"
        anchor = item.get("article_number") or ""
        chunk = text[:900]
        lines.append(f"[{idx}] 《{title}》{anchor}\n原文：{chunk}")
        used += len(chunk)
        if used > MAX_CONTEXT_CHARS:
            break
    return "\n\n".join(lines)


def _parse_citations(answer: str, evidence: List[Dict]) -> List[Dict]:
    """把答案中的 [n] 映射为真实知识块引用（编号不存在的直接丢弃）。"""
    numbers = []
    for match in re.finditer(r"\[(\d{1,2})\]", answer):
        num = int(match.group(1))
        if num not in numbers:
            numbers.append(num)
    citations = []
    for num in numbers:
        if num < 1 or num > len(evidence):
            continue
        item = evidence[num - 1]
        citations.append(
            {
                "index": num,
                "block_id": item["block_id"],
                "document_id": item["document_id"],
                "document_title": item.get("document_title") or item.get("title"),
                "article_number": item.get("article_number", ""),
                "clause_number": item.get("clause_number", ""),
                "effect_level_name": item.get("effect_level_name", ""),
                "validity_status": item.get("validity_status", ""),
                "publish_date": item.get("publish_date", ""),
                "page_start": item.get("page_start", 0),
                "source_url": item.get("source_url", ""),
                "quote": " ".join((item.get("original_text") or "").split())[:160],
                "score": item.get("evidence_score", 0.0),
            }
        )
    return citations


def ask(db: Session, question: str, session_id: str = "", filters: Optional[Dict] = None,
        top_k: int = TOP_K_RERANK, operator: str = "user") -> Dict:
    started = time.time()
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")

    evidence = recall_for_qa(db, question, filters, top_k=top_k)
    llm = get_llm()
    backend = llm.backend

    if not is_evidence_enough(evidence):
        refused = True
        answer = REFUSE_TEXT + "建议调整关键词，或先导入相关政策文件后再提问。"
        reason = "检索证据得分低于阈值，判定为证据不足（QA-006 拒答机制）"
        citations: List[Dict] = []
        top_score = max((e["evidence_score"] for e in evidence), default=0.0)
    else:
        refused = False
        reason = ""
        top_score = max(e["evidence_score"] for e in evidence)
        context = _build_context(evidence)
        try:
            answer = llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"【检索依据】\n{context}\n\n【问题】{question}\n\n请按规则作答。",
                    },
                ]
            )
        except LLMError as exc:
            backend = "extractive"
            answer = extractive_answer(question, evidence)
            logger_hint = f"（大模型不可用，已切换为原文摘录模式：{exc}）"
            answer = f"{answer}\n\n{logger_hint}"

    citations = _parse_citations(answer, evidence) if not refused else []
    latency = int((time.time() - started) * 1000)
    log = audit_service.log_qa(
        db, question, answer, citations, refused, reason, top_score, latency, backend, session_id, operator
    )
    return {
        "log_id": log.id,
        "session_id": session_id,
        "question": question,
        "answer": answer,
        "citations": citations,
        "refused": refused,
        "refuse_reason": reason,
        "evidence": evidence,
        "evidence_score": round(top_score, 6),
        "latency_ms": latency,
        "llm_backend": backend,
    }


def feedback(db: Session, log_id: str, feedback_value: str, note: str = "") -> bool:
    ok = audit_service.set_feedback(db, log_id, feedback_value, note)
    if ok:
        audit_service.log_operation(db, "FEEDBACK", "QALog", log_id, "user",
                                    {"feedback": feedback_value, "note": note})
    return ok


def history(db: Session, page: int = 1, page_size: int = 10, session_id: str = ""):
    query = db.query(QALog)
    if session_id:
        query = query.filter(QALog.session_id == session_id)
    total = query.count()
    items = (
        query.order_by(QALog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": item.id,
                "question": item.question,
                "answer": item.answer,
                "refused": item.refused,
                "citations": item.citations,
                "latency_ms": item.latency_ms,
                "llm_backend": item.llm_backend,
                "feedback": item.feedback,
                "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
            }
            for item in items
        ],
        "total": total,
    }
