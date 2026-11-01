"""采集接口（CRAWL-001～012）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.response import BizException, ok, paged
from app.db.database import get_db
from app.services import crawl_service
from app.tasks.scheduler import scheduler

router = APIRouter(prefix="/crawl", tags=["实时采集"])


class SourcePayload(BaseModel):
    name: str = ""
    url: str = ""
    source_type: str = "LIST"
    frequency: str = "NORMAL"
    institution_level: str = "OTHER"
    default_topics: list = []
    list_selector: str = "a"
    title_keywords: str = ""
    enabled: bool = True


@router.get("/sources")
def sources(db: Session = Depends(get_db), keyword: str = Query(""),
            page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    data = crawl_service.list_sources(db, page, page_size, keyword)
    return paged(data["items"], data["total"], page, page_size)


@router.post("/sources/test")
def test_source(payload: SourcePayload):
    """保存前"测试抓取"：即时抓取并预览解析结果，不入库。"""
    return ok(crawl_service.test_source(payload.dict()))


@router.post("/sources")
def create_source(payload: SourcePayload, db: Session = Depends(get_db), operator: str = Query("user")):
    try:
        source = crawl_service.create_source(db, payload.dict(), operator)
    except ValueError as exc:
        raise BizException(str(exc))
    scheduler.sync()
    return ok({"id": source.id}, "信源已创建并加入调度")


@router.put("/sources/{source_id}")
def update_source(source_id: str, payload: SourcePayload, db: Session = Depends(get_db),
                  operator: str = Query("user")):
    data = {k: v for k, v in payload.dict().items() if v not in ("", [], None) or k == "enabled"}
    source = crawl_service.update_source(db, source_id, data, operator)
    if not source:
        raise BizException("信源不存在", status_code=404)
    scheduler.sync()
    return ok({"id": source.id}, "信源已更新")


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db), operator: str = Query("user")):
    if not crawl_service.delete_source(db, source_id, operator):
        raise BizException("信源不存在", status_code=404)
    scheduler.sync()
    return ok(message="信源已删除")


@router.post("/sources/{source_id}/run")
def run_source(source_id: str, db: Session = Depends(get_db), operator: str = Query("user")):
    try:
        result = crawl_service.run_source(db, source_id, operator)
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)
    return ok(result, f"采集完成：发现 {result['found']} 条，新增 {result['new']} 条，更新 {result['updated']} 条")


@router.post("/run-all")
def run_all(db: Session = Depends(get_db), operator: str = Query("user")):
    results = crawl_service.run_all(db, operator)
    return ok({"results": results, "sources": len(results)}, f"已执行 {len(results)} 个信源")


@router.get("/records")
def records(db: Session = Depends(get_db), source_id: str = Query(""), status: str = Query(""),
            keyword: str = Query(""), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    data = crawl_service.records(db, page, page_size, source_id, status, keyword)
    return paged(data["items"], data["total"], page, page_size)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return ok(crawl_service.stats(db))


@router.get("/jobs")
def jobs():
    return ok({"jobs": scheduler.jobs(), "running": bool(scheduler.scheduler and scheduler.scheduler.running)})


@router.post("/sync")
def sync():
    count = scheduler.sync()
    return ok({"jobs": count}, f"已装载 {count} 个采集任务")
