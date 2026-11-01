"""本地启动入口：python run.py [--host 127.0.0.1] [--port 8000]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app.core.config import HOST, PORT  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="政策知识库 服务启动")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true", help="开发模式（代码变更自动重启）")
    args = parser.parse_args()
    print(f"启动服务：http://{args.host}:{args.port}")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
