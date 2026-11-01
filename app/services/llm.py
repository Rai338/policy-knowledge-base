"""大模型接入（生成层）：DeepSeek API 为主，离线回退为抽取式生成。

无 API Key 时自动使用回退实现，保证整条链路可运行、可演示。
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

import httpx

from app.core.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT,
)
from app.core.logging import logger


class LLMError(RuntimeError):
    pass


def _strip_json_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


class DeepSeekClient:
    def __init__(self):
        self.base_url = DEEPSEEK_BASE_URL.rstrip("/")
        self.api_key = DEEPSEEK_API_KEY
        self.model = DEEPSEEK_MODEL
        self._client = httpx.Client(timeout=LLM_TIMEOUT)

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[dict], temperature: float = None, max_tokens: int = None) -> str:
        if not self.api_key:
            raise LLMError("未配置 DEEPSEEK_API_KEY")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": LLM_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens or LLM_MAX_TOKENS,
            "stream": False,
        }
        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise LLMError(f"DeepSeek 调用失败（{resp.status_code}）：{resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class LLMClient:
    """统一入口：优先 DeepSeek，失败/未配置时回退。"""

    def __init__(self):
        self.deepseek = DeepSeekClient()

    @property
    def backend(self) -> str:
        return "deepseek" if self.deepseek.available() else "extractive"

    def chat(self, messages: List[dict], temperature: float = None, max_tokens: int = None) -> str:
        if self.deepseek.available():
            return self.deepseek.chat(messages, temperature, max_tokens)
        raise LLMError("未配置大模型")

    def chat_json(self, messages: List[dict]) -> dict:
        content = self.chat(messages, temperature=0.1)
        try:
            return json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:
            logger.warning("大模型返回非 JSON：%s", content[:200])
            raise LLMError(f"模型返回内容无法解析为 JSON：{exc}") from exc


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def extractive_answer(question: str, evidence: List[dict]) -> str:
    """离线回退：基于检索证据生成"可溯源"答案（不使用任何生成式模型）。

    输出严格限定为证据原文摘录 + 出处，不产生编造内容。
    """
    if not evidence:
        return ""
    lines = [f"关于“{question}”，知识库中检索到以下依据：", ""]
    for idx, item in enumerate(evidence, start=1):
        text = " ".join((item.get("original_text") or "").split())
        snippet = text[:260] + ("…" if len(text) > 260 else "")
        source = item.get("document_title") or item.get("title") or "未命名文件"
        anchor = item.get("article_number") or ""
        lines.append(f"[{idx}] 《{source}》{anchor}：{snippet}")
    lines.append("")
    lines.append("以上内容均摘录自知识库原文，未做推断；如需确定性结论请以原文和主管部门解释为准。")
    return "\n".join(lines)
