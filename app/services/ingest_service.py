"""导入编排（ING-001～008）：解析 → 元数据抽取 → 切块 → 去重 → 索引 → 复核队列。

上传导入与采集入库共用同一条流水线，保证处理口径一致。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import MAX_UPLOAD_MB, ALLOWED_EXTENSIONS, SAMPLE_DIR
from app.core.constants import DOC_STATUS, EFFECT_LEVEL_RANK, REVIEW_STATUS, category_of_level
from app.core.logging import logger
from app.db.models import (
    Document,
    DocumentVersion,
    PolicyBlock,
    ReviewItem,
    SourceFile,
)
from app.services import audit_service, storage
from app.services.chunker import chunk_text
from app.services.extractor import extract_meta
from app.services.indexer import block_to_indexed, get_index
from app.services.parsers import parse_file
from app.services.text_utils import content_hash, truncate


def _new_version(db: Session, document_id: str, note: str = "", content_hash_value: str = "") -> DocumentVersion:
    count = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).count()
    version = DocumentVersion(
        document_id=document_id,
        version_no=count + 1,
        version_label=f"第{count + 1}版",
        is_current=True,
        change_note=note,
        content_hash=content_hash_value,
    )
    db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).update(
        {DocumentVersion.is_current: False}
    )
    db.add(version)
    db.flush()
    return version


def _create_blocks(db: Session, document: Document, version: DocumentVersion,
                   source_file_id: str, raw_blocks) -> int:
    count = 0
    created: List[PolicyBlock] = []
    for idx, raw in enumerate(raw_blocks):
        block = PolicyBlock(
            document_id=document.id,
            version_id=version.id,
            source_file_id=source_file_id,
            title=raw.title or document.title,
            issuing_authority=list(document.issuing_authority or []),
            document_number=document.document_number,
            effect_level=document.effect_level,
            doc_category=document.doc_category or category_of_level(document.effect_level),
            topics=list(document.topics or []),
            jurisdiction=list(document.jurisdiction or []),
            applicable_subjects=list(document.applicable_subjects or []),
            validity_status=document.validity_status,
            publish_date=document.publish_date,
            effective_date=document.effective_date,
            expiry_date=document.expiry_date,
            structure_path=list(raw.structure_path or []),
            article_number=raw.article_number,
            clause_number=raw.clause_number,
            granularity=raw.granularity,
            hierarchy_rank=EFFECT_LEVEL_RANK.get(document.effect_level, 10),
            institution_level=document.institution_level,
            source_url=document.source_url,
            original_text=raw.text,
            context_before=raw_blocks[idx - 1].text[-200:] if idx > 0 else "",
            context_after=(raw_blocks[idx + 1].text[:200] if idx + 1 < len(raw_blocks) else ""),
            page_start=raw.page_start,
            page_end=raw.page_end,
            source_anchor=_anchor(raw),
            review_status=REVIEW_STATUS["AUTO"],
            content_hash=content_hash(raw.text),
        )
        db.add(block)
        created.append(block)
        count += 1
    db.flush()

    # 父子关系：款 → 条
    for idx, raw in enumerate(raw_blocks):
        if raw.parent_index is not None and raw.parent_index < len(created):
            created[idx].parent_block_id = created[raw.parent_index].block_id
    db.flush()
    return count


def _anchor(raw) -> str:
    parts = [p for p in (raw.article_number, raw.clause_number) if p]
    if raw.page_start:
        parts.append(f"P{raw.page_start}")
    return "-".join(parts)


def _maybe_review(db: Session, document: Document, meta: Dict) -> None:
    """元数据置信度不足时进入人工复核队列（ING-006）。"""
    reasons = []
    if meta.get("effect_level") == "OTHER":
        reasons.append("效力位阶未能自动判定")
    if not meta.get("publish_date"):
        reasons.append("未识别到发布日期")
    if not meta.get("issuing_authority"):
        reasons.append("未识别到发文机关")
    if reasons:
        db.add(
            ReviewItem(
                target_type="DOCUMENT",
                target_id=document.id,
                reason="；".join(reasons),
                status="PENDING",
            )
        )


def ingest_document(
    db: Session,
    title: str,
    text: str,
    *,
    source_type: str = "UPLOAD",
    source_url: str = "",
    source_id: str = "",
    file_info: Optional[Dict] = None,
    pages: Optional[List[str]] = None,
    meta_override: Optional[Dict] = None,
    operator: str = "system",
    version_note: str = "",
    requires_review: bool = False,
) -> Document:
    """统一的入库流水线（上传与采集共用）。"""
    file_info = file_info or {}
    meta_override = meta_override or {}
    meta = extract_meta(text, file_info.get("file_name", "") or title)
    meta.update({k: v for k, v in meta_override.items() if v not in (None, "", [])})

    doc_hash = content_hash(text)
    existing = (
        db.query(Document).filter(Document.title == meta["title"]).order_by(Document.created_at.desc()).first()
        if meta.get("title")
        else None
    )

    if existing:
        # 同名文件：按内容 hash 判断是重复还是修订（ING-004）
        last_file = (
            db.query(SourceFile)
            .filter(SourceFile.document_id == existing.id)
            .order_by(SourceFile.created_at.desc())
            .first()
        )
        if last_file and last_file.content_hash == doc_hash:
            raise ValueError(f"《{existing.title}》内容未发生变化，已跳过重复入库")
        document = existing
        document.status = DOC_STATUS["PARSING"]
        document.updated_at = dt.datetime.now()
        version = _new_version(db, document.id, version_note or "文件更新", doc_hash)
        version.revised_from = existing.current_version_id
        document.current_version_id = version.id
        document.source_type = source_type or document.source_type
        document.source_url = source_url or document.source_url
    else:
        document = Document(
            title=meta["title"] or title,
            document_number=meta.get("document_number", ""),
            issuing_authority=meta.get("issuing_authority", []),
            effect_level=meta.get("effect_level", "OTHER"),
            doc_category=meta.get("doc_category") or category_of_level(meta.get("effect_level", "OTHER")),
            institution_level=meta.get("institution_level", "OTHER"),
            jurisdiction=meta.get("jurisdiction", []),
            topics=meta.get("topics", []),
            applicable_subjects=meta.get("applicable_subjects", []),
            publish_date=meta.get("publish_date", ""),
            effective_date=meta.get("effective_date", ""),
            expiry_date=meta.get("expiry_date", ""),
            validity_status=meta.get("validity_status", "EFFECTIVE"),
            level_reason=meta.get("level_reason", ""),
            validity_reason=meta.get("validity_reason", ""),
            source_type=source_type,
            source_url=source_url,
            source_id=source_id,
            status=DOC_STATUS["PARSING"],
        )
        db.add(document)
        db.flush()
        version = _new_version(db, document.id, "首版入库", doc_hash)
        document.current_version_id = version.id

    # 元数据回填（支持修订）
    document.document_number = meta.get("document_number", document.document_number)
    document.issuing_authority = meta.get("issuing_authority", document.issuing_authority)
    document.effect_level = meta.get("effect_level", document.effect_level)
    # 文件大类（政策文件/法规）随位阶联动：人工可在管理端覆盖，未覆盖则按位阶自动判定
    document.doc_category = meta.get("doc_category") or category_of_level(document.effect_level)
    document.institution_level = meta.get("institution_level", document.institution_level)
    document.jurisdiction = meta.get("jurisdiction", document.jurisdiction)
    document.topics = meta.get("topics", document.topics)
    document.applicable_subjects = meta.get("applicable_subjects", document.applicable_subjects)
    document.publish_date = meta.get("publish_date", document.publish_date)
    document.effective_date = meta.get("effective_date", document.effective_date)
    document.expiry_date = meta.get("expiry_date", document.expiry_date)
    document.validity_status = meta.get("validity_status", document.validity_status)
    document.level_reason = meta.get("level_reason", document.level_reason)
    document.validity_reason = meta.get("validity_reason", document.validity_reason)
    # 摘要不在入库时写死（避免把文件头写入）；由解读接口按需生成（LLM 或规则抽取）并落库

    source_file = SourceFile(
        document_id=document.id,
        version_id=version.id,
        file_name=file_info.get("file_name", f"{document.title}.txt"),
        file_path=file_info.get("file_path", ""),
        file_size=file_info.get("file_size", len(text.encode("utf-8"))),
        mime_type=file_info.get("mime_type", "txt"),
        page_count=len(pages or []),
        content_hash=doc_hash,
        uploaded_by=operator,
    )
    db.add(source_file)
    db.flush()

    raw_blocks = chunk_text(text, pages or [])
    if not raw_blocks:
        document.status = DOC_STATUS["FAILED"]
        document.error_message = "未从文件中解析出任何知识块"
        db.commit()
        raise ValueError(document.error_message)

    get_index().remove_document(document.id)
    db.query(PolicyBlock).filter(PolicyBlock.document_id == document.id).delete()
    db.flush()

    block_count = _create_blocks(db, document, version, source_file.id, raw_blocks)
    document.block_count = block_count
    document.status = DOC_STATUS["REVIEWING"] if requires_review else DOC_STATUS["INDEXED"]

    # 上位法引用写入块级字段
    refs = meta.get("higher_law_refs", [])
    if refs:
        db.query(PolicyBlock).filter(PolicyBlock.document_id == document.id).update(
            {PolicyBlock.higher_law_refs: refs}, synchronize_session=False
        )

    if requires_review:
        db.add(
            ReviewItem(
                target_type="DOCUMENT",
                target_id=document.id,
                reason="用户导入，待管理员审核",
                status="PENDING",
            )
        )
    else:
        _maybe_review(db, document, meta)
    db.commit()

    # 索引写入：待审核的文档暂不进入检索/问答，审核通过后再入库
    if not requires_review:
        blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == document.id).all()
        indexed = []
        for block in blocks:
            item = block_to_indexed(block)
            item.document_title = document.title
            indexed.append(item)
        get_index().add(indexed)

    audit_service.log_operation(
        db, "UPLOAD" if source_type == "UPLOAD" else "CRAWL", "DOCUMENT", document.id,
        operator, {"title": document.title, "blocks": block_count, "source_type": source_type},
    )
    logger.info("入库完成：《%s》%s 个知识块", document.title, block_count)
    return document


def ingest_file(db: Session, path: Path, filename: str, operator: str = "system",
                meta_override: Optional[Dict] = None, source_type: str = "UPLOAD",
                source_url: str = "", requires_review: bool = False) -> Document:
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型：{suffix}，支持 {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    size_mb = path.stat().st_size / 1024 / 1024
    if size_mb > MAX_UPLOAD_MB:
        raise ValueError(f"文件超过 {MAX_UPLOAD_MB}MB 限制")

    parsed = parse_file(path)
    if parsed.is_empty:
        raise ValueError("文件内容为空或无法解析出文本")
    file_info = {
        "file_name": filename,
        "file_path": str(path),
        "file_size": path.stat().st_size,
        "mime_type": suffix.lstrip("."),
    }
    return ingest_document(
        db,
        title=Path(filename).stem,
        text=parsed.text,
        source_type=source_type,
        source_url=source_url,
        file_info=file_info,
        pages=parsed.pages,
        meta_override=meta_override,
        operator=operator,
        requires_review=requires_review,
    )


def delete_document(db: Session, document_id: str, operator: str = "system") -> bool:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        return False
    db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).delete()
    db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).delete()
    db.query(SourceFile).filter(SourceFile.document_id == document_id).delete()
    db.delete(document)
    db.commit()
    get_index().remove_document(document_id)
    audit_service.log_operation(db, "UPLOAD", "DOCUMENT", document_id, operator, {"action": "delete"})
    return True


def import_samples(db: Session, operator: str = "system", requires_review: bool = False) -> List[str]:
    """一键导入 samples 目录下的示例政策（便于空库演示）。"""
    imported: List[str] = []
    failed: List[str] = []
    skipped: List[str] = []
    if not SAMPLE_DIR.exists():
        logger.warning("samples 目录不存在，跳过示例导入：%s", SAMPLE_DIR)
        return imported
    for path in sorted(SAMPLE_DIR.glob("*")):
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            doc = ingest_file(db, path, path.name, operator=operator, requires_review=requires_review)
            imported.append(doc.title)
        except Exception as exc:  # pragma: no cover
            # 已入库且内容未变化属正常跳过，不应计为失败（否则每次重启都刷 ERROR）
            if "未发生变化" in str(exc):
                skipped.append(path.name)
                continue
            failed.append(path.name)
            logger.warning("示例文件 %s 导入失败：%s", path.name, exc)
    if skipped:
        logger.info("示例文件已入库且内容未变化，跳过 %d 个", len(skipped))
    if failed:
        logger.error(
            "示例导入存在失败文件（%d/%d）：%s",
            len(failed), len(imported) + len(failed) + len(skipped), ", ".join(failed),
        )
    return imported


def replace_document_text(db: Session, document_id: str, text: str, operator: str = "admin",
                         change_note: str = "正文修订") -> Optional[Document]:
    """在不改变文件 id 的前提下，用新正文重新切块、生成新版本并重建索引。

    用于管理端「编辑时修改正文」：保留文件身份、版本历史与索引连续性，
    避免只能删除重建而丢失版本记录与知识块关联。
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        return None
    doc_hash = content_hash(text)
    raw_blocks = chunk_text(text, [])
    if not raw_blocks:
        raise ValueError("未能从正文中解析出任何知识块")

    version = _new_version(db, document.id, change_note, doc_hash)
    version.revised_from = document.current_version_id
    document.current_version_id = version.id
    document.updated_at = dt.datetime.now()

    source_file = SourceFile(
        document_id=document.id,
        version_id=version.id,
        file_name=f"{document.title}.txt",
        file_path="",
        file_size=len(text.encode("utf-8")),
        mime_type="txt",
        page_count=0,
        content_hash=doc_hash,
        uploaded_by=operator,
    )
    db.add(source_file)
    db.flush()

    get_index().remove_document(document.id)
    db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).delete()
    db.flush()

    block_count = _create_blocks(db, document, version, source_file.id, raw_blocks)
    document.block_count = block_count
    document.status = DOC_STATUS["INDEXED"]
    db.commit()

    blocks = db.query(PolicyBlock).filter(PolicyBlock.document_id == document_id).all()
    indexed = []
    for block in blocks:
        item = block_to_indexed(block)
        item.document_title = document.title
        indexed.append(item)
    get_index().add(indexed)

    audit_service.log_operation(
        db, "UPDATE", "DOCUMENT", document_id, operator,
        {"blocks": block_count, "text_replaced": True},
    )
    return document
