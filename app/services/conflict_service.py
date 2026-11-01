"""政策冲突初筛（CON-001～005，验证性 PoC）：异步任务 + 多维度规则比对 + 分级结果 + 报告导出。

判定维度：时效 / 位阶 / 适用主体 / 地域 / 同一事项口径。
结论分三级：疑似冲突（SUSPECTED）、潜在冲突（POTENTIAL）、未发现冲突（NONE）。
"""
from __future__ import annotations

import datetime as dt
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import CONFLICT_PAIR_LIMIT, EXPORT_DIR, MAX_CONFLICT_WORKERS
from app.core.constants import CONFLICT_DIMENSIONS, EFFECT_LEVEL_RANK, TASK_STATUS, region_matches
from app.core.logging import logger
from app.db.database import SessionLocal
from app.db.models import ConflictFinding, ConflictTask, Document, PolicyBlock
from app.services import audit_service
from app.services.indexer import get_index
from app.services.llm import LLMError, get_llm
from app.services.text_utils import tokenize

_executor = ThreadPoolExecutor(max_workers=MAX_CONFLICT_WORKERS, thread_name_prefix="conflict")

RE_METRIC = re.compile(r"(\d+(?:\.\d+)?)\s*(%|％|万元|亿元|元|日|天|个月|月|年|人次|家)")
RE_DATE = re.compile(r"(?:19|20)\d{2}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?")
RE_NEGATIVE = re.compile(r"(不得|禁止|不予|取消|停止)")
RE_PERMISSIVE = re.compile(r"(可以|应当给予|予以支持|享受)")


# ------------------------------------------------------------------ 规则
def _metrics(text: str) -> List[Tuple[str, float]]:
    """抽取量化指标；先剔除日期，避免把年份/日期当成指标造成误报。"""
    cleaned = RE_DATE.sub(" ", text or "")
    result = []
    for value, unit in RE_METRIC.findall(cleaned):
        number = float(value)
        if unit == "年" and 1900 <= number <= 2100:  # 残留年份
            continue
        result.append((unit, number))
    return result


def _similarity(text_a: str, text_b: str) -> float:
    set_a, set_b = set(tokenize(text_a)), set(tokenize(text_b))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _metrics_conflict(a: PolicyBlock, b: PolicyBlock) -> Optional[str]:
    ma, mb = _metrics(a.original_text), _metrics(b.original_text)
    for unit, value_a in ma:
        for unit_b, value_b in mb:
            if unit == unit_b and abs(value_a - value_b) > 1e-6:
                return f"同一类指标“{unit}”取值不一致：{value_a}{unit} vs {value_b}{unit}"
    return None


def _detect_pair(a: PolicyBlock, b: PolicyBlock, dimensions: List[str]) -> List[Dict]:
    """对一对知识块逐维度检测。"""
    findings: List[Dict] = []
    text_a, text_b = a.original_text or "", b.original_text or ""
    sim = _similarity(text_a, text_b)
    if sim < 0.12:
        return findings

    def make(dim: str, level: str, reason: str, suggestion: str) -> Dict:
        return {
            "dimension": dim,
            "level": level,
            "block_a_id": a.block_id,
            "block_b_id": b.block_id,
            "reason": reason,
            "suggestion": suggestion,
            "similarity": round(sim, 4),
        }

    # 时效（TIME）
    if "TIME" in dimensions:
        today = dt.date.today().isoformat()
        a_expired = a.validity_status in ("ABOLISHED", "EXPIRED")
        b_expired = b.validity_status in ("ABOLISHED", "EXPIRED")
        if a_expired != b_expired:
            findings.append(
                make(
                    "TIME",
                    "SUSPECTED",
                    f"时效状态不一致：一侧为“{a.validity_status}”，另一侧为“{b.validity_status}”，"
                    f"但内容相似度 {sim:.2f}，可能存在新旧规定并行",
                    "按“新法优于旧法”原则适用现行有效文本，并核实废止文件的替代关系",
                )
            )
        elif a.effective_date and b.effective_date and a.effective_date != b.effective_date and sim > 0.3:
            findings.append(
                make(
                    "TIME",
                    "POTENTIAL",
                    f"生效日期不同（{a.effective_date} vs {b.effective_date}）但事项高度相似",
                    "以生效日期较晚者为准，必要时提请主管部门明确",
                )
            )

    # 位阶（LEVEL）
    if "LEVEL" in dimensions:
        rank_a = EFFECT_LEVEL_RANK.get(a.effect_level, 10)
        rank_b = EFFECT_LEVEL_RANK.get(b.effect_level, 10)
        conflict_reason = _metrics_conflict(a, b)
        if rank_a != rank_b and sim > 0.25 and conflict_reason:
            higher, lower = (a, b) if rank_a > rank_b else (b, a)
            findings.append(
                make(
                    "LEVEL",
                    "SUSPECTED",
                    f"位阶不同且规定不一致：{higher.effect_level}（{higher.title}） vs "
                    f"{lower.effect_level}（{lower.title}）；{conflict_reason}",
                    "优先适用位阶更高的规定；低位阶规定与上位法不一致的应不予适用",
                )
            )
        elif rank_a != rank_b and sim > 0.35:
            findings.append(
                make("LEVEL", "POTENTIAL", f"位阶不同（{a.effect_level} vs {b.effect_level}）且事项相似", "核实地方法与上位法的衔接关系")
            )

    # 适用主体（SUBJECT）
    if "SUBJECT" in dimensions:
        set_a, set_b = set(a.applicable_subjects or []), set(b.applicable_subjects or [])
        if set_a and set_b and not (set_a & set_b) and sim > 0.25:
            findings.append(
                make(
                    "SUBJECT",
                    "POTENTIAL",
                    f"适用主体不同（{'、'.join(set_a)} vs {'、'.join(set_b)}）但事项相似",
                    "确认两类主体的适用边界，避免扩大或限缩适用范围",
                )
            )

    # 地域（REGION）
    if "REGION" in dimensions:
        set_a, set_b = set(a.jurisdiction or []), set(b.jurisdiction or [])
        if set_a and set_b and not (set_a & set_b) and sim > 0.3:
            findings.append(
                make("REGION", "POTENTIAL", f"适用地域不同（{'、'.join(set_a)} vs {'、'.join(set_b)}）但内容相似",
                     "按属地原则适用，跨区域经营情形需进一步明确")
            )

    # 同一事项口径（MATTER）
    if "MATTER" in dimensions:
        metric_reason = _metrics_conflict(a, b)
        if metric_reason and sim > 0.25:
            findings.append(
                make("MATTER", "SUSPECTED", f"同一事项口径不一致：{metric_reason}", "核实适用条件差异（如行业、规模、时间窗口），并在答复中明确适用前提")
            )
        elif sim > 0.3 and (RE_NEGATIVE.search(text_a) and RE_PERMISSIVE.search(text_b)
                            or RE_NEGATIVE.search(text_b) and RE_PERMISSIVE.search(text_a)):
            findings.append(
                make("MATTER", "SUSPECTED", "表述方向相反：一侧为禁止性规定，另一侧为允许/支持性规定",
                     "以禁止性规定或上位法为准，提交主管部门释疑")
            )
        elif sim > 0.45:
            findings.append(make("MATTER", "POTENTIAL", "内容高度相似，可能为重复规定或新旧并存", "核对是否为同一规定的不同版本"))
    return findings


# ------------------------------------------------------------------ 任务
def _load_pairs(db: Session, document_ids: List[str], limit: int, region: str = "") -> List[Tuple[PolicyBlock, PolicyBlock]]:
    query = db.query(PolicyBlock)
    if document_ids:
        query = query.filter(PolicyBlock.document_id.in_(document_ids))
    blocks = query.limit(600).all()
    # 地区约束（A+C 方案）：选中某市时只纳入本市 + 本省上位法 + 全国文件，
    # 排除同省其它市文件，实现「同地域优先比对」。
    if region:
        blocks = [b for b in blocks if region_matches(list(b.jurisdiction or []), region)]
    if len(blocks) < 2:
        return []
    index = get_index()
    # 收集全部候选配对后按相似度排序取前 limit：保证各地域下都优先比对
    # 最相似（最可能冲突）的配对，避免因遍历顺序导致本市专属配对被截断，
    # 从而让「地区切换」在冲突初筛页也真正生效。
    candidates: List[Tuple[float, PolicyBlock, PolicyBlock]] = []
    seen = set()
    by_id = {b.block_id: b for b in blocks}
    for block in blocks:
        for hit in index.similar_blocks(block.block_id, top_k=4):
            other = by_id.get(hit["block_id"])
            if not other or other.block_id == block.block_id:
                continue
            key = tuple(sorted([block.block_id, other.block_id]))
            if key in seen:
                continue
            seen.add(key)
            candidates.append((hit.get("score", 0.0), block, other))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [(b, o) for _, b, o in candidates[:limit]]


def _run_task(task_id: str) -> None:
    db: Session = SessionLocal()
    try:
        task = db.query(ConflictTask).filter(ConflictTask.id == task_id).first()
        if not task:
            return
        task.status = TASK_STATUS["RUNNING"]
        task.started_at = dt.datetime.now()
        db.commit()

        dimensions = list(task.dimensions or list(CONFLICT_DIMENSIONS.keys()))
        pairs = _load_pairs(db, list(task.document_ids or []), CONFLICT_PAIR_LIMIT, region=task.region or "")
        task.total_pairs = len(pairs)
        db.commit()

        findings: List[Dict] = []
        for done, (a, b) in enumerate(pairs, start=1):
            findings.extend(_detect_pair(a, b, dimensions))
            task.done_pairs = done
            task.progress = int(done * 100 / max(len(pairs), 1))
            if done % 5 == 0:
                db.commit()

        findings = _dedup(findings)
        findings = _llm_review(findings, db)

        for item in findings:
            db.add(
                ConflictFinding(
                    task_id=task.id,
                    dimension=item["dimension"],
                    level=item["level"],
                    block_a_id=item["block_a_id"],
                    block_b_id=item["block_b_id"],
                    reason=item["reason"],
                    suggestion=item["suggestion"],
                    evidence=item.get("evidence", []),
                )
            )
        task.finding_count = len(findings)
        task.progress = 100
        task.status = TASK_STATUS["SUCCESS"]
        task.finished_at = dt.datetime.now()
        db.commit()
        logger.info("冲突检测任务 %s 完成，发现 %s 条", task_id, len(findings))
    except Exception as exc:  # pragma: no cover
        logger.exception("冲突检测任务失败：%s", exc)
        task = db.query(ConflictTask).filter(ConflictTask.id == task_id).first()
        if task:
            task.status = TASK_STATUS["FAILED"]
            task.error = str(exc)
            task.finished_at = dt.datetime.now()
            db.commit()
    finally:
        db.close()


def _dedup(findings: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for item in findings:
        key = (item["dimension"], item["block_a_id"], item["block_b_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _llm_review(findings: List[Dict], db: Session, limit: int = 20) -> List[Dict]:
    """大模型复核（可选）：为疑似冲突补充自然语言说明。"""
    if not findings:
        return findings
    suspects = [f for f in findings if f["level"] == "SUSPECTED"][:limit]
    if not suspects:
        return findings
    blocks = {}
    ids = {f["block_a_id"] for f in suspects} | {f["block_b_id"] for f in suspects}
    for block in db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all():
        blocks[block.block_id] = block
    try:
        llm = get_llm()
        if llm.backend == "extractive":
            return findings
        for item in suspects:
            a = blocks.get(item["block_a_id"])
            b = blocks.get(item["block_b_id"])
            if not a or not b:
                continue
            content = llm.chat(
                [
                    {"role": "system", "content": "你是政策合规审查助手，只依据材料判断，输出一句话结论。"},
                    {
                        "role": "user",
                        "content": (
                            f"材料A：{' '.join((a.original_text or '').split())[:400]}\n"
                            f"材料B：{' '.join((b.original_text or '').split())[:400]}\n"
                            f"问题：二者是否构成{item['dimension']}维度的冲突？一句话说明结论与依据。"
                        ),
                    },
                ],
                max_tokens=200,
            )
            item["reason"] = f"{item['reason']}｜模型复核：{content.strip()[:200]}"
            item["evidence"] = [
                {"side": "A", "block_id": a.block_id, "text": " ".join((a.original_text or "").split())[:160]},
                {"side": "B", "block_id": b.block_id, "text": " ".join((b.original_text or "").split())[:160]},
            ]
    except LLMError as exc:
        logger.info("冲突复核未使用大模型：%s", exc)
    return findings


def create_task(db: Session, name: str, document_ids: List[str], dimensions: List[str],
                operator: str = "user", region: str = "") -> ConflictTask:
    if not dimensions:
        dimensions = list(CONFLICT_DIMENSIONS.keys())
    task = ConflictTask(
        name=name or "冲突检测任务",
        document_ids=list(document_ids or []),
        dimensions=dimensions,
        region=region or "",
        status=TASK_STATUS["PENDING"],
    )
    db.add(task)
    db.commit()
    audit_service.log_operation(db, "CONFLICT", "ConflictTask", task.id, operator,
                                {"document_ids": document_ids, "dimensions": dimensions, "region": region})
    _executor.submit(_run_task, task.id)
    return task


def get_task(db: Session, task_id: str) -> Optional[Dict]:
    task = db.query(ConflictTask).filter(ConflictTask.id == task_id).first()
    if not task:
        return None
    findings = (
        db.query(ConflictFinding).filter(ConflictFinding.task_id == task_id)
        .order_by(ConflictFinding.created_at).all()
    )
    ids = {f.block_a_id for f in findings} | {f.block_b_id for f in findings}
    blocks = {b.block_id: b for b in db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all()} if ids else {}

    def brief(block_id: str) -> Dict:
        block = blocks.get(block_id)
        if not block:
            return {"block_id": block_id}
        return {
            "block_id": block.block_id,
            "document_id": block.document_id,
            "title": block.title,
            "article_number": block.article_number,
            "effect_level": block.effect_level,
            "validity_status": block.validity_status,
            "text": " ".join((block.original_text or "").split())[:200],
        }

    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "progress": task.progress,
        "total_pairs": task.total_pairs,
        "done_pairs": task.done_pairs,
        "finding_count": task.finding_count,
        "dimensions": task.dimensions,
        "region": task.region or "",
        "error": task.error,
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S") if task.created_at else "",
        "finished_at": task.finished_at.strftime("%Y-%m-%d %H:%M:%S") if task.finished_at else "",
        "findings": [
            {
                "id": f.id,
                "dimension": f.dimension,
                "dimension_name": CONFLICT_DIMENSIONS.get(f.dimension, f.dimension),
                "level": f.level,
                "reason": f.reason,
                "suggestion": f.suggestion,
                "evidence": f.evidence,
                "block_a": brief(f.block_a_id),
                "block_b": brief(f.block_b_id),
            }
            for f in findings
        ],
    }


def list_tasks(db: Session, page: int = 1, page_size: int = 10) -> Dict:
    query = db.query(ConflictTask)
    total = query.count()
    items = query.order_by(ConflictTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "status": t.status,
                "progress": t.progress,
                "total_pairs": t.total_pairs,
                "done_pairs": t.done_pairs,
                "finding_count": t.finding_count,
                "region": t.region or "",
                "error": t.error,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "",
            }
            for t in items
        ],
    }


def export_report(db: Session, task_id: str) -> str:
    data = get_task(db, task_id)
    if not data:
        raise ValueError("任务不存在")
    lines = [
        f"# 政策冲突初筛报告：{data['name']}",
        "",
        f"- 任务编号：{data['id']}",
        f"- 生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 检测维度：{', '.join(CONFLICT_DIMENSIONS.get(d, d) for d in data['dimensions'])}",
        f"- 比对组合：{data['total_pairs']} 对，发现 {data['finding_count']} 条",
        "",
        "## 结论明细",
        "",
    ]
    for idx, finding in enumerate(data["findings"], start=1):
        lines.append(
            f"{idx}. 【{finding['dimension_name']}｜{finding['level']}】{finding['reason']}\n"
            f"   - 建议：{finding['suggestion']}\n"
            f"   - 依据A：{finding['block_a'].get('title', '')} {finding['block_a'].get('article_number', '')}\n"
            f"   - 依据B：{finding['block_b'].get('title', '')} {finding['block_b'].get('article_number', '')}"
        )
    lines.append("")
    lines.append("> 本报告为规则初筛结果（PoC），不构成法律意见，正式适用前须经主管部门确认。")
    content = "\n".join(lines)
    path = EXPORT_DIR / f"conflict-{task_id}.md"
    path.write_text(content, encoding="utf-8")
    audit_service.log_operation(db, "CONFLICT", "ConflictTask", task_id, "user", {"action": "export"})
    return str(path)
