"""索引层（RET-001/002）：BM25 全文索引 + 向量索引（FAISS 优先，numpy 回退）。

索引在内存中维护，启动时从数据库全量重建（单机演示体量足够）；
接口与 Milvus 适配层保持一致，后续替换只需实现同样的 add/search/remove。
"""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.core.config import RRF_K, VECTOR_BACKEND
from app.core.constants import EFFECT_LEVEL_RANK, category_of_level, region_matches
from app.core.logging import logger
from app.services.embedding import get_embedder
from app.services.text_utils import tokenize


@dataclass
class IndexedBlock:
    block_id: str
    document_id: str
    document_title: str
    text: str
    tokens: List[str] = field(default_factory=list)
    effect_level: str = "OTHER"
    doc_category: str = "POLICY"      # POLICY 政策文件 | REGULATION 法规
    topics: List[str] = field(default_factory=list)
    jurisdiction: List[str] = field(default_factory=list)
    applicable_subjects: List[str] = field(default_factory=list)
    validity_status: str = "EFFECTIVE"
    institution_level: str = "OTHER"
    publish_date: str = ""
    hierarchy_rank: int = 10
    article_number: str = ""
    granularity: str = "ARTICLE"


class BM25:
    """经典 BM25（k1=1.5, b=0.75）。

    注意：本类不做增量删除，索引重建时整体替换。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_len: Dict[str, int] = {}
        self.doc_tokens: Dict[str, List[str]] = {}
        self.df: Dict[str, int] = {}
        self.avgdl = 0.0
        self.n = 0

    def add(self, block_id: str, tokens: Sequence[str]) -> None:
        self.doc_tokens[block_id] = list(tokens)
        self.doc_len[block_id] = len(tokens)
        for token in set(tokens):
            self.df[token] = self.df.get(token, 0) + 1
        self.n = len(self.doc_len)
        self.avgdl = (sum(self.doc_len.values()) / self.n) if self.n else 0.0

    def clear(self) -> None:
        self.doc_len.clear()
        self.doc_tokens.clear()
        self.df.clear()
        self.n = 0
        self.avgdl = 0.0

    def idf(self, token: str) -> float:
        df = self.df.get(token, 0)
        return float(np.log(1 + (self.n - df + 0.5) / (df + 0.5)))

    def scores(self, query_tokens: Sequence[str], candidates: Sequence[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for block_id in candidates:
            tokens = self.doc_tokens.get(block_id, [])
            if not tokens:
                continue
            tf: Dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            length = self.doc_len[block_id]
            score = 0.0
            for token in set(query_tokens):
                freq = tf.get(token, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * length / (self.avgdl or 1.0))
                score += self.idf(token) * freq * (self.k1 + 1) / denom
            out[block_id] = score
        return out


class VectorIndex:
    """向量索引：FAISS 可用则使用，否则 numpy 余弦。"""

    def __init__(self, dim: int):
        self.dim = dim
        self.ids: List[str] = []
        self.matrix = np.zeros((0, dim), dtype=np.float32)
        self.kind = "numpy"
        self._faiss = None
        if VECTOR_BACKEND in ("auto", "faiss"):
            try:
                import faiss  # noqa: PLC0415

                self._faiss = faiss.IndexFlatIP(dim)
                self.kind = "faiss"
            except Exception:  # pragma: no cover
                self._faiss = None
                self.kind = "numpy"

    def add(self, ids: List[str], vectors: np.ndarray) -> None:
        if not ids:
            return
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.shape[1] != self.dim:
            self.dim = vectors.shape[1]
            self.matrix = np.zeros((0, self.dim), dtype=np.float32)
            self._faiss = None
        self.ids.extend(ids)
        self.matrix = np.vstack([self.matrix, vectors]) if len(self.matrix) else vectors
        if self._faiss is not None:
            self._faiss.add(vectors)

    def clear(self) -> None:
        self.ids = []
        self.matrix = np.zeros((0, self.dim), dtype=np.float32)
        if self._faiss is not None:
            self._faiss.reset()

    def search(self, query_vec: np.ndarray, top_n: int) -> List[tuple]:
        if not self.ids:
            return []
        query_vec = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        if self._faiss is not None:
            scores, idx = self._faiss.search(query_vec, min(top_n, len(self.ids)))
            return [(self.ids[i], float(scores[0][k])) for k, i in enumerate(idx[0]) if i >= 0]
        sims = self.matrix @ query_vec[0]
        order = np.argsort(-sims)[:top_n]
        return [(self.ids[int(i)], float(sims[int(i)])) for i in order]


class IndexStore:
    """知识块索引（单例）。"""

    def __init__(self):
        self.blocks: Dict[str, IndexedBlock] = {}
        self.bm25 = BM25()
        self.vector = VectorIndex(get_embedder().dim)
        self.lock = threading.RLock()

    # ------------------------------------------------------------ 写入
    def add(self, blocks: List[IndexedBlock]) -> int:
        if not blocks:
            return 0
        embedder = get_embedder()
        with self.lock:
            texts = [b.text for b in blocks]
            vectors = embedder.encode(texts)
            if self.vector.dim != vectors.shape[1]:
                self.rebuild_vectors()
            for block in blocks:
                self.blocks[block.block_id] = block
                self.bm25.add(block.block_id, block.tokens)
            self.vector.add([b.block_id for b in blocks], vectors)
        logger.info("索引新增 %s 个知识块，当前总量 %s", len(blocks), len(self.blocks))
        return len(blocks)

    def remove_document(self, document_id: str) -> int:
        with self.lock:
            ids = [b.block_id for b in self.blocks.values() if b.document_id == document_id]
            for block_id in ids:
                self.blocks.pop(block_id, None)
            self._rebuild()
        return len(ids)

    def clear(self) -> None:
        with self.lock:
            self.blocks.clear()
            self._rebuild()

    def rebuild_vectors(self) -> None:
        with self.lock:
            self._rebuild()

    def _rebuild(self) -> None:
        self.bm25.clear()
        self.vector = VectorIndex(get_embedder().dim)
        blocks = list(self.blocks.values())
        if not blocks:
            return
        for block in blocks:
            self.bm25.add(block.block_id, block.tokens)
        vectors = get_embedder().encode([b.text for b in blocks])
        self.vector.add([b.block_id for b in blocks], vectors)

    # ------------------------------------------------------------ 检索
    @staticmethod
    def _match_filters(block: IndexedBlock, filters: Dict) -> bool:
        if not filters:
            return True
        if filters.get("effect_levels") and block.effect_level not in filters["effect_levels"]:
            return False
        # 文件大类筛选：政策文件 / 法规
        if filters.get("doc_categories") and block.doc_category not in filters["doc_categories"]:
            return False
        if filters.get("validity_statuses") and block.validity_status not in filters["validity_statuses"]:
            return False
        if filters.get("institution_levels") and block.institution_level not in filters["institution_levels"]:
            return False
        if filters.get("granularity") and block.granularity != filters["granularity"]:
            return False
        for key, field_name in (
            ("topics", "topics"),
            ("jurisdictions", "jurisdiction"),
            ("subjects", "applicable_subjects"),
        ):
            wanted = filters.get(key)
            if wanted and not set(wanted) & set(getattr(block, field_name)):
                return False
        # 地区切换：本市 → 本省（仅省，不含他市）→ 全国 的梯度过滤
        region = filters.get("region")
        if region and not region_matches(block.jurisdiction, region):
            return False
        date_from = filters.get("date_from")
        if date_from and block.publish_date and block.publish_date < date_from:
            return False
        date_to = filters.get("date_to")
        if date_to and block.publish_date and block.publish_date > date_to:
            return False
        if filters.get("document_ids") and block.document_id not in filters["document_ids"]:
            return False
        return True

    def candidates(self, filters: Optional[Dict] = None) -> List[str]:
        filters = filters or {}
        return [bid for bid, b in self.blocks.items() if self._match_filters(b, filters)]

    def hybrid_search(
        self,
        query: str,
        filters: Optional[Dict] = None,
        top_k: int = 20,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> List[Dict]:
        """BM25 + 向量双路召回，RRF 融合后返回候选（含各路得分）。"""
        with self.lock:
            allowed = set(self.candidates(filters))
            if not allowed:
                return []
            query_tokens = tokenize(query)
            bm25_scores = self.bm25.scores(query_tokens, list(self.bm25.doc_tokens.keys()))
            vector_hits = dict(self.vector.search(get_embedder().encode_one(query), top_k * 3))
            merged: Dict[str, Dict] = {}
            ranks_bm25 = _rank_dict(bm25_scores)
            ranks_vec = _rank_dict(vector_hits)
            for block_id in set(ranks_bm25) | set(ranks_vec):
                if block_id not in allowed:
                    continue
                rrf = bm25_weight / (RRF_K + ranks_bm25.get(block_id, 999)) + \
                      vector_weight / (RRF_K + ranks_vec.get(block_id, 999))
                merged[block_id] = {
                    "block_id": block_id,
                    "rrf_score": rrf,
                    "bm25_score": bm25_scores.get(block_id, 0.0),
                    "vector_score": vector_hits.get(block_id, 0.0),
                }
            result = sorted(merged.values(), key=lambda x: x["rrf_score"], reverse=True)
            return result[: max(top_k, 1)]

    def similar_blocks(self, block_id: str, top_k: int = 5) -> List[Dict]:
        block = self.blocks.get(block_id)
        if not block:
            return []
        hits = self.vector.search(get_embedder().encode_one(block.text), top_k + 1)
        return [
            {"block_id": bid, "score": score}
            for bid, score in hits
            if bid != block_id
        ][:top_k]

    def stats(self) -> Dict:
        return {
            "block_count": len(self.blocks),
            "document_count": len({b.document_id for b in self.blocks.values()}),
            "vector_backend": self.vector.kind,
            "vector_dim": self.vector.dim,
        }


def _rank_dict(scores: Dict[str, float]) -> Dict[str, int]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return {bid: i + 1 for i, (bid, _) in enumerate(ordered)}


_store: Optional[IndexStore] = None


def get_index() -> IndexStore:
    global _store
    if _store is None:
        _store = IndexStore()
    return _store


def block_to_indexed(block) -> IndexedBlock:
    text = " ".join(
        part for part in (block.title, block.original_text, " ".join(block.topics or [])) if part
    )
    return IndexedBlock(
        block_id=block.block_id,
        document_id=block.document_id,
        document_title=getattr(block, "document_title", "") or "",
        text=text,
        tokens=tokenize(text),
        effect_level=block.effect_level,
        doc_category=(getattr(block, "doc_category", "") or category_of_level(block.effect_level)),
        topics=list(block.topics or []),
        jurisdiction=list(block.jurisdiction or []),
        applicable_subjects=list(block.applicable_subjects or []),
        validity_status=block.validity_status,
        institution_level=block.institution_level,
        publish_date=block.publish_date or "",
        hierarchy_rank=EFFECT_LEVEL_RANK.get(block.effect_level, 10),
        article_number=block.article_number or "",
        granularity=block.granularity or "ARTICLE",
    )


def load_index_from_db(db) -> Dict:
    """从数据库全量重建索引（启动时调用）。"""
    from app.db.models import Document, PolicyBlock

    store = get_index()
    store.clear()
    documents = {d.id: d.title for d in db.query(Document).all()}
    blocks = db.query(PolicyBlock).all()
    indexed = []
    for block in blocks:
        item = block_to_indexed(block)
        item.document_title = documents.get(block.document_id, "")
        indexed.append(item)
    store.add(indexed)
    logger.info("索引重建完成：%s 个知识块 / %s 份文件", len(indexed), len(documents))
    return store.stats()
