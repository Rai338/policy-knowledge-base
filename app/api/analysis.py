"""解读与知识关联接口（ANA-001～007）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.response import BizException, ok
from app.db.database import get_db
from app.services import analysis_service

router = APIRouter(prefix="/analysis", tags=["解读与关联"])


class TermPayload(BaseModel):
    term: str
    operator: str = "user"


class ApplicabilityPayload(BaseModel):
    subject: str = ""
    region: str = ""
    topic: str = ""
    page_size: int = 10


@router.get("/summary/{document_id}")
def summary(document_id: str, db: Session = Depends(get_db), operator: str = Query("user")):
    try:
        return ok(analysis_service.summarize(db, document_id, operator))
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)


@router.get("/interpret/{document_id}")
def interpret(document_id: str, db: Session = Depends(get_db), operator: str = Query("user")):
    try:
        return ok(analysis_service.interpret(db, document_id, operator))
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)


@router.post("/term")
def explain_term(payload: TermPayload, db: Session = Depends(get_db)):
    try:
        return ok(analysis_service.explain_term(db, payload.term, payload.operator))
    except ValueError as exc:
        raise BizException(str(exc))


@router.get("/related")
def related(db: Session = Depends(get_db), document_id: str = Query(""),
            block_id: str = Query(""), top_k: int = Query(6, ge=1, le=20)):
    if not document_id and not block_id:
        raise BizException("请提供 document_id 或 block_id")
    try:
        return ok(analysis_service.related(db, document_id, block_id, top_k))
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)


@router.get("/compare/{document_id}")
def compare(document_id: str, db: Session = Depends(get_db)):
    try:
        return ok(analysis_service.compare_versions(db, document_id))
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)


@router.post("/applicability")
def applicability(payload: ApplicabilityPayload, db: Session = Depends(get_db)):
    return ok(
        analysis_service.judge_applicability(
            db, payload.subject, payload.region, payload.topic, payload.page_size
        )
    )
