"""数据库引擎与会话。"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # pool_pre_ping：取出连接前先探活，避免 MySQL wait_timeout 后拿到已断开的连接；
    # pool_recycle：定期重建连接，长连接场景（后台调度/采集）更稳。
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI 依赖：每次请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 旧库新增列的兼容表：SQLite 的 create_all 不会为已存在表补列，需显式 ALTER。
# 新增字段时在此登记，保证老数据库平滑升级、不丢数据。
_EXTRA_COLUMNS = {
    "documents": [
        ("doc_category", "VARCHAR(32) DEFAULT 'POLICY'"),
    ],
    "policy_blocks": [
        ("doc_category", "VARCHAR(32) DEFAULT 'POLICY'"),
    ],
}


def _ensure_columns() -> None:
    """为已存在的旧表补充新增列（幂等；PostgreSQL 由 Alembic 之类工具处理）。"""
    if not _is_sqlite:
        return
    with engine.connect() as conn:
        for table, columns in _EXTRA_COLUMNS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.commit()


def init_db() -> None:
    """建表（幂等）+ 旧库补列迁移。"""
    from app.db import models  # noqa: F401  注册全部模型

    Base.metadata.create_all(engine)
    _ensure_columns()
