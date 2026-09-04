"""认证路由：登录（防爆破锁定） / 创建用户(admin) / 当前用户。"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import models
from ..config import get_settings
from ..deps import DbDep
from ..deps import CurrentUser, write_audit
from ..ops import get_login_lock
from ..schemas import LoginRequest, UserCreate
from ..security import (create_access_token, hash_password,
                        validate_password_strength, verify_password)

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, db: DbDep):
    ip = request.client.host if request.client else "-"
    lock = get_login_lock()
    if lock.is_locked(f"u:{body.username}") or lock.is_locked(f"ip:{ip}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "失败次数过多，账号已临时锁定，请稍后再试")
    user = db.scalar(select(models.User).where(models.User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        lock.fail(f"u:{body.username}")
        lock.fail(f"ip:{ip}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被停用")
    lock.clear(f"u:{body.username}")
    lock.clear(f"ip:{ip}")
    token = create_access_token(user.id, user.role.value, user.username)
    write_audit(db, user, "auth.login", "user", str(user.id))
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "username": user.username,
                     "full_name": user.full_name, "role": user.role.value}}


@router.get("/auth/me")
def me(user: CurrentUser):
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
            "role": user.role.value, "hospital": user.hospital}


@router.post("/auth/register")
def register(body: UserCreate, db: DbDep, admin: CurrentUser):
    if admin.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可创建账号")
    if body.role not in ("admin", "chief", "doctor"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法角色")
    ok, reason = validate_password_strength(body.password, get_settings().password_min_length)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)
    exists = db.scalar(select(models.User).where(models.User.username == body.username))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    u = models.User(username=body.username,
                    password_hash=hash_password(body.password),
                    full_name=body.full_name,
                    role=models.Role(body.role),
                    hospital=(body.hospital or "").strip())
    db.add(u)
    db.commit()
    db.refresh(u)
    write_audit(db, admin, "user.create", "user", str(u.id), body.username)
    return {"id": u.id, "username": u.username, "role": u.role.value}
