"""审计日志服务（LOG-001～003）：操作、检索、问答全过程留痕。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import OperationLog, QALog, SearchLog


def log_operation(db: Session, action: str, target_type: str = "", target_id: str = "",
                  operator: str = "system", detail: Optional[dict] = None) -> OperationLog:
    record = OperationLog(
        action=action,
        target_type=target_type,
        target_id=target_id,
        operator=operator,
        detail=detail or {},
    )
    db.add(record)
    db.commit()
    return record


def log_search(db: Session, keyword: str, filters: dict, result_count: int, latency_ms: int) -> SearchLog:
    record = SearchLog(
        keyword=keyword,
        filters=filters or {},
        result_count=result_count,
        latency_ms=latency_ms,
    )
    db.add(record)
    db.commit()
    return record


def log_qa(db: Session, question: str, answer: str, citations: list, refused: bool,
           refuse_reason: str, evidence_score: float, latency_ms: int,
           backend: str, session_id: str = "", operator: str = "user") -> QALog:
    record = QALog(
        session_id=session_id,
        question=question,
        answer=answer,
        citations=citations or [],
        refused=bool(refused),
        refuse_reason=refuse_reason,
        evidence_score=evidence_score,
        latency_ms=latency_ms,
        llm_backend=backend,
        operator=operator,
    )
    db.add(record)
    db.commit()
    return record


def set_feedback(db: Session, log_id: str, feedback: str, note: str = "") -> bool:
    record = db.query(QALog).filter(QALog.id == log_id).first()
    if not record:
        return False
    record.feedback = feedback
    record.feedback_note = note
    db.commit()
    return True
