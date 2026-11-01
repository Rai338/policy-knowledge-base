"""数据模型（对应项目书第 10 章数据模型）。

实体：政策文件 / 文件版本 / 源文件 / 政策知识块 / 字典项 /
      采集信源 / 采集台账 / 检索日志 / 问答日志 / 冲突任务 / 冲突发现 /
      操作日志 / 人工复核队列
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, JSON, Index
from app.db.database import Base

IDENT_PREFIX = "pkb"


def _now():
    return dt.datetime.now()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Document(Base):
    """政策文件（ING-001/002/003）。"""

    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: _uid("doc"))
    title = Column(String(500), nullable=False, index=True)
    document_number = Column(String(200), default="", index=True)
    issuing_authority = Column(JSON, default=list)      # 发文机关（多值）
    effect_level = Column(String(32), default="OTHER", index=True)
    doc_category = Column(String(32), default="POLICY", index=True)  # POLICY 政策文件 | REGULATION 法规
    institution_level = Column(String(32), default="OTHER")
    jurisdiction = Column(JSON, default=list)           # 适用地域
    topics = Column(JSON, default=list)                 # 主题标签
    applicable_subjects = Column(JSON, default=list)    # 适用主体
    publish_date = Column(String(32), default="")
    effective_date = Column(String(32), default="")
    expiry_date = Column(String(32), default="")
    validity_status = Column(String(32), default="EFFECTIVE", index=True)
    level_reason = Column(Text, default="")             # 位阶判定依据（人工复核用）
    validity_reason = Column(Text, default="")          # 时效判定依据（人工复核用）
    summary = Column(Text, default="")
    source_type = Column(String(32), default="UPLOAD")  # UPLOAD | CRAWL
    source_url = Column(String(1000), default="")
    source_id = Column(String(64), default="")
    status = Column(String(32), default="PENDING", index=True)  # DOC_STATUS
    error_message = Column(Text, default="")
    block_count = Column(Integer, default=0)
    current_version_id = Column(String(64), default="")
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now, index=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class DocumentVersion(Base):
    """文件版本（ING-004 版本管理、ANA-006 修订对照）。"""

    __tablename__ = "document_versions"

    id = Column(String(64), primary_key=True, default=lambda: _uid("ver"))
    document_id = Column(String(64), nullable=False, index=True)
    version_no = Column(Integer, default=1)
    version_label = Column(String(100), default="第1版")
    is_current = Column(Boolean, default=True)
    change_note = Column(Text, default="")
    revised_from = Column(String(64), default="")       # 上一版本 id
    content_hash = Column(String(128), default="")
    created_at = Column(DateTime, default=_now)


class SourceFile(Base):
    """源文件（原始文件留痕，支撑来源可追溯）。"""

    __tablename__ = "source_files"

    id = Column(String(64), primary_key=True, default=lambda: _uid("file"))
    document_id = Column(String(64), nullable=False, index=True)
    version_id = Column(String(64), default="")
    file_name = Column(String(300), default="")
    file_path = Column(String(1000), default="")
    file_size = Column(Integer, default=0)
    mime_type = Column(String(120), default="")
    page_count = Column(Integer, default=0)
    content_hash = Column(String(128), default="", index=True)
    uploaded_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=_now)


class PolicyBlock(Base):
    """政策知识块（10.2 字段全集）。"""

    __tablename__ = "policy_blocks"

    block_id = Column(String(64), primary_key=True, default=lambda: _uid("blk"))
    document_id = Column(String(64), nullable=False, index=True)
    version_id = Column(String(64), default="", index=True)
    source_file_id = Column(String(64), default="")

    title = Column(String(500), default="")
    issuing_authority = Column(JSON, default=list)
    document_number = Column(String(200), default="")
    effect_level = Column(String(32), default="OTHER", index=True)
    doc_category = Column(String(32), default="POLICY", index=True)  # POLICY 政策文件 | REGULATION 法规
    topics = Column(JSON, default=list)
    jurisdiction = Column(JSON, default=list)
    applicable_subjects = Column(JSON, default=list)
    validity_status = Column(String(32), default="EFFECTIVE", index=True)
    publish_date = Column(String(32), default="")
    effective_date = Column(String(32), default="")
    expiry_date = Column(String(32), default="")

    structure_path = Column(JSON, default=list)   # 章/节/条/款路径
    article_number = Column(String(64), default="")  # 条号
    clause_number = Column(String(64), default="")   # 款号
    granularity = Column(String(16), default="ARTICLE")  # ARTICLE | CLAUSE
    parent_block_id = Column(String(64), default="")
    hierarchy_rank = Column(Integer, default=0)
    higher_law_refs = Column(JSON, default=list)
    related_blocks = Column(JSON, default=list)
    revised_from = Column(String(64), default="")
    institution_level = Column(String(32), default="OTHER")

    source_url = Column(String(1000), default="")
    original_text = Column(Text, default="")
    context_before = Column(Text, default="")
    context_after = Column(Text, default="")
    page_start = Column(Integer, default=0)
    page_end = Column(Integer, default=0)
    source_anchor = Column(String(300), default="")

    review_status = Column(String(32), default="AUTO")
    parser_version = Column(String(32), default="0.1.0")
    content_hash = Column(String(128), default="", index=True)
    created_at = Column(DateTime, default=_now)


class DictItem(Base):
    """字典项（ADM-001 字典维护：主题/主体/地域/位阶等可扩展取值）。"""

    __tablename__ = "dict_items"

    id = Column(String(64), primary_key=True, default=lambda: _uid("dict"))
    category = Column(String(32), nullable=False, index=True)  # topic|subject|jurisdiction|level
    code = Column(String(100), default="")
    name = Column(String(200), nullable=False)
    enabled = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)


class CrawlSource(Base):
    """采集信源（CRAWL-001/002/003）。"""

    __tablename__ = "crawl_sources"

    id = Column(String(64), primary_key=True, default=lambda: _uid("src"))
    name = Column(String(300), nullable=False)
    url = Column(String(1000), nullable=False)
    source_type = Column(String(32), default="LIST")   # LIST | RSS
    frequency = Column(String(16), default="NORMAL")   # CORE | NORMAL | TAIL
    institution_level = Column(String(32), default="OTHER")
    default_topics = Column(JSON, default=list)
    list_selector = Column(String(500), default="a")       # 列表页链接选择器（CSS）
    title_keywords = Column(String(500), default="")       # 标题过滤关键词，逗号分隔
    enabled = Column(Boolean, default=True, index=True)
    last_run_at = Column(DateTime, default=None)
    last_status = Column(String(32), default="IDLE")
    last_error = Column(Text, default="")
    total_found = Column(Integer, default=0)
    total_new = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)


class CrawlRecord(Base):
    """采集台账（CRAWL-007/008：发现、去重、入库、失败留痕）。"""

    __tablename__ = "crawl_records"

    id = Column(String(64), primary_key=True, default=lambda: _uid("crl"))
    source_id = Column(String(64), nullable=False, index=True)
    title = Column(String(500), default="")
    # url 不加列级 index：utf8mb4 下 VARCHAR(1000) 索引需 4000 字节，超过 InnoDB 3072 上限；
    # 改为表级前缀索引（前 255 字符，1020 字节，可满足按 url 去重查询）。
    url = Column(String(1000), default="")
    content_hash = Column(String(128), default="")
    simhash = Column(String(64), default="")
    etag = Column(String(200), default="")
    last_modified = Column(String(100), default="")
    status = Column(String(32), default="NEW", index=True)  # NEW|UPDATED|UNCHANGED|FAILED
    message = Column(Text, default="")
    document_id = Column(String(64), default="")
    crawled_at = Column(DateTime, default=_now, index=True)

    __table_args__ = (
        Index("ix_crawl_records_url", "url", mysql_length=255),
    )


class SearchLog(Base):
    """检索日志（LOG-002）。"""

    __tablename__ = "search_logs"

    id = Column(String(64), primary_key=True, default=lambda: _uid("slg"))
    keyword = Column(String(500), default="")
    filters = Column(JSON, default=dict)
    result_count = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    clicked_block_id = Column(String(64), default="")
    created_at = Column(DateTime, default=_now, index=True)


class QALog(Base):
    """问答日志（LOG-003：问题、答案、引用、拒答、延迟、反馈）。"""

    __tablename__ = "qa_logs"

    id = Column(String(64), primary_key=True, default=lambda: _uid("qal"))
    session_id = Column(String(64), default="", index=True)
    question = Column(Text, default="")
    answer = Column(Text, default="")
    citations = Column(JSON, default=list)
    refused = Column(Boolean, default=False)
    refuse_reason = Column(Text, default="")
    evidence_score = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    llm_backend = Column(String(64), default="")
    feedback = Column(String(16), default="")   # UP | DOWN | ""
    feedback_note = Column(Text, default="")
    operator = Column(String(64), default="user")
    created_at = Column(DateTime, default=_now, index=True)


class ConflictTask(Base):
    """冲突检测任务（CON-001/002/003：异步执行 + 进度回传）。"""

    __tablename__ = "conflict_tasks"

    id = Column(String(64), primary_key=True, default=lambda: _uid("cft"))
    name = Column(String(300), default="冲突检测任务")
    document_ids = Column(JSON, default=list)
    dimensions = Column(JSON, default=list)
    region = Column(String(64), default="", index=True)  # 地区切换：仅比对该地域范围内的文件（""=全库）
    status = Column(String(32), default="PENDING", index=True)
    progress = Column(Integer, default=0)
    total_pairs = Column(Integer, default=0)
    done_pairs = Column(Integer, default=0)
    finding_count = Column(Integer, default=0)
    error = Column(Text, default="")
    started_at = Column(DateTime, default=None)
    finished_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=_now, index=True)


class ConflictFinding(Base):
    """冲突发现（CON-004/005：分级 + 证据 + 建议）。"""

    __tablename__ = "conflict_findings"

    id = Column(String(64), primary_key=True, default=lambda: _uid("cfd"))
    task_id = Column(String(64), nullable=False, index=True)
    dimension = Column(String(32), default="MATTER")
    level = Column(String(32), default="POTENTIAL")   # SUSPECTED | POTENTIAL | NONE
    block_a_id = Column(String(64), default="")
    block_b_id = Column(String(64), default="")
    reason = Column(Text, default="")
    suggestion = Column(Text, default="")
    evidence = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)


class OperationLog(Base):
    """操作日志（LOG-001）。"""

    __tablename__ = "operation_logs"

    id = Column(String(64), primary_key=True, default=lambda: _uid("opl"))
    action = Column(String(32), default="", index=True)
    target_type = Column(String(64), default="")
    target_id = Column(String(64), default="")
    operator = Column(String(64), default="system")
    detail = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now, index=True)


class ReviewItem(Base):
    """人工复核队列（ING-006/CRAWL-009：自动结果的确认入口）。"""

    __tablename__ = "review_items"

    id = Column(String(64), primary_key=True, default=lambda: _uid("rvw"))
    target_type = Column(String(32), default="DOCUMENT")  # DOCUMENT | BLOCK | CRAWL
    target_id = Column(String(64), default="", index=True)
    reason = Column(Text, default="")
    status = Column(String(32), default="PENDING", index=True)  # PENDING|APPROVED|REJECTED
    operator = Column(String(64), default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class User(Base):
    """系统用户（预置账号 + 角色权限）。

    role: USER 普通用户（简洁检索/问答/解读） | ADMIN 管理员（含后台增删改查）
    password_hash: pbkdf2_hmac 加盐哈希，格式为 "salt$hash"（标准库实现，无额外依赖）
    """

    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: _uid("usr"))
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(200), nullable=False)
    display_name = Column(String(100), default="")
    role = Column(String(16), default="USER", index=True)      # USER | ADMIN
    status = Column(String(16), default="ACTIVE", index=True)  # ACTIVE | DISABLED
    last_login_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=_now, index=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
