"""检索接口（RET-001～006）。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import MIN_RELEVANCE_SCORE, WEBSEARCH_ENABLED, WEBSEARCH_MAX_RESULTS
from app.core.response import BizException, ok, paged
from app.db.database import get_db
from app.db.models import Document, PolicyBlock
from app.services import audit_service
from app.services.indexer import get_index
from app.services.retriever import search_blocks
from app.services.serializer import block_to_dict
from app.services.websearch_service import search_web

router = APIRouter(prefix="/search", tags=["检索"])
blocks_router = APIRouter(prefix="/blocks", tags=["知识块"])


@router.get("")
def search(
    db: Session = Depends(get_db),
    q: str = Query("", description="检索关键词"),
    effect_levels: Optional[List[str]] = Query(None),
    doc_categories: Optional[List[str]] = Query(None, description="文件大类：POLICY 政策文件 / REGULATION 法规"),
    validity_statuses: Optional[List[str]] = Query(None),
    institution_levels: Optional[List[str]] = Query(None),
    topics: Optional[List[str]] = Query(None),
    jurisdictions: Optional[List[str]] = Query(None),
    region: str = Query("", description="地区切换：选中某市时按「本市→本省→全国」梯度召回"),
    subjects: Optional[List[str]] = Query(None),
    document_ids: Optional[List[str]] = Query(None),
    granularity: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    only_current: bool = Query(True, description="仅现行有效"),
    sort_by: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    if not q.strip():
        raise BizException("请输入检索关键词")
    filters = {
        "effect_levels": effect_levels or [],
        "doc_categories": doc_categories or [],
        "validity_statuses": validity_statuses or [],
        "institution_levels": institution_levels or [],
        "topics": topics or [],
        "jurisdictions": jurisdictions or [],
        "region": region or "",
        "subjects": subjects or [],
        "document_ids": document_ids or [],
        "granularity": granularity,
        "date_from": date_from,
        "date_to": date_to,
    }
    result = search_blocks(db, q, filters, page, page_size, sort_by, only_current)
    audit_service.log_search(db, q, filters, result["total"], result["latency_ms"])

    # 本地未命中或相关度过低时，自动启用联网兜底（RET-007）：
    # 未配置联网服务时返回官方渠道建议，不报错、不虚构结果
    web = None
    if WEBSEARCH_ENABLED and (result["total"] == 0 or result["max_score"] < MIN_RELEVANCE_SCORE):
        web = search_web(q, WEBSEARCH_MAX_RESULTS)

    return ok(
        {
            "items": result["items"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
            "latency_ms": result["latency_ms"],
            "max_score": result["max_score"],
            # 因“仅现行有效”被排除的命中数，前端据此提示用户放宽条件
            "excluded_by_validity": result.get("excluded_by_validity", 0),
            # 检索方式（语义向量后端等），用于界面说明 RAG 语义命中
            "retrieval": result.get("retrieval", {}),
            # 联网补充结果（仅本地未命中时存在；未配置服务时为渠道建议）
            "web": web,
        }
    )


@router.get("/web")
def web_search(
    q: str = Query("", description="联网检索关键词"),
    limit: int = Query(5, ge=1, le=20),
):
    """联网检索：本地知识库未命中时的补充渠道。

    配置 PKB_WEBSEARCH_PROVIDER + PKB_WEBSEARCH_API_KEY 后返回真实联网结果；
    未配置时返回官方渠道检索入口（降级不报错）。
    """
    if not q.strip():
        raise BizException("请输入检索关键词")
    return ok(search_web(q.strip(), limit))


@router.get("/suggest")
def suggest(q: str = Query(""), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    """检索建议：标题/条号联想（空库时返回空数组，前端展示空状态）。"""
    if not q.strip():
        return ok([])
    like = f"%{q.strip()}%"
    docs = db.query(Document).filter(Document.title.like(like)).limit(limit).all()
    return ok([{"type": "document", "id": d.id, "title": d.title} for d in docs])


@blocks_router.get("/{block_id}")
def block_detail(block_id: str, db: Session = Depends(get_db)):
    block = db.query(PolicyBlock).filter(PolicyBlock.block_id == block_id).first()
    if not block:
        raise BizException("知识块不存在", status_code=404)
    document = db.query(Document).filter(Document.id == block.document_id).first()
    parent = (
        db.query(PolicyBlock).filter(PolicyBlock.block_id == block.parent_block_id).first()
        if block.parent_block_id else None
    )
    children = db.query(PolicyBlock).filter(PolicyBlock.parent_block_id == block_id).all()
    similar_ids = [hit["block_id"] for hit in get_index().similar_blocks(block_id, 5)]
    similar_blocks = (
        db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(similar_ids)).all() if similar_ids else []
    )
    return ok(
        {
            "block": block_to_dict(block, document.title if document else ""),
            "document": {
                "id": document.id if document else "",
                "title": document.title if document else "",
                "document_number": document.document_number if document else "",
                "source_url": document.source_url if document else "",
            },
            "parent": block_to_dict(parent) if parent else None,
            "children": [block_to_dict(b) for b in children],
            "similar": [block_to_dict(b) for b in similar_blocks],
        }
    )


@blocks_router.get("/{block_id}/similar")
def block_similar(block_id: str, top_k: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    hits = get_index().similar_blocks(block_id, top_k)
    ids = [hit["block_id"] for hit in hits]
    blocks = db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all() if ids else []
    score_map = {hit["block_id"]: hit["score"] for hit in hits}
    items = [block_to_dict(b, score=score_map.get(b.block_id, 0.0)) for b in blocks]
    return ok({"items": sorted(items, key=lambda x: x["score"], reverse=True)})
