"""数据库引擎与会话。SQLite 起步，SQLAlchemy 保持可迁移 PostgreSQL。"""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}  # PG 网络瞬断后自动重连接


settings = get_settings()
# 确保 sqlite 数据目录存在
if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _ensure_column(table: str, column: str, ddl: str) -> None:
    """幂等补列：兼容已建库（SQLite/PG 均支持 ADD COLUMN），新库跳过。"""
    insp = inspect(engine)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return
    if column not in cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
    # 轻量迁移：老库 users 表补 hospital 列（多机构可见性）
    _ensure_column("users", "hospital", "hospital VARCHAR(64) DEFAULT ''")
