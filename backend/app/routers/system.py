"""系统信息路由：数据库状态、版本、配置摘要等运维端点（需登录）。"""
from fastapi import APIRouter
from sqlalchemy import inspect, text

from ..config import get_settings
from ..db import engine
from ..deps import CurrentUser

router = APIRouter(tags=["system"])
settings = get_settings()


@router.get("/db/info")
def get_db_info(user: CurrentUser):
    """返回数据库连接信息、表数量、存储路径等（SQLAlchemy 通用，兼容 SQLite/PostgreSQL）。"""
    insp = inspect(engine)
    tables = insp.get_table_names()
    table_counts = {}
    for t in tables:
        try:
            with engine.connect() as conn:
                table_counts[t] = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() or 0
        except Exception:
            table_counts[t] = -1

    return {
        "database": engine.dialect.name,
        "tables": table_counts,
        "table_count": len(tables),
        "version": settings.app_name,
        "debug": settings.debug,
    }
