"""账号管理接口（ADM-USER）：用户列表 / 新增 / 启停 / 改密 / 删除（管理员）。

与项目本地 User 模型（role + status + password_hash）保持一致，
不依赖 yj 遗留的 user_service（其引用了不存在的 salt 列，数据库层面不兼容）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.response import BizException, ok
from app.db.database import get_db
from app.db.models import User
from app.services import auth_service

router = APIRouter(prefix="/admin", tags=["账号管理"])

STATUS_NAMES = {"ACTIVE": "正常", "DISABLED": "已停用"}


def _to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "role_name": auth_service.ROLES.get(user.role, user.role),
        "status": user.status,
        "status_name": STATUS_NAMES.get(user.status, user.status),
        "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if user.last_login_at else "",
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
    }


class UserCreatePayload(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "USER"


class UserUpdatePayload(BaseModel):
    display_name: str = ""
    role: str = ""
    status: str = ""
    password: str = ""


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """账号列表（仅管理员可见）。"""
    users = db.query(User).order_by(User.created_at).all()
    return ok([_to_dict(u) for u in users])


@router.post("/users")
def create_user(payload: UserCreatePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """新增账号（管理员可指定角色，含 ADMIN）。"""
    username = (payload.username or "").strip()
    if not username or not payload.password:
        raise BizException("用户名与密码不能为空")
    if len(payload.password) < 6:
        raise BizException("密码至少 6 位")
    if payload.role not in ("USER", "ADMIN"):
        raise BizException("角色只能是 USER 或 ADMIN")
    if db.query(User).filter(User.username == username).first():
        raise BizException(f"用户名「{username}」已存在")
    new_user = User(
        username=username,
        password_hash=auth_service.hash_password(payload.password),
        display_name=payload.display_name.strip() or username,
        role=payload.role,
        status="ACTIVE",
    )
    db.add(new_user)
    db.commit()
    return ok(_to_dict(new_user), "已创建用户")


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdatePayload, db: Session = Depends(get_db),
               operator: User = Depends(require_admin)):
    """更新账号：显示名 / 角色 / 状态 / 可选改密。"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise BizException("用户不存在", status_code=404)
    if payload.display_name.strip():
        target.display_name = payload.display_name.strip()
    if payload.role:
        if payload.role not in ("USER", "ADMIN"):
            raise BizException("角色只能是 USER 或 ADMIN")
        # 不能把自己降级为非管理员，避免锁死
        if target.id == operator.id and payload.role != "ADMIN":
            raise BizException("不能取消自己的管理员角色")
        target.role = payload.role
    if payload.status:
        if payload.status not in ("ACTIVE", "DISABLED"):
            raise BizException("状态只能是 ACTIVE 或 DISABLED")
        if target.id == operator.id and payload.status == "DISABLED":
            raise BizException("不能停用当前登录账号")
        target.status = payload.status
    if payload.password:
        if len(payload.password) < 6:
            raise BizException("密码至少 6 位")
        target.password_hash = auth_service.hash_password(payload.password)
    db.commit()
    return ok(_to_dict(target), "已更新")


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    """删除账号（保护：不能删自己、不能删最后一个管理员）。"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise BizException("用户不存在", status_code=404)
    if target.id == operator.id:
        raise BizException("不能删除当前登录账号")
    if target.role == "ADMIN":
        admins = db.query(User).filter(User.role == "ADMIN", User.status == "ACTIVE").count()
        if admins <= 1:
            raise BizException("不能删除最后一个管理员")
    db.delete(target)
    db.commit()
    return ok(message=f"已删除用户「{target.username}」")
