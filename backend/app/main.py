"""FastAPI 主入口：启动初始化（管理员种子/技能/参考库）、路由注册、鉴权全局保护。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .routers import admin, auth, consultations, feedback, intake, knowledge, library, media, patients
from .security import hash_password

settings = get_settings()


def _seed() -> None:
    db = SessionLocal()
    try:
        from . import models  # noqa: F401

        # 管理员种子（首次启动）
        existing = db.scalar(select(models.User).where(models.User.username == settings.seed_admin_username))
        if existing is None:
            db.add(models.User(
                username=settings.seed_admin_username,
                password_hash=hash_password(settings.seed_admin_password),
                full_name="系统管理员",
                role=models.Role.ADMIN,
            ))
            db.commit()
        # 技能/参考库种子
        from .routers.knowledge import seed_if_empty
        seed_if_empty(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# 生产部署时前端同源部署即可；CORS 仅用于本地开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.debug and ["http://localhost:5173", "http://127.0.0.1:5173"] or [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, patients.router, consultations.router,
          intake.router, feedback.router, knowledge.router, library.router, media.router, admin.router):
    app.include_router(r, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health")
def health():
    return {"ok": True, "app": settings.app_name}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # 生产模式不要把内部细节抛给客户端；开发模式保留详情
    detail = str(exc) if settings.debug else "服务器内部错误"
    from fastapi.responses import JSONResponse
    from fastapi import status as st
    return JSONResponse(status_code=st.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": detail})
