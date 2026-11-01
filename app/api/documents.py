"""文档与知识块接口（ING-001～008 / RET-006）。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.constants import DOC_STATUS, region_matches
from app.db.database import get_db
from app.db.models import Document, DocumentVersion, PolicyBlock, ReviewItem
from app.core.response import BizException, ok, paged
from app.services import audit_service, ingest_service, storage
from app.services.indexer import get_index
from app.services.serializer import block_to_dict, document_to_dict

router = APIRouter(prefix="/documents", tags=["文档"])


class TextImportPayload(BaseModel):
    title: str
    text: str
    source_url: str = ""
    effect_level: Optional[str] = None
    topics: Optional[list] = None
    jurisdiction: Optional[list] = None
    applicable_subjects: Optional[list] = None
    validity_status: Optional[str] = None


class ReviewPayload(BaseModel):
    status: str = "APPROVED"
    effect_level: Optional[str] = None
    topics: Optional[list] = None
    validity_status: Optional[str] = None
    operator: str = "reviewer"


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    keyword: str = Query("", description="标题/文号关键词"),
    effect_level: str = Query(""),
    doc_category: str = Query("", description="文件大类：POLICY 政策文件 / REGULATION 法规"),
    validity_status: str = Query(""),
    source_type: str = Query(""),
    topic: str = Query(""),
    region: str = Query("", description="地区切换：选中某市时仅返回本市+本省上位法+全国文件"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query("created_at"),
):
    query = db.query(Document)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Document.title.like(like), Document.document_number.like(like)))
    if effect_level:
        query = query.filter(Document.effect_level == effect_level)
    if doc_category:
        query = query.filter(Document.doc_category == doc_category)
    if validity_status:
        query = query.filter(Document.validity_status == validity_status)
    if source_type:
        query = query.filter(Document.source_type == source_type)
    if topic:
        query = query.filter(Document.topics.like(f"%{topic}%"))
    rows = query.all()
    # 地区过滤（本市 → 本省仅省 → 全国 的梯度，排除同省其它市）
    if region:
        rows = [d for d in rows if region_matches(list(d.jurisdiction or []), region)]
    total = len(rows)
    order = Document.created_at.desc() if sort_by == "created_at" else Document.publish_date.desc()
    rows.sort(key=lambda d: getattr(d, "created_at") if sort_by == "created_at" else (d.publish_date or ""),
              reverse=True)
    items = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return paged([document_to_dict(d) for d in items], total, page, page_size)


@router.post("/upload")
async def upload_document(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    effect_level: str = Form(""),
    topics: str = Form(""),
    jurisdiction: str = Form(""),
    operator: str = Form("system"),
):
    raw = await file.read()
    if not raw:
        raise BizException("上传文件内容为空")
    info = storage.save_upload(file.filename or "upload.txt", raw)
    meta_override = {}
    if effect_level:
        meta_override["effect_level"] = effect_level
    if topics:
        meta_override["topics"] = [t.strip() for t in topics.split(",") if t.strip()]
    if jurisdiction:
        meta_override["jurisdiction"] = [t.strip() for t in jurisdiction.split(",") if t.strip()]
    try:
        document = ingest_service.ingest_file(
            db, Path(info["file_path"]), info["file_name"], operator=operator, meta_override=meta_override
        )
    except ValueError as exc:
        raise BizException(str(exc))
    except Exception as exc:
        raise BizException(f"解析失败：{exc}")
    return ok(document_to_dict(document), "导入成功")


@router.post("/text")
def import_text(payload: TextImportPayload, db: Session = Depends(get_db), operator: str = Query("system")):
    if not payload.text.strip():
        raise BizException("正文不能为空")
    meta_override = {
        k: v for k, v in payload.dict().items()
        if k in ("effect_level", "topics", "jurisdiction", "applicable_subjects", "validity_status") and v
    }
    try:
        document = ingest_service.ingest_document(
            db,
            title=payload.title,
            text=payload.text,
            source_url=payload.source_url,
            meta_override=meta_override,
            operator=operator,
        )
    except ValueError as exc:
        raise BizException(str(exc))
    return ok(document_to_dict(document), "导入成功")


@router.post("/import-samples")
def import_samples(db: Session = Depends(get_db), operator: str = Query("system")):
    titles = ingest_service.import_samples(db, operator=operator)
    if not titles:
        raise BizException("samples 目录下没有可导入的示例文件")
    return ok({"imported": titles}, f"已导入 {len(titles)} 份示例政策")


@router.get("/{document_id}")
def document_detail(document_id: str, db: Session = Depends(get_db),
                    block_page: int = Query(1, ge=1), block_page_size: int = Query(20, ge=1, le=100)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise BizException("文件不存在", status_code=404)
    document.view_count = (document.view_count or 0) + 1
    db.commit()
    total = db.query(func.count(PolicyBlock.block_id)).filter(PolicyBlock.document_id == document_id).scalar()
    blocks = (
        db.query(PolicyBlock)
        .filter(PolicyBlock.document_id == document_id)
        .order_by(PolicyBlock.created_at)
        .offset((block_page - 1) * block_page_size)
        .limit(block_page_size)
        .all()
    )
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_no)
        .all()
    )
    return ok(
        {
            "document": document_to_dict(document, total),
            "versions": [
                {
                    "id": v.id,
                    "version_no": v.version_no,
                    "version_label": v.version_label,
                    "is_current": v.is_current,
                    "change_note": v.change_note,
                    "created_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S") if v.created_at else "",
                }
                for v in versions
            ],
            "blocks": {
                "items": [block_to_dict(b, document.title) for b in blocks],
                "total": total,
                "page": block_page,
                "page_size": block_page_size,
            },
        }
    )


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db), operator: str = Query("system")):
    if not ingest_service.delete_document(db, document_id, operator=operator):
        raise BizException("文件不存在", status_code=404)
    return ok(message="已删除")


@router.post("/{document_id}/reindex")
def reindex(document_id: str, db: Session = Depends(get_db)):
    blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).all()
    if not blocks:
        raise BizException("该文件没有知识块")
    document = db.query(Document).filter(Document.id == document_id).first()
    index = get_index()
    index.remove_document(document_id)
    from app.services.indexer import block_to_indexed

    indexed = []
    for block in blocks:
        item = block_to_indexed(block)
        item.document_title = document.title if document else ""
        indexed.append(item)
    index.add(indexed)
    audit_service.log_operation(db, "INDEX", "DOCUMENT", document_id, "system", {"blocks": len(blocks)})
    return ok({"blocks": len(blocks)}, "重建索引完成")


@router.post("/{document_id}/review")
def review_document(document_id: str, payload: ReviewPayload, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise BizException("文件不存在", status_code=404)
    if payload.effect_level:
        document.effect_level = payload.effect_level
    if payload.topics:
        document.topics = payload.topics
    if payload.validity_status:
        document.validity_status = payload.validity_status
    db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).update(
        {
            PolicyBlock.effect_level: document.effect_level,
            PolicyBlock.topics: document.topics,
            PolicyBlock.validity_status: document.validity_status,
        },
        synchronize_session=False,
    )
    item = (
        db.query(ReviewItem)
        .filter(ReviewItem.target_type == "DOCUMENT", ReviewItem.target_id == document_id)
        .order_by(ReviewItem.created_at.desc())
        .first()
    )
    if item:
        item.status = payload.status
        item.operator = payload.operator
    db.commit()
    audit_service.log_operation(db, "REVIEW", "DOCUMENT", document_id, payload.operator,
                                {"status": payload.status})
    return ok(document_to_dict(document), "复核完成")


@router.get("/{document_id}/blocks")
def document_blocks(document_id: str, db: Session = Depends(get_db), page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=200)):
    total = db.query(func.count(PolicyBlock.block_id)).filter(PolicyBlock.document_id == document_id).scalar()
    blocks = (
        db.query(PolicyBlock)
        .filter(PolicyBlock.document_id == document_id)
        .order_by(PolicyBlock.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paged([block_to_dict(b) for b in blocks], total, page, page_size)
