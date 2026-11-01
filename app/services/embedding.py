"""向量编码（对应项目书 9.3：BGE-M3 为主，提供离线回退）。

后端：
- hash   : 特征哈希 + TF 加权（离线可用，当前默认）
- bge3   : 本地 BGE-M3（需 pip install FlagEmbedding 并下载模型）
- openai : 兼容 OpenAI 的 embedding 接口（DeepSeek 官方未提供 embedding，按需配置）
"""
from __future__ import annotations

import hashlib
import math
from typing import List, Optional

import numpy as np

from app.core.config import EMBEDDING_BACKEND, EMBEDDING_DIM, EMBEDDING_MODEL
from app.core.logging import logger
from app.services.text_utils import tokenize


class HashEmbedder:
    """离线可用的确定性向量：token 哈希到固定维度，TF 加权后 L2 归一化。"""

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def _hash(self, token: str) -> int:
        return int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)

    def encode_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        if not tokens:
            return vec
        for token in tokens:
            idx = self._hash(token) % self.dim
            vec[idx] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.encode_one(t) for t in texts])


class BGEEmbedder:
    """本地 BGE-M3（可选）。"""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415 延迟导入

        self.model = BGEM3FlagModel(model_name, use_fp16=False)

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1024), dtype=np.float32)
        output = self.model.encode(texts, max_length=1024)["dense_vecs"]
        return np.asarray(output, dtype=np.float32)


class OpenAIEmbedder:
    """兼容 OpenAI 的 embedding 接口。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        import httpx  # noqa: PLC0415

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=30)

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1536), dtype=np.float32)
        resp = self._client.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return np.asarray([d["embedding"] for d in data], dtype=np.float32)


class EmbeddingClient:
    """统一入口：按配置选择后端，失败自动降级为 hash。"""

    def __init__(self):
        self.backend = EMBEDDING_BACKEND
        self.impl: Optional[object] = None
        self.dim = EMBEDDING_DIM
        self._init_impl()

    def _init_impl(self) -> None:
        try:
            if self.backend == "bge3":
                self.impl = BGEEmbedder()
                self.dim = 1024
            elif self.backend == "openai":
                import os

                self.impl = OpenAIEmbedder(
                    os.getenv("PKB_EMBEDDING_BASE_URL", "https://api.deepseek.com"),
                    os.getenv("PKB_EMBEDDING_API_KEY", ""),
                    os.getenv("PKB_EMBEDDING_MODEL_NAME", "text-embedding-3-small"),
                )
                self.dim = 1536
            else:
                self.impl = HashEmbedder(self.dim)
        except Exception as exc:  # pragma: no cover
            logger.warning("向量后端 %s 初始化失败，降级为 hash：%s", self.backend, exc)
            self.backend = "hash"
            self.impl = HashEmbedder(self.dim)

    def encode(self, texts: List[str]) -> np.ndarray:
        try:
            return self.impl.encode(texts)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            logger.warning("向量编码失败，使用 hash 回退：%s", exc)
            return HashEmbedder(self.dim).encode(texts)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


_embedder: Optional[EmbeddingClient] = None


def get_embedder() -> EmbeddingClient:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingClient()
    return _embedder
