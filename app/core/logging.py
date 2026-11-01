"""日志：同时输出到控制台与文件（LOG-001 要求操作留痕，留存 6 个月）。"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from app.core.config import LOG_DIR

LOG_FILE = LOG_DIR / "policy-kb.log"

_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = TimedRotatingFileHandler(
    LOG_FILE, when="D", interval=1, backupCount=180, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)


def get_logger(name: str = "policy-kb") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(_file_handler)
        logger.addHandler(_console_handler)
        logger.propagate = False
    return logger


logger = get_logger()
