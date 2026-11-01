"""管理接口（ADM-001/002）：字典维护、人工复核队列、索引维护。"""
from __future__ import annotations

import datetime as dt
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.constants import (
    APPLICABLE_SUBJECTS,
    EFFECT_LEVELS,
    EFFECT_LEVEL_RANK,
    INSTITUTION_LEVELS,
    PROVINCES,
    TOPICS,
    category_of_level,
)
from app.core.response import BizException, ok, paged
from app.db.database import get_db
from app.db.models import CrawlRecord, DictItem, Document, PolicyBlock, ReviewItem
from app.services import audit_service, ingest_service
from app.services.indexer import block_to_indexed, get_index, load_index_from_db
from app.services.serializer import block_to_dict, document_to_dict

router = APIRouter(prefix="/admin", tags=["管理"])

BUILTIN = {
    "topic": TOPICS,
    "subject": APPLICABLE_SUBJECTS,
    "jurisdiction": PROVINCES,
    "level": [item["code"] for item in EFFECT_LEVELS],
    "institution_level": list(INSTITUTION_LEVELS.keys()),
}


class DictPayload(BaseModel):
    category: str
    name: str
    code: str = ""
    enabled: bool = True
    sort_order: int = 0


class ReviewPayload(BaseModel):
    status: str = "APPROVED"
    operator: str = "reviewer"
    # 复核闭环：可就地修正目标对象的标签（地区 / 主题 / 适用主体），随"一键通过"一并保存
    jurisdiction: Optional[list] = None
    topics: Optional[list] = None
    applicable_subjects: Optional[list] = None


@router.get("/dict")
def list_dict(db: Session = Depends(get_db), category: str = Query(""),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    query = db.query(DictItem)
    if category:
        query = query.filter(DictItem.category == category)
    total = query.count()
    items = query.order_by(DictItem.category, DictItem.sort_order).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return paged(
        [
            {
                "id": i.id,
                "category": i.category,
                "code": i.code,
                "name": i.name,
                "enabled": i.enabled,
                "is_builtin": i.is_builtin,
                "sort_order": i.sort_order,
            }
            for i in items
        ],
        total,
        page,
        page_size,
    )


@router.post("/dict")
def create_dict(payload: DictPayload, db: Session = Depends(get_db), operator: str = Query("admin")):
    if not payload.category or not payload.name:
        raise BizException("分类与名称不能为空")
    item = DictItem(
        category=payload.category,
        code=payload.code or payload.name,
        name=payload.name,
        enabled=payload.enabled,
        is_builtin=False,
        sort_order=payload.sort_order,
    )
    db.add(item)
    db.commit()
    audit_service.log_operation(db, "DICT", "DictItem", item.id, operator, {"action": "create"})
    return ok({"id": item.id}, "字典项已新增")


@router.put("/dict/{item_id}")
def update_dict(item_id: str, payload: DictPayload, db: Session = Depends(get_db),
                operator: str = Query("admin")):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise BizException("字典项不存在", status_code=404)
    item.category = payload.category or item.category
    item.name = payload.name or item.name
    item.code = payload.code or item.code
    item.enabled = payload.enabled
    item.sort_order = payload.sort_order
    db.commit()
    audit_service.log_operation(db, "DICT", "DictItem", item_id, operator, {"action": "update"})
    return ok(message="已更新")


@router.delete("/dict/{item_id}")
def delete_dict(item_id: str, db: Session = Depends(get_db), operator: str = Query("admin")):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise BizException("字典项不存在", status_code=404)
    db.delete(item)
    db.commit()
    audit_service.log_operation(db, "DICT", "DictItem", item_id, operator, {"action": "delete"})
    return ok(message="已删除")


@router.get("/dict/options")
def dict_options(db: Session = Depends(get_db)):
    """内置字典 + 自定义字典合并后的筛选项。"""
    custom = db.query(DictItem).filter(DictItem.enabled.is_(True)).all()
    result = {key: list(values) for key, values in BUILTIN.items()}
    for item in custom:
        result.setdefault(item.category, [])
        if item.name not in result[item.category]:
            result[item.category].append(item.name)
    result["level_names"] = {x["code"]: x["name"] for x in EFFECT_LEVELS}
    result["institution_level_names"] = INSTITUTION_LEVELS
    return ok(result)


@router.get("/review")
def review_queue(db: Session = Depends(get_db), status: str = Query(""),
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    query = db.query(ReviewItem)
    if status:
        query = query.filter(ReviewItem.status == status)
    total = query.count()
    items = query.order_by(ReviewItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    doc_titles = {}
    doc_ids = [i.target_id for i in items if i.target_type == "DOCUMENT"]
    if doc_ids:
        doc_titles = {d.id: d.title for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()}
    return paged(
        [
            {
                "id": i.id,
                "target_type": i.target_type,
                "target_id": i.target_id,
                "target_title": doc_titles.get(i.target_id, ""),
                "reason": i.reason,
                "status": i.status,
                "operator": i.operator,
                "created_at": i.created_at.strftime("%Y-%m-%d %H:%M:%S") if i.created_at else "",
            }
            for i in items
        ],
        total,
        page,
        page_size,
    )


def _reindex_blocks(db: Session, document_id: str, document_title: str) -> int:
    """重建某文件的知识块索引（标签修正后立即生效）。"""
    blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).all()
    index = get_index()
    index.remove_document(document_id)
    if blocks:
        indexed = []
        for block in blocks:
            entry = block_to_indexed(block)
            entry.document_title = document_title
            indexed.append(entry)
        index.add(indexed)
    return len(blocks)


def _apply_review_patch(db: Session, item: ReviewItem, payload: ReviewPayload) -> bool:
    """把复核时的标签修正就地写入目标对象（知识块 / 文件），并同步索引。

    返回是否发生了实际修正。
    """
    patch = {
        "jurisdiction": payload.jurisdiction,
        "topics": payload.topics,
        "applicable_subjects": payload.applicable_subjects,
    }
    if all(value is None for value in patch.values()):
        return False

    if item.target_type == "BLOCK":
        block = db.query(PolicyBlock).filter(PolicyBlock.block_id == item.target_id).first()
        if not block:
            return False
        for field, value in patch.items():
            if value is not None:
                setattr(block, field, list(value))
        db.commit()
        doc = db.query(Document).filter(Document.id == block.document_id).first()
        _reindex_blocks(db, block.document_id, doc.title if doc else "")
        return True

    # 默认按文件处理：修正文件标签并同步到其全部知识块
    document = db.query(Document).filter(Document.id == item.target_id).first()
    if not document:
        return False
    for field, value in patch.items():
        if value is not None:
            setattr(document, field, list(value))
    blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == item.target_id).all()
    for block in blocks:
        for field, value in patch.items():
            if value is not None:
                setattr(block, field, list(value))
    db.commit()
    _reindex_blocks(db, document.id, document.title)
    return True


@router.get("/review/{item_id}")
def review_detail(item_id: str, db: Session = Depends(get_db)):
    """复核详情（原文对照 + 可就地修正的目标对象）。

    - target_type=BLOCK：返回该知识块原文与该文件信息；
    - target_type=DOCUMENT：返回文件信息与其全部知识块（逐条原文）。
    """
    item = db.query(ReviewItem).filter(ReviewItem.id == item_id).first()
    if not item:
        raise BizException("复核项不存在", status_code=404)

    document = None
    blocks: list = []
    if item.target_type == "BLOCK":
        block = db.query(PolicyBlock).filter(PolicyBlock.block_id == item.target_id).first()
        if block:
            document = db.query(Document).filter(Document.id == block.document_id).first()
            blocks = [block]
    else:
        document = db.query(Document).filter(Document.id == item.target_id).first()
        if document:
            blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == item.target_id).all()

    doc_title = document.title if document else ""
    return ok(
        {
            "id": item.id,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "target_title": doc_title,
            "reason": item.reason,
            "status": item.status,
            "operator": item.operator,
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
            "document": document_to_dict(document) if document else None,
            "blocks": [block_to_dict(b, doc_title) for b in blocks],
        }
    )


@router.post("/review/{item_id}")
def handle_review(item_id: str, payload: ReviewPayload, db: Session = Depends(get_db)):
    item = db.query(ReviewItem).filter(ReviewItem.id == item_id).first()
    if not item:
        raise BizException("复核项不存在", status_code=404)
    patched = _apply_review_patch(db, item, payload)
    item.status = payload.status
    item.operator = payload.operator
    db.commit()
    audit_service.log_operation(db, "REVIEW", item.target_type, item.target_id, payload.operator,
                                {"status": payload.status, "patched": patched})
    return ok(message="已通过并保存修正" if patched else "已处理")


@router.get("/todo")
def todo(db: Session = Depends(get_db)):
    """管理员待办概览：待复核 / 采集失败 / 解析失败，供首页计数直达。"""
    pending_review = db.query(ReviewItem).filter(ReviewItem.status == "PENDING").count()
    crawl_failed = db.query(CrawlRecord).filter(CrawlRecord.status == "FAILED").count()
    parse_failed = db.query(Document).filter(Document.status == "FAILED").count()
    return ok(
        {
            "pending_review": pending_review,
            "crawl_failed": crawl_failed,
            "parse_failed": parse_failed,
        }
    )


@router.post("/reindex")
def reindex_all(db: Session = Depends(get_db), operator: str = Query("admin")):
    stats = load_index_from_db(db)
    audit_service.log_operation(db, "INDEX", "ALL", "", operator, stats)
    return ok(stats, "全量索引重建完成")


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """数据概览（DATA-*）：文件、知识块、来源构成、时效构成。"""
    from sqlalchemy import func

    documents = db.query(Document).count()
    blocks = db.query(func.count(PolicyBlock.block_id)).scalar()
    by_level = dict(db.query(Document.effect_level, func.count(Document.id)).group_by(Document.effect_level).all())
    by_validity = dict(
        db.query(Document.validity_status, func.count(Document.id)).group_by(Document.validity_status).all()
    )
    by_source = dict(db.query(Document.source_type, func.count(Document.id)).group_by(Document.source_type).all())
    return ok(
        {
            "documents": documents,
            "blocks": blocks,
            "by_level": by_level,
            "by_validity": by_validity,
            "by_source": by_source,
            "index": get_index().stats(),
        }
    )


# ---------------------------------------------------------------- 政策法规后台管理（增删改查）
class DocumentPayload(BaseModel):
    """新增/编辑政策法规。

    新增：title 与 text 必填，提交正文后自动解析切块入库。
    编辑：text 留空表示仅修改元信息，不重新切块。
    """

    title: str = ""
    text: str = ""
    doc_category: str = ""          # POLICY 政策文件 | REGULATION 法规
    effect_level: str = ""
    document_number: str = ""
    issuing_authority: Optional[list] = None
    jurisdiction: Optional[list] = None
    topics: Optional[list] = None
    applicable_subjects: Optional[list] = None
    validity_status: str = ""
    publish_date: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    source_url: str = ""


def _meta_override(payload: DocumentPayload) -> Dict:
    """抽取允许覆盖自动抽取结果的字段。

    title 必须显式覆盖：extract_meta 默认取正文首行作为标题，
    管理端新增时应以用户填写的标题为准，否则标题会变成"第一条 ……"。
    """
    data: Dict = {}
    if payload.title.strip():
        data["title"] = payload.title.strip()
    for key in ("doc_category", "effect_level", "validity_status",
                "topics", "jurisdiction", "applicable_subjects"):
        value = getattr(payload, key, None)
        if value:
            data[key] = value
    return data


@router.get("/documents")
def admin_list_documents(
    db: Session = Depends(get_db),
    keyword: str = Query(""),
    doc_category: str = Query(""),
    effect_level: str = Query(""),
    validity_status: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user=Depends(require_admin),
):
    """后台政策法规列表（支持按文件大类 / 入库状态筛选）。"""
    query = db.query(Document)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Document.title.like(like), Document.document_number.like(like)))
    if doc_category:
        query = query.filter(Document.doc_category == doc_category)
    if effect_level:
        query = query.filter(Document.effect_level == effect_level)
    if validity_status:
        query = query.filter(Document.validity_status == validity_status)
    if status:
        query = query.filter(Document.status == status)
    total = query.count()
    items = (
        query.order_by(Document.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paged([document_to_dict(d) for d in items], total, page, page_size)


@router.post("/documents")
def admin_create_document(payload: DocumentPayload, db: Session = Depends(get_db),
                          user=Depends(require_admin)):
    """新增政策/法规：提交正文，自动解析切块并入库。"""
    if not payload.title.strip():
        raise BizException("标题不能为空")
    if not payload.text.strip():
        raise BizException("正文不能为空")
    try:
        document = ingest_service.ingest_document(
            db,
            title=payload.title.strip(),
            text=payload.text,
            source_url=payload.source_url,
            meta_override=_meta_override(payload),
            operator=user.username,
        )
    except ValueError as exc:
        raise BizException(str(exc))
    except Exception as exc:
        raise BizException(f"解析失败：{exc}")
    audit_service.log_operation(db, "CREATE", "DOCUMENT", document.id, user.username,
                                {"title": document.title})
    return ok(document_to_dict(document), "新增成功")


@router.put("/documents/{document_id}")
def admin_update_document(document_id: str, payload: DocumentPayload,
                          db: Session = Depends(get_db), user=Depends(require_admin)):
    """编辑政策法规元信息（正文留空则不重新切块）。"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise BizException("文件不存在", status_code=404)

    if payload.title.strip():
        document.title = payload.title.strip()
    for field in ("document_number", "publish_date", "effective_date", "expiry_date", "source_url"):
        value = (getattr(payload, field) or "").strip()
        if value:
            setattr(document, field, value)
    for field in ("issuing_authority", "jurisdiction", "topics", "applicable_subjects"):
        value = getattr(payload, field)
        if value:
            setattr(document, field, value)
    if payload.effect_level:
        document.effect_level = payload.effect_level
    if payload.validity_status:
        document.validity_status = payload.validity_status
    # 文件大类：显式指定优先，否则随效力位阶自动联动
    document.doc_category = payload.doc_category or category_of_level(document.effect_level)
    document.updated_at = dt.datetime.now()

    if payload.text and payload.text.strip():
        # 重新切块：保留文件身份与版本历史，仅替换正文与知识块
        try:
            ingest_service.replace_document_text(
                db, document_id, payload.text, operator=user.username, change_note="正文修订"
            )
        except ValueError as exc:
            raise BizException(str(exc))
        document = db.query(Document).filter(Document.id == document_id).first()
        return ok(document_to_dict(document, document.block_count), "保存成功（正文已重新切块）")

    # 仅更新元信息：同步冗余字段到知识块，保证检索/筛选结果与文件一致
    blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).all()
    for block in blocks:
        block.doc_category = document.doc_category
        block.effect_level = document.effect_level
        block.validity_status = document.validity_status
        block.document_number = document.document_number
        block.publish_date = document.publish_date
        block.effective_date = document.effective_date
        block.expiry_date = document.expiry_date
        if document.issuing_authority:
            block.issuing_authority = list(document.issuing_authority)
        if document.jurisdiction:
            block.jurisdiction = list(document.jurisdiction)
        block.hierarchy_rank = EFFECT_LEVEL_RANK.get(document.effect_level, 10)
    db.commit()

    # 重建该文件索引，使筛选与检索立即生效
    index = get_index()
    index.remove_document(document_id)
    if blocks:
        indexed = []
        for block in blocks:
            item = block_to_indexed(block)
            item.document_title = document.title
            indexed.append(item)
        index.add(indexed)
    audit_service.log_operation(db, "UPDATE", "DOCUMENT", document_id, user.username,
                                {"blocks": len(blocks)})
    return ok(document_to_dict(document, len(blocks)), "保存成功")


@router.delete("/documents/{document_id}")
def admin_delete_document(document_id: str, db: Session = Depends(get_db),
                          user=Depends(require_admin)):
    """删除政策法规（连带知识块与索引）。"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise BizException("文件不存在", status_code=404)
    title = document.title
    if not ingest_service.delete_document(db, document_id, operator=user.username):
        raise BizException("删除失败", status_code=500)
    audit_service.log_operation(db, "DELETE", "DOCUMENT", document_id, user.username,
                                {"title": title})
    return ok(message=f"已删除《{title}》")
