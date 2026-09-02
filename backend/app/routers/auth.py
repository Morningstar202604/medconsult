"""认证路由：登录 / 创建用户(admin) / 当前用户。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser, write_audit
from ..schemas import LoginRequest, UserCreate
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(body: LoginRequest, db: DbDep):
    user = db.scalar(select(models.User).where(models.User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被停用")
    token = create_access_token(user.id, user.role.value, user.username)
    write_audit(db, user, "auth.login", "user", str(user.id))
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "username": user.username,
                     "full_name": user.full_name, "role": user.role.value}}


@router.get("/auth/me")
def me(user: CurrentUser):
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
            "role": user.role.value}


@router.post("/auth/register")
def register(body: UserCreate, db: DbDep, admin: CurrentUser):
    if admin.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可创建账号")
    if body.role not in ("admin", "chief", "doctor"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法角色")
    exists = db.scalar(select(models.User).where(models.User.username == body.username))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    u = models.User(username=body.username,
                    password_hash=hash_password(body.password),
                    full_name=body.full_name,
                    role=models.Role(body.role))
    db.add(u)
    db.commit()
    db.refresh(u)
    write_audit(db, admin, "user.create", "user", str(u.id), body.username)
    return {"id": u.id, "username": u.username, "role": u.role.value}
