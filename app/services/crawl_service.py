"""实时/准实时采集（CRAWL-001～012）：信源管理、分级轮询、增量识别、入库留痕。

采集实现要点：
- 分级轮询：核心源 5 分钟、一般源 30 分钟、长尾源每日（CRAWL-002）
- 事件源：RSS/Atom 订阅优先，无 RSS 时解析列表页链接（CRAWL-003）
- 增量识别：ETag / Last-Modified + 列表前 N 条 + content_hash + SimHash（CRAWL-004/005）
- 新发现或变更的正文走与上传一致的入库流水线（CRAWL-006）
- 全过程写入采集台账，失败留痕并更新信源状态（CRAWL-007/008/010）
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import (
    CRAWL_LIST_LIMIT,
    CRAWL_TIMEOUT,
    CRAWL_USER_AGENT,
    SIMHASH_DISTANCE_THRESHOLD,
)
from app.core.constants import CRAWL_FREQ, CRAWL_STATUS
from app.core.logging import logger
from app.db.models import CrawlRecord, CrawlSource, Document
from app.services import audit_service, ingest_service
from app.services.parsers import parse_html
from app.services.text_utils import content_hash, hamming_distance, simhash

HEADERS = {"User-Agent": CRAWL_USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}


# ------------------------------------------------------------------ 信源管理
def list_sources(db: Session, page: int = 1, page_size: int = 20, keyword: str = "") -> Dict:
    query = db.query(CrawlSource)
    if keyword:
        query = query.filter(CrawlSource.name.like(f"%{keyword}%"))
    total = query.count()
    items = query.order_by(CrawlSource.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "source_type": s.source_type,
                "frequency": s.frequency,
                "frequency_name": CRAWL_FREQ.get(s.frequency, {}).get("name", s.frequency),
                "frequency_minutes": CRAWL_FREQ.get(s.frequency, {}).get("minutes", 30),
                "institution_level": s.institution_level,
                "default_topics": s.default_topics,
                "list_selector": s.list_selector,
                "title_keywords": s.title_keywords,
                "enabled": s.enabled,
                "last_run_at": s.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if s.last_run_at else "",
                "last_status": s.last_status,
                "last_error": s.last_error,
                "total_found": s.total_found,
                "total_new": s.total_new,
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else "",
            }
            for s in items
        ],
    }


def create_source(db: Session, payload: Dict, operator: str = "user") -> CrawlSource:
    if not payload.get("name") or not payload.get("url"):
        raise ValueError("信源名称与地址不能为空")
    source = CrawlSource(
        name=payload["name"],
        url=payload["url"],
        source_type=payload.get("source_type", "LIST"),
        frequency=payload.get("frequency", "NORMAL"),
        institution_level=payload.get("institution_level", "OTHER"),
        default_topics=payload.get("default_topics", []),
        list_selector=payload.get("list_selector", "a"),
        title_keywords=payload.get("title_keywords", ""),
        enabled=bool(payload.get("enabled", True)),
    )
    db.add(source)
    db.commit()
    audit_service.log_operation(db, "SOURCE", "CrawlSource", source.id, operator, {"action": "create"})
    return source


def update_source(db: Session, source_id: str, payload: Dict, operator: str = "user") -> Optional[CrawlSource]:
    source = db.query(CrawlSource).filter(CrawlSource.id == source_id).first()
    if not source:
        return None
    for field in ("name", "url", "source_type", "frequency", "institution_level",
                  "default_topics", "list_selector", "title_keywords", "enabled"):
        if field in payload and payload[field] is not None:
            setattr(source, field, payload[field])
    db.commit()
    audit_service.log_operation(db, "SOURCE", "CrawlSource", source_id, operator, {"action": "update"})
    return source


def delete_source(db: Session, source_id: str, operator: str = "user") -> bool:
    source = db.query(CrawlSource).filter(CrawlSource.id == source_id).first()
    if not source:
        return False
    db.delete(source)
    db.commit()
    audit_service.log_operation(db, "SOURCE", "CrawlSource", source_id, operator, {"action": "delete"})
    return True


# ------------------------------------------------------------------ 抓取
def _fetch(url: str) -> httpx.Response:
    return httpx.get(url, headers=HEADERS, timeout=CRAWL_TIMEOUT, follow_redirects=True)


def _parse_rss(raw: str) -> List[Dict]:
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return items
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes[:CRAWL_LIST_LIMIT]:
        title = node.findtext("title") or node.findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = node.findtext("link") or ""
        if not link:
            link_node = node.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.get("href") if link_node is not None else ""
        if title and link:
            items.append({"title": title.strip(), "url": link.strip()})
    return items


def _parse_list(raw: str, base_url: str, selector: str, keywords: str) -> List[Dict]:
    items = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        nodes = soup.select(selector or "a")
    except Exception:  # pragma: no cover
        nodes = []
        for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{4,80})</a>', raw):
            nodes.append(type("N", (), {"get": lambda k, d="", m=match: m.group(1) if k == "href" else "",
                                        "get_text": lambda m=match: m.group(2)})())
    keyword_list = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    for node in nodes:
        href = node.get("href", "") if hasattr(node, "get") else ""
        text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node)
        if not href or len(text.strip()) < 4:
            continue
        if keyword_list and not any(k in text for k in keyword_list):
            continue
        url = urllib.parse.urljoin(base_url, href)
        items.append({"title": text.strip()[:120], "url": url})
        if len(items) >= CRAWL_LIST_LIMIT:
            break
    return _dedup_items(items)


def _dedup_items(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for item in items:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        out.append(item)
    return out


# ------------------------------------------------------------------ 测试抓取
def test_source(payload: Dict) -> Dict:
    """保存信源前"测试抓取"：抓取列表页/订阅，预览解析结果（不入库、不落台账）。

    返回：
    - ok：是否成功
    - message：失败原因或提示
    - items：解析出的条目（标题 + 链接，最多 20 条）
    - sample：首条正文的解析抽样（标题、链接、正文字数、正文片段），
      用于让管理员确认"选择器 / 关键词"配置能否截取到真正的政策正文。
    """
    url = (payload.get("url") or "").strip()
    if not url:
        return {"ok": False, "message": "请先填写信源地址", "items": [], "sample": None}

    source_type = payload.get("source_type", "LIST")
    try:
        resp = _fetch(url)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "message": f"列表页抓取失败：{exc}", "items": [], "sample": None}

    if source_type == "RSS":
        items = _parse_rss(resp.text)
    else:
        items = _parse_list(resp.text, url, payload.get("list_selector", "a"),
                            payload.get("title_keywords", ""))

    result = {
        "ok": True,
        "message": f"抓取成功，解析出 {len(items)} 条候选条目",
        "items": items[:20],
        "sample": None,
    }
    if not items:
        result["message"] = "抓取成功，但未解析出任何条目：请检查列表选择器或标题关键词是否过严"
        return result

    # 对首条做正文抽样，验证正文页能否正确解析出政策全文
    first = items[0]
    try:
        detail = _fetch(first["url"])
        detail.raise_for_status()
        parsed = parse_html(detail.text)
        text = " ".join((parsed.text or "").split())
        result["sample"] = {
            "title": first["title"],
            "url": first["url"],
            "text_length": len(text),
            "snippet": text[:300],
            "warning": "正文过短，疑似非政策正文" if len(text) < 200 else "",
        }
    except Exception as exc:
        result["sample"] = {
            "title": first["title"],
            "url": first["url"],
            "text_length": 0,
            "snippet": "",
            "warning": f"正文页抓取失败：{exc}",
        }
    return result


# ------------------------------------------------------------------ 采集执行
def run_source(db: Session, source_id: str, operator: str = "scheduler") -> Dict:
    source = db.query(CrawlSource).filter(CrawlSource.id == source_id).first()
    if not source:
        raise ValueError("信源不存在")
    started = dt.datetime.now()
    result = {"source_id": source.id, "found": 0, "new": 0, "updated": 0, "unchanged": 0, "failed": 0,
              "errors": []}
    source.last_status = CRAWL_STATUS["RUNNING"]
    db.commit()
    try:
        resp = _fetch(source.url)
        resp.raise_for_status()
    except Exception as exc:
        source.last_status = CRAWL_STATUS["FAILED"]
        source.last_error = f"列表页抓取失败：{exc}"
        source.last_run_at = started
        db.commit()
        audit_service.log_operation(db, "CRAWL", "CrawlSource", source.id, operator,
                                    {"status": "FAILED", "error": str(exc)})
        result["errors"].append(source.last_error)
        return result

    items = _parse_rss(resp.text) if source.source_type == "RSS" else _parse_list(
        resp.text, source.url, source.list_selector, source.title_keywords
    )
    result["found"] = len(items)
    source.total_found += len(items)

    for item in items:
        try:
            status, document_id, message, extras = _process_item(db, source, item)
        except Exception as exc:
            status, document_id, message, extras = "FAILED", "", str(exc)[:300], {}
        result_key = {"NEW": "new", "UPDATED": "updated", "UNCHANGED": "unchanged", "FAILED": "failed"}[status]
        result[result_key] += 1
        if status == "FAILED":
            result["errors"].append(f"{item['title']}：{message}")
        db.add(
            CrawlRecord(
                source_id=source.id,
                title=item["title"],
                url=item["url"],
                content_hash=extras.get("content_hash", ""),
                simhash=extras.get("simhash", ""),
                etag=extras.get("etag", ""),
                last_modified=extras.get("last_modified", ""),
                status=status,
                document_id=document_id,
                message=message,
                crawled_at=dt.datetime.now(),
            )
        )
        db.commit()

    source.last_run_at = dt.datetime.now()
    source.last_status = CRAWL_STATUS["SUCCESS"] if not result["errors"] else CRAWL_STATUS["FAILED"]
    source.last_error = "；".join(result["errors"][:3])
    source.total_new += result["new"] + result["updated"]
    db.commit()
    audit_service.log_operation(
        db, "CRAWL", "CrawlSource", source.id, operator,
        {"found": result["found"], "new": result["new"], "updated": result["updated"],
         "unchanged": result["unchanged"], "failed": result["failed"]},
    )
    logger.info("采集完成：%s，发现 %s 条，新增 %s 条", source.name, result["found"], result["new"])
    return result


def _process_item(db: Session, source: CrawlSource, item: Dict) -> tuple:
    """单条采集：增量识别 → 抓取正文 → 入库。返回 (状态, 文档ID, 说明, 指纹信息)。"""
    existing = (
        db.query(CrawlRecord)
        .filter(CrawlRecord.source_id == source.id, CrawlRecord.url == item["url"])
        .order_by(CrawlRecord.crawled_at.desc())
        .first()
    )

    try:
        resp = _fetch(item["url"])
        resp.raise_for_status()
    except Exception as exc:
        return "FAILED", "", f"正文抓取失败：{exc}", {}

    etag = resp.headers.get("ETag", "")
    last_modified = resp.headers.get("Last-Modified", "")
    fingerprints = {"etag": etag, "last_modified": last_modified}
    if existing and existing.etag and existing.etag == etag and existing.status != "FAILED":
        return "UNCHANGED", existing.document_id, "ETag 未变化", fingerprints

    parsed = parse_html(resp.text)
    text = parsed.text
    if len(text) < 200:
        return "FAILED", "", "正文过短（<200字），疑似非政策正文，已跳过", fingerprints

    doc_hash = content_hash(text)
    doc_sim = simhash(text)
    fingerprints.update({"content_hash": doc_hash, "simhash": doc_sim})
    if existing and existing.content_hash == doc_hash:
        return "UNCHANGED", existing.document_id, "内容 hash 未变化", fingerprints
    if existing and existing.simhash and hamming_distance(existing.simhash, doc_sim) <= SIMHASH_DISTANCE_THRESHOLD:
        return "UNCHANGED", existing.document_id, "SimHash 判定为近似重复", fingerprints

    status = "UPDATED" if existing else "NEW"
    try:
        document = ingest_service.ingest_document(
            db,
            title=item["title"],
            text=text,
            source_type="CRAWL",
            source_url=item["url"],
            source_id=source.id,
            pages=parsed.pages,
            meta_override={"topics": source.default_topics} if source.default_topics else {},
            operator="crawler",
            version_note="采集更新" if status == "UPDATED" else "采集入库",
        )
    except ValueError as exc:
        message = str(exc)
        if "未发生变化" in message:
            return "UNCHANGED", "", message, fingerprints
        return "FAILED", "", message, fingerprints
    except Exception as exc:
        return "FAILED", "", f"入库失败：{exc}", fingerprints

    message = "新发现并入库" if status == "NEW" else "发现更新并生成新版本"
    return status, document.id, message, fingerprints


def run_all(db: Session, operator: str = "scheduler") -> List[Dict]:
    sources = db.query(CrawlSource).filter(CrawlSource.enabled.is_(True)).all()
    return [run_source(db, source.id, operator) for source in sources]


def records(db: Session, page: int = 1, page_size: int = 20, source_id: str = "",
            status: str = "", keyword: str = "") -> Dict:
    query = db.query(CrawlRecord)
    if source_id:
        query = query.filter(CrawlRecord.source_id == source_id)
    if status:
        query = query.filter(CrawlRecord.status == status)
    if keyword:
        query = query.filter(CrawlRecord.title.like(f"%{keyword}%"))
    total = query.count()
    items = query.order_by(CrawlRecord.crawled_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    source_names = {s.id: s.name for s in db.query(CrawlSource).all()}
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "source_name": source_names.get(r.source_id, ""),
                "title": r.title,
                "url": r.url,
                "status": r.status,
                "message": r.message,
                "document_id": r.document_id,
                "crawled_at": r.crawled_at.strftime("%Y-%m-%d %H:%M:%S") if r.crawled_at else "",
            }
            for r in items
        ],
    }


def stats(db: Session) -> Dict:
    total_sources = db.query(CrawlSource).count()
    enabled = db.query(CrawlSource).filter(CrawlSource.enabled.is_(True)).count()
    today = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = db.query(CrawlRecord).filter(
        CrawlRecord.crawled_at >= today, CrawlRecord.status.in_(["NEW", "UPDATED"])
    ).count()
    failed = db.query(CrawlRecord).filter(CrawlRecord.status == "FAILED").count()
    crawled_docs = db.query(Document).filter(Document.source_type == "CRAWL").count()
    return {
        "total_sources": total_sources,
        "enabled_sources": enabled,
        "new_today": new_today,
        "failed_records": failed,
        "crawled_documents": crawled_docs,
    }
