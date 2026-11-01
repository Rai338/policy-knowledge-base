"""认证与角色（预置账号 + USER/ADMIN 角色权限）。

设计要点：
1. 口令使用 pbkdf2_hmac 加盐哈希存储（标准库实现，不引入 passlib/bcrypt 依赖），
   格式 "salt$hash"，校验用 hmac.compare_digest 防计时攻击。
2. 登录令牌为 HMAC-SHA256 签名的无状态 token（username.exp.signature），
   不依赖服务端会话存储，重启后依然有效；过期由 exp 时间戳控制。
3. 角色仅两级：USER（简洁检索/问答/解读）与 ADMIN（含后台增删改查）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import (
    AUTH_SECRET,
    AUTH_TOKEN_TTL_HOURS,
    DEFAULT_ADMIN,
    DEFAULT_USER,
)
from app.core.logging import logger
from app.db.models import User

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"

ROLES: Dict[str, str] = {
    ROLE_USER: "普通用户",
    ROLE_ADMIN: "管理员",
}

# 迭代次数（兼顾安全与响应速度；生产可上调）
_PBKDF2_ROUNDS = 100_000


# ---------------------------------------------------------------- 口令哈希
def hash_password(password: str) -> str:
    """生成加盐哈希，格式 salt$hash。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验口令（旧格式或无盐数据直接判失败）。"""
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    calc = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    )
    return hmac.compare_digest(calc.hex(), digest)


# ---------------------------------------------------------------- 令牌
def _sign(payload: str) -> str:
    return hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(username: str) -> str:
    """签发令牌：username.过期时间戳.签名。"""
    exp = int((dt.datetime.now() + dt.timedelta(hours=AUTH_TOKEN_TTL_HOURS)).timestamp())
    payload = f"{username}.{exp}"
    return f"{payload}.{_sign(payload)}"


def parse_token(token: str) -> Optional[str]:
    """校验令牌，返回用户名；无效/过期返回 None。"""
    if not token or token.count(".") != 2:
        return None
    username, exp, signature = token.split(".", 2)
    if not hmac.compare_digest(_sign(f"{username}.{exp}"), signature):
        return None
    try:
        if int(exp) < int(dt.datetime.now().timestamp()):
            return None
    except (TypeError, ValueError):
        return None
    return username


# ---------------------------------------------------------------- 用户
def get_user(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def user_to_dict(user: User) -> Dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "role_name": ROLES.get(user.role, user.role),
        "status": user.status,
        "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if user.last_login_at else "",
    }


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    """校验账号口令；成功则更新最后登录时间并返回用户。"""
    user = get_user(db, (username or "").strip())
    if not user or user.status != "ACTIVE":
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    user.last_login_at = dt.datetime.now()
    db.commit()
    return user


def register_user(db: Session, username: str, password: str,
                  display_name: str = "", role: str = ROLE_USER) -> User:
    """注册新用户（默认普通用户；注册接口不允许自提管理员）。"""
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    if get_user(db, username):
        raise ValueError("该用户名已存在")
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name or username,
        role=role if role in ROLES else ROLE_USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_default_users(db: Session) -> int:
    """播种预置账号（仅当不存在时创建），返回新建数量。"""
    created = 0
    for preset, role in ((DEFAULT_ADMIN, ROLE_ADMIN), (DEFAULT_USER, ROLE_USER)):
        if get_user(db, preset["username"]):
            continue
        db.add(
            User(
                username=preset["username"],
                password_hash=hash_password(preset["password"]),
                display_name=preset["display_name"],
                role=role,
            )
        )
        created += 1
    if created:
        db.commit()
        logger.info("已播种预置账号 %d 个（admin/user）", created)
    return created
