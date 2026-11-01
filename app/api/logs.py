"""日志接口（LOG-001～003）：操作、检索、问答留痕查询。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import LOG_ACTIONS
from app.core.response import ok, paged
from app.db.database import get_db
from app.db.models import OperationLog, QALog, SearchLog

router = APIRouter(prefix="/logs", tags=["日志"])


@router.get("/operations")
def operations(db: Session = Depends(get_db), action: str = Query(""), keyword: str = Query(""),
               start: str = Query(""), end: str = Query(""),
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)):
    query = db.query(OperationLog)
    if action:
        query = query.filter(OperationLog.action == action)
    if keyword:
        query = query.filter(OperationLog.target_id.like(f"%{keyword}%"))
    if start:
        query = query.filter(OperationLog.created_at >= start)
    if end:
        try:
            end_dt = (dt.datetime.strptime(end, "%Y-%m-%d") + dt.timedelta(days=1)).strftime("%Y-%m-%d")
            query = query.filter(OperationLog.created_at < end_dt)
        except ValueError:
            pass
    total = query.count()
    items = query.order_by(OperationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paged(
        [
            {
                "id": i.id,
                "action": i.action,
                "action_name": LOG_ACTIONS.get(i.action, i.action),
                "target_type": i.target_type,
                "target_id": i.target_id,
                "operator": i.operator,
                "detail": i.detail,
                "created_at": i.created_at.strftime("%Y-%m-%d %H:%M:%S") if i.created_at else "",
            }
            for i in items
        ],
        total,
        page,
        page_size,
    )


@router.get("/search")
def search_logs(db: Session = Depends(get_db), page: int = Query(1, ge=1),
                page_size: int = Query(20, ge=1, le=200)):
    query = db.query(SearchLog)
    total = query.count()
    items = query.order_by(SearchLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paged(
        [
            {
                "id": i.id,
                "keyword": i.keyword,
                "filters": i.filters,
                "result_count": i.result_count,
                "latency_ms": i.latency_ms,
                "created_at": i.created_at.strftime("%Y-%m-%d %H:%M:%S") if i.created_at else "",
            }
            for i in items
        ],
        total,
        page,
        page_size,
    )


@router.get("/qa")
def qa_logs(db: Session = Depends(get_db), refused: str = Query(""), page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=200)):
    query = db.query(QALog)
    if refused in ("true", "false"):
        query = query.filter(QALog.refused.is_(refused == "true"))
    total = query.count()
    items = query.order_by(QALog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paged(
        [
            {
                "id": i.id,
                "question": i.question,
                "answer": i.answer,
                "refused": i.refused,
                "citations": i.citations,
                "evidence_score": i.evidence_score,
                "latency_ms": i.latency_ms,
                "llm_backend": i.llm_backend,
                "feedback": i.feedback,
                "created_at": i.created_at.strftime("%Y-%m-%d %H:%M:%S") if i.created_at else "",
            }
            for i in items
        ],
        total,
        page,
        page_size,
    )


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    today = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    by_action = dict(db.query(OperationLog.action, func.count(OperationLog.id)).group_by(OperationLog.action).all())
    today_ops = db.query(OperationLog).filter(OperationLog.created_at >= today).count()
    return ok(
        {
            "by_action": by_action,
            "action_names": LOG_ACTIONS,
            "today_operations": today_ops,
            "total_operations": db.query(OperationLog).count(),
        }
    )
