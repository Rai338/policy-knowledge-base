"""联网检索兜底（RET-007）：本地知识库未命中时，自动转为联网检索补充。

设计要点：
1. 可插拔 provider：设置 PKB_WEBSEARCH_PROVIDER 与 PKB_WEBSEARCH_API_KEY 即启用
   真实联网检索；内置 tavily / bocha，另支持 custom（自建兼容端点）。
2. 优雅降级：未配置密钥或联网失败时，不抛异常、不虚构结果，
   返回"检索建议 + 候选官方渠道入口"，保证演示与功能不中断。
3. 联网结果统一标注来源引擎，并提示"来自站外、需人工核实"，
   与本地政策知识块明确区分，不混入可溯源引证。
"""
from __future__ import annotations

import urllib.parse
from typing import Dict, List, Optional

import httpx

from app.core.config import (
    WEBSEARCH_API_KEY,
    WEBSEARCH_ENDPOINT,
    WEBSEARCH_MAX_RESULTS,
    WEBSEARCH_PROVIDER,
    WEBSEARCH_TIMEOUT,
)
from app.core.logging import logger

# 未配置联网检索时给出的官方渠道建议（避免返回空结果让用户无从下手）
FALLBACK_SOURCES = [
    {
        "name": "中国政府网 · 政策文件检索",
        "template": "https://sousuo.www.gov.cn/sousuo/search.shtml?searchWord={q}",
    },
    {"name": "国家法律法规数据库", "template": "https://flk.npc.gov.cn/"},
    {"name": "必应检索", "template": "https://www.bing.com/search?q={q}"},
    {"name": "百度检索", "template": "https://www.baidu.com/s?wd={q}"},
]

DEGRADED_MESSAGE = (
    "本地知识库未检索到相关内容，且当前未配置联网检索服务。"
    "已为你提供官方渠道的检索入口（站外结果请人工核实）。"
)


def is_configured() -> bool:
    """是否已配置可用的联网检索服务。"""
    provider = (WEBSEARCH_PROVIDER or "").strip().lower()
    if not provider:
        return False
    if provider == "custom":
        return bool(WEBSEARCH_ENDPOINT)
    return bool(WEBSEARCH_API_KEY)


def _suggestions(query: str) -> List[Dict]:
    """生成官方渠道检索入口。"""
    quoted = urllib.parse.quote(query or "")
    out: List[Dict] = []
    for item in FALLBACK_SOURCES:
        template = item["template"]
        url = template.replace("{q}", quoted) if "{q}" in template else template
        out.append({"name": item["name"], "url": url})
    return out


def _degraded(query: str, message: str = "") -> Dict:
    """降级响应：不含任何虚构结果。"""
    return {
        "query": query,
        "engine": "",
        "degraded": True,
        "message": message or DEGRADED_MESSAGE,
        "results": [],
        "suggestions": _suggestions(query),
    }


def _normalize(items: List[Dict], engine: str) -> List[Dict]:
    """统一结果结构：title / url / snippet / source。"""
    out: List[Dict] = []
    for raw in items[:WEBSEARCH_MAX_RESULTS]:
        title = (raw.get("title") or raw.get("name") or "").strip()
        url = (raw.get("url") or raw.get("link") or "").strip()
        if not (title or url):
            continue
        snippet = (raw.get("content") or raw.get("snippet") or raw.get("summary") or "").strip()
        out.append({"title": title, "url": url, "snippet": snippet[:300], "source": engine})
    return out


def _tavily_search(query: str) -> Optional[List[Dict]]:
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": WEBSEARCH_API_KEY,
            "query": query,
            "max_results": WEBSEARCH_MAX_RESULTS,
            "search_depth": "basic",
        },
        timeout=WEBSEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return (resp.json() or {}).get("results") or []


def _bocha_search(query: str) -> Optional[List[Dict]]:
    resp = httpx.post(
        "https://api.bochaai.com/v1/web-search",
        headers={"Authorization": f"Bearer {WEBSEARCH_API_KEY}"},
        json={"query": query, "count": WEBSEARCH_MAX_RESULTS, "summary": True},
        timeout=WEBSEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    pages = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
    return [
        {"title": p.get("name"), "url": p.get("url"), "content": p.get("snippet")}
        for p in pages
    ]


def _custom_search(query: str) -> Optional[List[Dict]]:
    resp = httpx.post(
        WEBSEARCH_ENDPOINT,
        json={"query": query, "max_results": WEBSEARCH_MAX_RESULTS, "api_key": WEBSEARCH_API_KEY},
        timeout=WEBSEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return (resp.json() or {}).get("results") or []


PROVIDERS = {
    "tavily": _tavily_search,
    "bocha": _bocha_search,
    "custom": _custom_search,
}


def search_web(query: str, max_results: int = 0) -> Dict:
    """联网检索；未配置或失败时返回降级结果（永不向调用方抛异常）。"""
    query = (query or "").strip()
    if not query:
        return _degraded(query, "请输入检索关键词")
    if not is_configured():
        return _degraded(query)

    provider = (WEBSEARCH_PROVIDER or "").strip().lower()
    handler = PROVIDERS.get(provider)
    if not handler:
        return _degraded(query, f"暂不支持的联网检索服务：{provider}")

    try:
        raw_items = handler(query) or []
        results = _normalize(raw_items, provider)
        if not results:
            return _degraded(query, f"联网检索（{provider}）未返回结果，可参考以下官方渠道。")
        return {
            "query": query,
            "engine": provider,
            "degraded": False,
            "message": "本地知识库未命中，以下为联网检索结果（来自站外，请人工核实后引用）。",
            "results": results[: max_results or WEBSEARCH_MAX_RESULTS],
            "suggestions": _suggestions(query),
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("联网检索失败（provider=%s）：%s", provider, exc)
        return _degraded(query, f"联网检索服务暂时不可用（{exc}），可参考以下官方渠道。")
