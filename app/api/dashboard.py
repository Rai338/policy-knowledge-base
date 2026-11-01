"""首页统计与元信息（UI-001、LOG-001～003 统计视图）。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import APP_NAME, APP_VERSION, BUILD_ID, THEME, theme_css_vars
from app.core.constants import DOC_CATEGORIES, EFFECT_LEVELS, INSTITUTION_LEVELS, REGION_OPTIONS, VALIDITY_STATUS
from app.core.response import ok
from app.db.database import get_db
from app.db.models import (
    ConflictFinding,
    ConflictTask,
    Document,
    OperationLog,
    PolicyBlock,
    QALog,
    ReviewItem,
    SearchLog,
)
from app.services import crawl_service
from app.services.indexer import get_index

router = APIRouter(prefix="/dashboard", tags=["首页"])
meta_router = APIRouter(prefix="/meta", tags=["元信息"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    today = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    documents = db.query(Document).count()
    blocks = db.query(func.count(PolicyBlock.block_id)).scalar()
    new_today = db.query(Document).filter(Document.created_at >= today).count()
    qa_total = db.query(QALog).count()
    qa_refused = db.query(QALog).filter(QALog.refused.is_(True)).count()
    search_total = db.query(SearchLog).count()
    pending_review = db.query(ReviewItem).filter(ReviewItem.status == "PENDING").count()
    conflict_tasks = db.query(ConflictTask).count()
    conflict_findings = db.query(ConflictFinding).count()
    avg_latency = db.query(func.avg(QALog.latency_ms)).scalar() or 0
    return ok(
        {
            "documents": documents,
            "blocks": blocks,
            "new_today": new_today,
            "qa_total": qa_total,
            "qa_refused": qa_refused,
            "search_total": search_total,
            "pending_review": pending_review,
            "conflict_tasks": conflict_tasks,
            "conflict_findings": conflict_findings,
            "qa_avg_latency_ms": int(avg_latency),
            "crawl": crawl_service.stats(db),
            "index": get_index().stats(),
        }
    )


@router.get("/trend")
def trend(db: Session = Depends(get_db), days: int = 7):
    """近 N 日入库与问答趋势。"""
    today = dt.date.today()
    items = []
    for offset in range(days - 1, -1, -1):
        day = today - dt.timedelta(days=offset)
        start = dt.datetime.combine(day, dt.time.min)
        end = start + dt.timedelta(days=1)
        documents = db.query(Document).filter(Document.created_at >= start, Document.created_at < end).count()
        qa = db.query(QALog).filter(QALog.created_at >= start, QALog.created_at < end).count()
        items.append({"date": day.isoformat(), "documents": documents, "qa": qa})
    return ok({"items": items})


@meta_router.get("/theme")
def theme():
    """主题常量（前端与后端共用同一份定义）。"""
    return ok({"vars": THEME, "css": theme_css_vars(),
               "app": {"name": APP_NAME, "version": APP_VERSION, "build": BUILD_ID}})


@meta_router.get("/options")
def options():
    return ok(
        {
            "effect_levels": EFFECT_LEVELS,
            # 文件大类（政策文件 / 法规），供前端归类筛选项使用
            "doc_categories": DOC_CATEGORIES,
            "validity_status": VALIDITY_STATUS,
            "institution_levels": INSTITUTION_LEVELS,
        }
    )


@meta_router.get("/regions")
def regions():
    """地区切换可选地域（A+C 方案）：全国（不过滤）/ 芜湖 / 合肥 / 马鞍山 / 蚌埠。"""
    return ok(REGION_OPTIONS)
