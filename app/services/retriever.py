"""检索服务（RET-001～006）：混合召回 → 重排 → 过滤 → 排序 → 分页。

重排为启发式（接 BGE-Reranker 时替换 rerank() 内部实现即可）：
综合相关度、关键词覆盖、效力位阶、时效、精确短语命中。
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from app.core.config import (
    EMBEDDING_BACKEND,
    MIN_RELEVANCE_SCORE,
    MIN_SEMANTIC_SCORE,
    TOP_K_RECALL,
    VECTOR_BACKEND,
)
from app.db.models import PolicyBlock, Document
from app.services.indexer import get_index
from app.services.serializer import block_to_dict, highlight
from app.services.text_utils import tokenize

CURRENT_VALID = {"EFFECTIVE", "FUTURE"}
# 候选池大小：召回上限之外的额外余量，保证分页 total 与“被过滤计数”不被截断
CANDIDATE_POOL = 120
# 被时效过滤的条目，其相关度需达到头部结果的该比例才计入提示，避免噪声
EXCLUDED_RELATIVE_FLOOR = 0.75
# 结果保留门槛：低于头部结果该比例的条目视为弱相关，不计入命中数
RESULT_SCORE_RATIO = 0.55


def _coverage(query: str, text: str) -> float:
    tokens = set(tokenize(query))
    if not tokens:
        return 0.0
    hit = sum(1 for t in tokens if t in text)
    return hit / len(tokens)


def rerank(candidates: List[Dict], query: str, index) -> List[Dict]:
    """启发式重排：rrf + 覆盖度 + 位阶 + 时效 + 短语命中。"""
    max_rrf = max((c["rrf_score"] for c in candidates), default=1.0) or 1.0
    phrase = query.strip()
    result = []
    for cand in candidates:
        block = index.blocks.get(cand["block_id"])
        if not block:
            continue
        text = block.text
        base = cand["rrf_score"] / max_rrf
        cover = _coverage(query, text)
        level_bonus = min(block.hierarchy_rank, 60) / 60 * 0.12
        time_bonus = 0.08 if block.validity_status in CURRENT_VALID else -0.05
        phrase_bonus = 0.12 if phrase and phrase in text else 0.0
        final = 0.5 * base + 0.2 * cover + level_bonus + time_bonus + phrase_bonus
        cand = dict(cand)
        cand["final_score"] = round(final, 6)
        cand["coverage"] = round(cover, 4)
        result.append(cand)
    result.sort(key=lambda x: x["final_score"], reverse=True)
    return result


def search_blocks(
    db,
    query: str,
    filters: Optional[Dict] = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "relevance",
    only_current: bool = False,
) -> Dict:
    """主检索入口，返回分页结果与耗时。

    候选池取到 CANDIDATE_POOL 条再排序分页，避免 total 被召回上限截断；
    开启“仅现行有效”时同步统计因时效被排除的命中数，供前端提示。
    """
    started = time.time()
    filters = dict(filters or {})
    user_validity = filters.get("validity_statuses") or []
    excluded = 0

    index = get_index()
    top_k = max(TOP_K_RECALL, page * page_size, CANDIDATE_POOL)
    ranked = rerank(index.hybrid_search(query, filters, top_k=top_k), query, index)

    # 绝对相关性门槛：必须有真实的关键词命中，或达到语义相似度下限。
    # 否则一律视为"未命中"——否则仅靠位阶/时效等静态加权就能堆出高分，
    # 导致任意查询（含乱码）都返回大量弱相关结果，联网兜底也永远触发不了。
    ranked = [
        item for item in ranked
        if (item.get("bm25_score", 0.0) or 0.0) > 0
        or (item.get("vector_score", 0.0) or 0.0) >= MIN_SEMANTIC_SCORE
    ]

    if only_current and not user_validity:
        # 先重排再按时效拆分：只有“相关度接近头部结果”的条目才算被过滤的命中，
        # 否则弱相关噪声会被误当成“另有 N 条结果”。
        top_score = ranked[0]["final_score"] if ranked else 0.0
        floor = max(MIN_RELEVANCE_SCORE, top_score * EXCLUDED_RELATIVE_FLOOR)
        kept, dropped = [], []
        for item in ranked:
            if index.blocks[item["block_id"]].validity_status in CURRENT_VALID:
                kept.append(item)
            elif item["final_score"] >= floor:
                dropped.append(item)
        excluded = len(dropped)
        ranked = kept

    # 相关性下限：以头部结果分数为基准过滤弱相关噪声，让“共 N 条”贴近真实命中
    if ranked:
        floor = max(MIN_RELEVANCE_SCORE, ranked[0]["final_score"] * RESULT_SCORE_RATIO)
        ranked = [item for item in ranked if item["final_score"] >= floor]

    if sort_by == "date":
        ranked.sort(key=lambda x: index.blocks[x["block_id"]].publish_date or "", reverse=True)
    elif sort_by == "level":
        ranked.sort(key=lambda x: index.blocks[x["block_id"]].hierarchy_rank, reverse=True)

    total = len(ranked)
    start = (page - 1) * page_size
    page_items = ranked[start : start + page_size]

    ids = [item["block_id"] for item in page_items]
    blocks = {b.block_id: b for b in db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all()} if ids else {}
    doc_ids = {b.document_id for b in blocks.values()}
    titles = {d.id: d.title for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()} if doc_ids else {}

    keywords = _query_keywords(query)
    items = []
    for item in page_items:
        block = blocks.get(item["block_id"])
        if not block:
            continue
        payload = block_to_dict(block, titles.get(block.document_id, ""), item["final_score"], keywords)
        payload["bm25_score"] = round(item.get("bm25_score", 0.0), 4)
        payload["vector_score"] = round(item.get("vector_score", 0.0), 4)
        # 命中来源：语义（向量）/ 关键词（BM25）/ 两者共同命中，便于用户判断是否为语义召回
        vec = float(item.get("vector_score", 0.0) or 0.0)
        bm = float(item.get("bm25_score", 0.0) or 0.0)
        payload["semantic_score"] = round(vec, 4)
        payload["keyword_score"] = round(bm, 4)
        payload["match_type"] = "语义+关键词" if (vec > 0 and bm > 0) else ("语义" if vec > 0 else "关键词")
        items.append(payload)

    latency = int((time.time() - started) * 1000)
    return {
        "items": items,
        "total": total,
        "latency_ms": latency,
        "max_score": round(ranked[0]["final_score"], 6) if ranked else 0.0,
        "excluded_by_validity": excluded,
        "query": query,
        # 检索方式说明：语义向量 + 关键词混合召回（RAG），供前端展示"语义检索已启用"
        "retrieval": {
            "mode": "hybrid",
            "embedding_backend": EMBEDDING_BACKEND,
            "vector_backend": VECTOR_BACKEND,
        },
    }


def _query_keywords(query: str) -> List[str]:
    raw = [w for w in re.split(r"[\s，。；、？]+", query) if len(w) >= 2]
    return raw[:8]


def recall_for_qa(db, query: str, filters: Optional[Dict] = None, top_k: int = 5) -> List[Dict]:
    """问答召回：仅现行有效，返回带证据分的知识块。"""
    filters = dict(filters or {})
    filters["validity_statuses"] = sorted(CURRENT_VALID)
    index = get_index()
    candidates = index.hybrid_search(query, filters, top_k=max(top_k * 4, 20))
    ranked = rerank(candidates, query, index)[:top_k]
    if not ranked:
        return []
    ids = [item["block_id"] for item in ranked]
    blocks = {b.block_id: b for b in db.query(PolicyBlock).filter(PolicyBlock.block_id.in_(ids)).all()}
    doc_ids = {b.document_id for b in blocks.values()}
    titles = {d.id: d.title for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()} if doc_ids else {}
    out = []
    for item in ranked:
        block = blocks.get(item["block_id"])
        if not block:
            continue
        payload = block_to_dict(block, titles.get(block.document_id, ""), item["final_score"])
        payload["evidence_score"] = round(item["final_score"], 6)
        payload["coverage"] = item.get("coverage", 0.0)
        out.append(payload)
    return out


def is_evidence_enough(evidence: List[Dict]) -> bool:
    """证据充分性判定（QA-006 拒答机制）。"""
    if not evidence:
        return False
    return max(e["evidence_score"] for e in evidence) >= MIN_RELEVANCE_SCORE
