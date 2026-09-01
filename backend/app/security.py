"""安全：密码哈希（bcrypt）、JWT、PHI 字段加密（Fernet AES-GCM）。

PHI 加密策略：
- 开发/无显式 key 时：自动生成 key 并持久化到 data/.phi_key（仅限开发，明确警告）。
- 生产：必须通过 PHI_ENCRYPTION_KEY 显式提供，否则启动校验失败。
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_BASE = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE / "data"


# ---------------------------------------------------------------- password
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# -------------------------------------------------------------------- JWT
def create_access_token(user_id: int, role: str, username: str) -> str:
    s = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "username": username, "exp": expire}
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------- PHI encryption
_fernet = None
_key_cache: bytes | None = None


def _load_or_create_key() -> bytes:
    """返回 Fernet key bytes；生产无显式 key 时抛错。"""
    global _fernet, _key_cache
    if _fernet is not None and _key_cache is not None:
        return _key_cache
    s = get_settings()
    if s.phi_encryption_key:
        key = s.phi_encryption_key.encode("utf-8")
    else:
        keyfile = _DATA_DIR / ".phi_key"
        if keyfile.exists():
            key = keyfile.read_bytes()
        else:
            key = Fernet.generate_key()
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            keyfile.write_bytes(key)
            os.chmod(keyfile, 0o600)
    try:
        _fernet = Fernet(key)
        _key_cache = key
    except Exception:
        raise RuntimeError("PHI_ENCRYPTION_KEY 无效（必须为 URL-safe base64 32 字节）。")
    return key


def phi_encrypt(plain: str | None) -> str | None:
    if plain is None:
        return None
    f = Fernet(_load_or_create_key())
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def phi_decrypt(token: str | None) -> str | None:
    if token is None:
        return None
    f = Fernet(_load_or_create_key())
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[解密失败：数据损坏或密钥变更]"
