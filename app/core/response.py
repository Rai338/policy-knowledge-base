"""统一响应封装与异常处理。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def ok(data: Any = None, message: str = "success", **extra) -> dict:
    payload = {"code": 0, "message": message, "data": data}
    payload.update(extra)
    return payload


def fail(message: str, code: int = 1, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}


def paged(items: list, total: int, page: int, page_size: int, message: str = "success") -> dict:
    return {
        "code": 0,
        "message": message,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
    }


class BizException(Exception):
    """业务异常：直接以 code/message 形式返回前端。"""

    def __init__(self, message: str, code: int = 1, status_code: int = 200):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizException)
    async def _biz_handler(request: Request, exc: BizException):
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.message, exc.code),
        )

    @app.exception_handler(Exception)
    async def _server_handler(request: Request, exc: Exception):
        # 兜底：避免前端拿到 HTML 500 页面，统一为可解析的失败提示
        return JSONResponse(status_code=500, content=fail(f"服务端异常：{exc}"))
