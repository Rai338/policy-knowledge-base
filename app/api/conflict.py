"""冲突初筛接口（CON-001～005）。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.constants import CONFLICT_DIMENSIONS
from app.core.response import BizException, ok, paged
from app.db.database import get_db
from app.services import conflict_service

router = APIRouter(prefix="/conflict", tags=["冲突初筛"])


class TaskPayload(BaseModel):
    name: str = "冲突检测任务"
    document_ids: List[str] = []
    dimensions: List[str] = []
    region: str = ""
    operator: str = "user"


@router.post("/tasks")
def create_task(payload: TaskPayload, db: Session = Depends(get_db)):
    unknown = [d for d in payload.dimensions if d not in CONFLICT_DIMENSIONS]
    if unknown:
        raise BizException(f"未知检测维度：{unknown}")
    task = conflict_service.create_task(db, payload.name, payload.document_ids,
                                        payload.dimensions, payload.operator, region=payload.region)
    return ok({"id": task.id, "status": task.status}, "任务已提交，请稍后查询结果")


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db), page: int = Query(1, ge=1),
               page_size: int = Query(10, ge=1, le=100)):
    data = conflict_service.list_tasks(db, page, page_size)
    return paged(data["items"], data["total"], page, page_size)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    data = conflict_service.get_task(db, task_id)
    if not data:
        raise BizException("任务不存在", status_code=404)
    return ok(data)


@router.post("/tasks/{task_id}/export")
def export_task(task_id: str, db: Session = Depends(get_db)):
    try:
        path = conflict_service.export_report(db, task_id)
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)
    return ok({"path": path, "filename": path.split("\\")[-1].split("/")[-1]}, "报告已生成")


@router.get("/tasks/{task_id}/download")
def download_task(task_id: str, db: Session = Depends(get_db)):
    try:
        path = conflict_service.export_report(db, task_id)
    except ValueError as exc:
        raise BizException(str(exc), status_code=404)
    return FileResponse(path, filename=f"conflict-{task_id}.md", media_type="text/markdown")


@router.get("/dimensions")
def dimensions():
    return ok([{"code": k, "name": v} for k, v in CONFLICT_DIMENSIONS.items()])
