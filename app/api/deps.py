"""认证依赖：从 Authorization 头解析令牌，注入当前用户与角色校验。"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY
from app.core.security import decode_token
from app.db.database import get_db
from app.db.models import User


def get_current_user(
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    payload = decode_token(token, SECRET_KEY) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return user


def require_user(user: User = Depends(get_current_user)) -> User:
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
