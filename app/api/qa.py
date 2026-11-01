"""问答接口（QA-001～007）。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.response import BizException, ok, paged
from app.db.database import get_db
from app.services import qa_service

router = APIRouter(prefix="/qa", tags=["问答"])


class AskPayload(BaseModel):
    question: str
    session_id: str = ""
    top_k: int = 5
    operator: str = "user"
    filters: Optional[dict] = None


class FeedbackPayload(BaseModel):
    log_id: str
    feedback: str
    note: str = ""


@router.post("/ask")
def ask(payload: AskPayload, db: Session = Depends(get_db)):
    try:
        result = qa_service.ask(
            db,
            question=payload.question,
            session_id=payload.session_id,
            filters=payload.filters,
            top_k=payload.top_k,
            operator=payload.operator,
        )
    except ValueError as exc:
        raise BizException(str(exc))
    return ok(result)


@router.post("/feedback")
def feedback(payload: FeedbackPayload, db: Session = Depends(get_db)):
    if payload.feedback not in ("UP", "DOWN"):
        raise BizException("反馈值应为 UP 或 DOWN")
    if not qa_service.feedback(db, payload.log_id, payload.feedback, payload.note):
        raise BizException("问答记录不存在", status_code=404)
    return ok(message="感谢反馈")


@router.get("/history")
def history(db: Session = Depends(get_db), session_id: str = Query(""),
            page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    data = qa_service.history(db, page, page_size, session_id)
    return paged(data["items"], data["total"], page, page_size)
