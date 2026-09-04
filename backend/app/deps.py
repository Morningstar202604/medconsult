"""FastAPI 依赖：当前用户、角色校验、审计日志。"""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .db import get_db
from .security import decode_access_token

logger = logging.getLogger("medconsult")
_bearer = HTTPBearer(auto_error=False)

DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    payload = decode_access_token(creds.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效凭证")
    user = db.get(models.User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不可用")
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]


def require_roles(*roles: models.Role):
    def checker(user: CurrentUser) -> models.User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权限执行该操作")
        return user

    return checker


def write_audit(
    db: Session,
    user: models.User | None,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    detail: str = "",
    ip: str = "",
) -> None:
    try:
        db.add(models.AuditLog(
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail[:2000],
            ip=ip,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("审计日志写入失败", exc_info=True)


def client_ip(request: Request) -> str:
    """客户端真实 IP。仅当配置 behind_proxy=true（部署在受控反向代理后）才信任
    X-Forwarded-For；否则一律用直连地址，防止客户端伪造头绕过限流与规避审计。"""
    if get_settings().behind_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def data_scope(db: Session, user: models.User) -> list[int] | None:
    """数据可见性范围：返回允许查看的 user_id 列表；None 表示不限（全部）。

    企业交付的隐私基线（对患者 PHI 与会诊记录的最小化原则）：
    - 主任/管理员：全院可见（负责审核与质控）
    - 医生：默认仅自己创建的数据；配置了 hospital 时同机构同事数据可见（协作）
    """
    if user.role in (models.Role.ADMIN, models.Role.CHIEF):
        return None
    if user.hospital:
        rows = db.execute(
            select(models.User.id).where(models.User.hospital == user.hospital)
        ).scalars().all()
        return list(rows)
    return [user.id]


def scope_filter(scope: list[int] | None, owner_col):
    """把可见性范围转换为 SQLAlchemy where 条件（None=不过滤）。"""
    if scope is None:
        return None
    return owner_col.in_(scope)
