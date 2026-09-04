"""用户管理与审计日志路由（仅管理员/主任）。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser
from ..schemas import UserUpdate
from ..security import hash_password

router = APIRouter(tags=["admin"])


@router.get("/users")
def list_users(db: DbDep, user: CurrentUser):
    if user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可查看用户")
    rows = db.scalars(select(models.User).order_by(models.User.id)).all()
    return {"items": [{"id": u.id, "username": u.username, "full_name": u.full_name,
                       "role": u.role.value, "hospital": u.hospital,
                       "is_active": u.is_active,
                       "created_at": u.created_at.isoformat() if u.created_at else None}
                      for u in rows]}


@router.post("/users/{uid}/reset-password")
def reset_password(uid: int, db: DbDep, user: CurrentUser, new_password: str = ""):
    if user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可重置密码")
    if len(new_password) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "密码至少 6 位")
    target = db.get(models.User, uid)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    target.password_hash = hash_password(new_password)
    db.commit()
    return {"ok": True}


@router.post("/users/{uid}/update")
def update_user(uid: int, body: UserUpdate, db: DbDep, user: CurrentUser):
    if user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可修改用户")
    target = db.get(models.User, uid)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if body.is_active is not None:
        target.is_active = body.is_active
    if body.full_name is not None:
        target.full_name = body.full_name
    if body.hospital is not None:
        target.hospital = body.hospital.strip()
    db.commit()
    return {"ok": True}


@router.get("/audit")
def list_audit(db: DbDep, user: CurrentUser, limit: int = 200):
    if user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可查看审计日志")
    rows = db.scalars(select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(limit)).all()
    return {"items": [{"id": a.id, "user_id": a.user_id, "action": a.action,
                       "resource_type": a.resource_type, "resource_id": a.resource_id,
                       "detail": a.detail, "ip": a.ip,
                       "created_at": a.created_at.isoformat() if a.created_at else None}
                      for a in rows]}
