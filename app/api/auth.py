"""认证接口（登录 / 注册 / 当前用户 / 管理员校验）。

前端登录后保存 token，请求管理端接口时在 Authorization 头携带：Bearer <token>。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.response import BizException, ok
from app.db.database import get_db
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginPayload(BaseModel):
    username: str
    password: str


class RegisterPayload(BaseModel):
    username: str
    password: str
    display_name: str = ""


def _extract_token(authorization: str) -> str:
    """从 Authorization 头提取令牌，兼容 Bearer 前缀。"""
    if not authorization:
        return ""
    token = authorization.strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def get_current_user(db: Session = Depends(get_db), authorization: str = Header("")):
    """当前登录用户；未登录或令牌失效时抛 401。"""
    username = auth_service.parse_token(_extract_token(authorization))
    if not username:
        raise BizException("未登录或登录已过期，请重新登录", status_code=401)
    user = auth_service.get_user(db, username)
    if not user or user.status != "ACTIVE":
        raise BizException("账号不存在或已停用", status_code=401)
    return user


def require_admin(user=Depends(get_current_user)):
    """管理员权限校验（后台增删改查接口使用）。"""
    if user.role != auth_service.ROLE_ADMIN:
        raise BizException("该功能需要管理员权限", status_code=403)
    return user


@router.post("/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.username, payload.password)
    if not user:
        raise BizException("用户名或密码不正确", status_code=401)
    return ok(
        {
            "token": auth_service.create_token(user.username),
            "user": auth_service.user_to_dict(user),
        }
    )


@router.post("/register")
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    """注册新用户（固定为普通用户，防止自提管理员）。"""
    try:
        user = auth_service.register_user(
            db, payload.username, payload.password, payload.display_name
        )
    except ValueError as exc:
        raise BizException(str(exc))
    return ok({"user": auth_service.user_to_dict(user)})


@router.get("/me")
def me(user=Depends(get_current_user)):
    return ok({"user": auth_service.user_to_dict(user)})


@router.get("/roles")
def roles():
    """角色字典（前端展示用）。"""
    return ok({"roles": auth_service.ROLES})
