"""全局配置与常量（集中管理：路径、端口、模型参数、检索阈值、主题色等）。

所有魔法数字与开关集中在此处，便于扩展维护。
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- 路径
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("PKB_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_DIR = DATA_DIR / "index"
LOG_DIR = DATA_DIR / "logs"
EXPORT_DIR = DATA_DIR / "exports"
SAMPLE_DIR = BASE_DIR / "samples"
WEB_DIR = BASE_DIR / "web"

for _d in (DATA_DIR, UPLOAD_DIR, INDEX_DIR, LOG_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 服务
APP_NAME = "政策知识库"
APP_VERSION = "0.1.0"
# 前端构建号：index.html 内联声明，页面启动时与 /api/meta/theme 返回值比对，
# 不一致说明浏览器仍在用缓存的旧页面/旧脚本 → 自动带时间戳重载，实现"自愈"。
# 每次发版改这里（并与 web/index.html 的 window.PKB_BUILD 保持一致）。
BUILD_ID = "20260930a"
API_PREFIX = "/api"
HOST = os.getenv("PKB_HOST", "127.0.0.1")
PORT = int(os.getenv("PKB_PORT", "8000"))

# ---------------------------------------------------------------- 认证与角色
# 登录令牌签名密钥（生产环境务必通过环境变量覆盖）
AUTH_SECRET = os.getenv("PKB_AUTH_SECRET", "policy-kb-demo-secret-change-me")
# 登录令牌有效时长（小时）
AUTH_TOKEN_TTL_HOURS = int(os.getenv("PKB_AUTH_TTL_HOURS", "12"))
# 预置账号（仅首次启动播种；之后以库内为准，可在管理端改密）
DEFAULT_ADMIN = {"username": os.getenv("PKB_ADMIN_USER", "admin"),
                 "password": os.getenv("PKB_ADMIN_PASS", "admin123"),
                 "display_name": "系统管理员"}
DEFAULT_USER = {"username": os.getenv("PKB_USER_USER", "user"),
                "password": os.getenv("PKB_USER_PASS", "user123"),
                "display_name": "普通用户"}

# ---------------------------------------------------------------- 数据库
# 默认使用本地 SQLite（零配置、无需网络、启动最快，演示最稳）。
# 切教师机 MySQL（数据已同步，用于展示关系型数据库）：
#   PKB_DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/policy_kb?charset=utf8mb4
# 或直接双击项目根目录的「启动-教师机MySQL.bat」。
# 切 PostgreSQL：PKB_DATABASE_URL=postgresql+psycopg2://user:pwd@host:5432/policy_kb
DATABASE_URL = os.getenv(
    "PKB_DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'policy_kb.db'}",
)

# ---------------------------------------------------------------- 大模型（DeepSeek）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("PKB_LLM_TEMPERATURE", "0.2"))
LLM_TIMEOUT = float(os.getenv("PKB_LLM_TIMEOUT", "60"))
LLM_MAX_TOKENS = int(os.getenv("PKB_LLM_MAX_TOKENS", "1600"))

# ---------------------------------------------------------------- 认证（AUTH）
# HMAC 签名令牌的密钥；生产必须通过环境变量覆盖，使用默认值仅用于本地演示
SECRET_KEY = os.getenv("PKB_SECRET_KEY", "dev-insecure-change-me")
TOKEN_EXPIRE_HOURS = int(os.getenv("PKB_TOKEN_EXPIRE_HOURS", "24"))
# 首次启动时若无任何管理员，自动创建该默认账号（请在首次登录后修改密码）
ADMIN_USERNAME = os.getenv("PKB_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("PKB_ADMIN_PASSWORD", "admin123")
# 演示用普通用户（登录页「普通用户」角色快速入口的一键登录账号）
DEMO_USERNAME = os.getenv("PKB_DEMO_USERNAME", "user")
DEMO_PASSWORD = os.getenv("PKB_DEMO_PASSWORD", "user123")

# ---------------------------------------------------------------- 向量/检索
# hash: 离线可用（特征哈希）；bge3: 本地 BGE-M3；openai: 兼容 OpenAI 的 embedding 接口
EMBEDDING_BACKEND = os.getenv("PKB_EMBEDDING_BACKEND", "hash")
EMBEDDING_MODEL = os.getenv("PKB_EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("PKB_EMBEDDING_DIM", "512"))
VECTOR_BACKEND = os.getenv("PKB_VECTOR_BACKEND", "auto")  # auto | faiss | numpy | milvus
RERANK_BACKEND = os.getenv("PKB_RERANK_BACKEND", "heuristic")  # heuristic | bge-reranker

TOP_K_RECALL = int(os.getenv("PKB_TOP_K_RECALL", "20"))   # 混合检索召回候选
TOP_K_RERANK = int(os.getenv("PKB_TOP_K_RERANK", "5"))    # 重排后返回条数
BM25_WEIGHT = float(os.getenv("PKB_BM25_WEIGHT", "0.5"))  # BM25 融合权重
VECTOR_WEIGHT = float(os.getenv("PKB_VECTOR_WEIGHT", "0.5"))
RRF_K = int(os.getenv("PKB_RRF_K", "60"))                 # RRF 平滑因子
MIN_RELEVANCE_SCORE = float(os.getenv("PKB_MIN_SCORE", "0.08"))  # 低于该分数判定证据不足
# 语义相似度下限：低于此值且不伴关键词命中时，视为"未真正命中"
# （防止任何查询都因静态加权而返回一堆弱相关结果，导致联网兜底永不触发）
# 默认 0.18：hash 向量下真实查询多由关键词命中承载，纯语义 0.10~0.15 多为噪声；
# 接入 BGE-M3 等真实向量模型后，相关文本余弦相似度普遍 >0.3，该阈值同样适用。
MIN_SEMANTIC_SCORE = float(os.getenv("PKB_MIN_SEMANTIC", "0.18"))
MAX_CONTEXT_CHARS = int(os.getenv("PKB_MAX_CONTEXT_CHARS", "6000"))

# ---------------------------------------------------------------- 切块
MAX_BLOCK_CHARS = int(os.getenv("PKB_MAX_BLOCK_CHARS", "500"))  # 超过则按"款"细分
MIN_BLOCK_CHARS = int(os.getenv("PKB_MIN_BLOCK_CHARS", "12"))

# ---------------------------------------------------------------- 采集
CRAWL_ENABLED = os.getenv("PKB_CRAWL_ENABLED", "true").lower() == "true"
CRAWL_USER_AGENT = os.getenv(
    "PKB_CRAWL_USER_AGENT",
    "PolicyKB-Crawler/0.1 (+education-demo; contact: team@example.com)",
)
CRAWL_TIMEOUT = float(os.getenv("PKB_CRAWL_TIMEOUT", "20"))
CRAWL_MAX_PAGES = int(os.getenv("PKB_CRAWL_MAX_PAGES", "3"))
CRAWL_LIST_LIMIT = int(os.getenv("PKB_CRAWL_LIST_LIMIT", "30"))  # 列表页取前 N 条比对
SIMHASH_DISTANCE_THRESHOLD = int(os.getenv("PKB_SIMHASH_DISTANCE", "3"))

# ---------------------------------------------------------------- 联网检索兜底
# 本地知识库检索不到时，自动转为联网检索补充（RET-007）。
# 采用可插拔 provider：配置 PKB_WEBSEARCH_PROVIDER + PKB_WEBSEARCH_API_KEY 即启用真实联网；
# 未配置时优雅降级为"检索建议 + 候选官方渠道"，不报错、不影响演示。
WEBSEARCH_ENABLED = os.getenv("PKB_WEBSEARCH_ENABLED", "true").lower() == "true"
# 支持：tavily | bocha | custom（custom 需配合 PKB_WEBSEARCH_ENDPOINT）
WEBSEARCH_PROVIDER = os.getenv("PKB_WEBSEARCH_PROVIDER", "")
WEBSEARCH_API_KEY = os.getenv("PKB_WEBSEARCH_API_KEY", "")
WEBSEARCH_ENDPOINT = os.getenv("PKB_WEBSEARCH_ENDPOINT", "")
WEBSEARCH_TIMEOUT = float(os.getenv("PKB_WEBSEARCH_TIMEOUT", "15"))
WEBSEARCH_MAX_RESULTS = int(os.getenv("PKB_WEBSEARCH_MAX_RESULTS", "5"))

# ---------------------------------------------------------------- 任务
MAX_CONFLICT_WORKERS = int(os.getenv("PKB_CONFLICT_WORKERS", "2"))
CONFLICT_PAIR_LIMIT = int(os.getenv("PKB_CONFLICT_PAIR_LIMIT", "80"))

# ---------------------------------------------------------------- 分页
DEFAULT_PAGE_SIZE = int(os.getenv("PKB_PAGE_SIZE", "10"))
MAX_PAGE_SIZE = 100

# ---------------------------------------------------------------- 主题（前端同步使用）
THEME = {
    # 设计语言对齐 policy-workbench 原型：浅灰绿底 + 墨绿青品牌色 + 陶土橙强调色
    "primary": "#1E817B",
    "primaryLight": "#12625F",
    "primaryBg": "#E1E9E5",
    "bg": "#E9EFEC",
    "surface": "#F8FAF8",
    "textPrimary": "#18201F",
    "textSecondary": "#6D7C78",
    "border": "#C8D3CF",
    "ice": "#A9C8C4",
    "signal": "#C95C43",
    "success": "#2E8B62",
    "warning": "#C2872F",
    "danger": "#B8492F",
    "info": "#5A7F94",
    "radiusSm": "6px",
    "radiusMd": "8px",
    "radiusLg": "10px",
    "shadowSm": "0 1px 0 rgba(24,32,31,0.04)",
    "shadowMd": "0 6px 18px rgba(24,32,31,0.08)",
    "shadowLg": "0 14px 34px rgba(24,32,31,0.14)",
}

# ---------------------------------------------------------------- 支持的文件类型
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
MAX_UPLOAD_MB = 50


def theme_css_vars() -> str:
    """把主题常量导出为 CSS 变量（前端可直接消费，保证一处定义两处生效）。"""
    mapping = {
        "primary": "--color-primary",
        "primaryLight": "--color-primary-light",
        "primaryBg": "--color-primary-bg",
        "bg": "--color-bg",
        "surface": "--color-surface",
        "textPrimary": "--color-text-primary",
        "textSecondary": "--color-text-secondary",
        "border": "--color-border",
        "ice": "--color-ice",
        "signal": "--color-signal",
        "success": "--color-success",
        "warning": "--color-warning",
        "danger": "--color-danger",
        "info": "--color-info",
        "radiusSm": "--radius-sm",
        "radiusMd": "--radius-md",
        "radiusLg": "--radius-lg",
        "shadowSm": "--shadow-sm",
        "shadowMd": "--shadow-md",
        "shadowLg": "--shadow-lg",
    }
    return "\n".join(f"  {css}: {THEME[key]};" for key, css in mapping.items())
