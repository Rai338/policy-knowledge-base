"""用户与账号管理（AUTH-001/002）：登录校验、用户 CRUD、默认管理员播种。"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import ADMIN_PASSWORD, ADMIN_USERNAME, DEMO_PASSWORD, DEMO_USERNAME
from app.core.logging import logger
from app.core.security import hash_password, new_salt, verify_password
from app.db.models import User


def _to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "role_name": "管理员" if user.role == "admin" else "普通用户",
        "display_name": user.display_name,
        "enabled": user.enabled,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
    }


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not user.enabled:
        return None
    if not verify_password(password, user.salt, user.password_hash):
        return None
    return user


def list_users(db: Session) -> List[dict]:
    users = db.query(User).order_by(User.created_at).all()
    return [_to_dict(u) for u in users]


def create_user(db: Session, username: str, password: str, role: str = "user",
                display_name: str = "") -> User:
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名与密码不能为空")
    if db.query(User).filter(User.username == username).first():
        raise ValueError(f"用户名「{username}」已存在")
    if role not in ("user", "admin"):
        raise ValueError("角色只能是 user 或 admin")
    salt = new_salt()
    user = User(
        username=username,
        password_hash=hash_password(password, salt),
        salt=salt,
        role=role,
        display_name=display_name or username,
        enabled=True,
    )
    db.add(user)
    db.commit()
    return user


def update_user(db: Session, user_id: str, *, display_name: str = "", role: str = "",
                enabled: Optional[bool] = None, password: str = "") -> Optional[User]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if display_name:
        user.display_name = display_name
    if role:
        if role not in ("user", "admin"):
            raise ValueError("角色只能是 user 或 admin")
        user.role = role
    if enabled is not None:
        user.enabled = bool(enabled)
    if password:
        user.salt = new_salt()
        user.password_hash = hash_password(password, user.salt)
    db.commit()
    return user


def delete_user(db: Session, user_id: str, current_user: User) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    if user.id == current_user.id:
        raise ValueError("不能删除当前登录账号")
    if user.role == "admin":
        admins = db.query(User).filter(User.role == "admin", User.enabled.is_(True)).count()
        if admins <= 1:
            raise ValueError("不能删除最后一个管理员")
    db.delete(user)
    db.commit()
    return True


def ensure_default_accounts(db: Session) -> None:
    """首次启动播种默认演示账号：一个管理员 + 一个普通用户（登录页角色快速入口使用）。"""
    if not db.query(User).filter(User.role == "admin").first():
        salt = new_salt()
        db.add(User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD, salt),
            salt=salt,
            role="admin",
            display_name="系统管理员",
            enabled=True,
        ))
        logger.warning("已创建默认管理员账号：%s（默认密码，请尽快修改）", ADMIN_USERNAME)
    if not db.query(User).filter(User.username == DEMO_USERNAME).first():
        salt = new_salt()
        db.add(User(
            username=DEMO_USERNAME,
            password_hash=hash_password(DEMO_PASSWORD, salt),
            salt=salt,
            role="user",
            display_name="演示用户",
            enabled=True,
        ))
        logger.warning("已创建默认演示用户账号：%s", DEMO_USERNAME)
    db.commit()
