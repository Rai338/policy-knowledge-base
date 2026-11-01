"""知识库应用入口：注册路由、初始化数据与索引、启动采集调度、托管前端静态页面。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, analysis, auth, conflict, crawl, dashboard, documents, logs, qa, search, users
from app.core.config import API_PREFIX, APP_NAME, APP_VERSION, WEB_DIR
from app.core.logging import logger
from app.core.response import register_exception_handlers
from app.db.database import init_db
from app.services.indexer import load_index_from_db
from app.tasks.scheduler import scheduler

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="政策知识库：采集/导入 → 解析切块 → 混合检索 → 可追溯问答 → 解读关联 → 冲突初筛",
)

register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_NO_CACHE_TYPES = ("text/html", "text/css", "javascript")


@app.middleware("http")
async def disable_html_cache(request, call_next):
    """入口页与前端脚本一律禁用缓存。

    浏览器默认会对 index.html 做启发式缓存，导致改版后仍加载旧 index.html，
    而旧页面又引用旧版本号的 JS，最终表现为「改了却一直是旧页面」；
    更棘手的是旧脚本可能调用已变更的接口，表现为莫名其妙的 404。
    这里对 HTML/CSS/JS 一律加 no-store（本地演示场景，代价可忽略），
    确保浏览器拿到的始终是与后端一致的版本。
    """
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if any(t in content_type for t in _NO_CACHE_TYPES):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    from app.db.database import SessionLocal
    from app.db.models import Document
    from app.services.ingest_service import import_samples

    db = SessionLocal()
    try:
        # 播种预置账号（admin/user），保证 clone 后即可登录体验用户端与管理端
        try:
            from app.services.auth_service import ensure_default_users

            ensure_default_users(db)
        except Exception as exc:  # pragma: no cover
            logger.error("预置账号播种失败：%s", exc)
        # 空库时自动导入 samples/ 示例政策：保证 clone 后首次运行即有数据，
        # 且与开发者环境一致（向量用确定性 hash，跨机器结果可复现）
        if db.query(Document).count() == 0:
            logger.info("检测到空库，自动导入 samples/ 示例政策…")
            imported = import_samples(db)
            logger.info("自动导入完成：成功 %d 份", len(imported))
        stats = load_index_from_db(db)
        logger.info("启动完成：%s", stats)
        # 兜底校验：若导入后仍为 0，明确报错，避免“页面正常但无数据”的静默失败
        if db.query(Document).count() == 0:
            logger.error(
                "启动后文档数仍为 0：示例自动导入未生效。请确认："
                "① samples/ 目录存在且含 .txt 文件；② 依赖已安装（pip install -r requirements.txt）；"
                "③ 上方日志中是否有“示例文件 XXX 导入失败”的警告。"
            )
    finally:
        db.close()
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler.stop()


@app.get(f"{API_PREFIX}/health", tags=["系统"])
def health():
    return {"code": 0, "message": "ok", "data": {"name": APP_NAME, "version": APP_VERSION}}


app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(search.blocks_router, prefix=API_PREFIX)
app.include_router(qa.router, prefix=API_PREFIX)
app.include_router(analysis.router, prefix=API_PREFIX)
app.include_router(conflict.router, prefix=API_PREFIX)
app.include_router(crawl.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(logs.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(dashboard.meta_router, prefix=API_PREFIX)


# ---------------------------------------------------------------- 前端静态站点
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def main() -> None:
    import uvicorn

    from app.core.config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
