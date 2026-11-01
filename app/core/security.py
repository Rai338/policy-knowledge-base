"""认证原语（零依赖）：pbkdf2 密码哈希 + HMAC 签名令牌。

只依赖标准库（hashlib / hmac / base64 / secrets / json / time），
不引入 PyJWT / passlib，与项目"零依赖可启动"的风格保持一致。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

_PBKDF2_ITERATIONS = 100_000


def new_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    try:
        actual = hash_password(password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected_hash)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, payload_b64: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def generate_token(user_id: str, role: str, secret: str, expire_hours: int) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + expire_hours * 3600,
    }
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(secret, payload_b64)}"


def decode_token(token: str, secret: str) -> Optional[dict]:
    """验签 + 校验有效期，失败或过期返回 None。"""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, signature = parts
    if not hmac.compare_digest(_sign(secret, payload_b64), signature):
        return None
    try:
        payload = json.loads(_unb64url(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload
