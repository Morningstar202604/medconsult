"""FastAPI 主入口：启动初始化（管理员种子/技能/参考库）、路由注册、鉴权全局保护。"""
from contextlib import asynccontextmanager
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select, text

from .config import get_settings
from .db import SessionLocal, init_db
from .ops import (
    SlidingWindowLimiter, current_trace_id,
    get_login_lock, metrics, new_trace_id, set_trace_id,
)
from .routers import (admin, agent, auth, consultations, feedback, intake,
                      knowledge, library, media, patients, system, tools)
from .security import hash_password

settings = get_settings()


def _configure_logging() -> None:
    """结构化日志：统一格式，trace_id 贯穿请求。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [trace=%(_trace_id)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
    logging.getLogger().addFilter(TraceIdFilter())


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record._trace_id = current_trace_id()
        return True


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
    _configure_logging()
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

# 全局限流器：登录端点更严格
_global_limiter = SlidingWindowLimiter(settings.api_rate_limit_per_minute or 10**9, 60)
_login_limiter = SlidingWindowLimiter(settings.login_rate_limit_per_minute, 60)
_login_lock = get_login_lock()


@app.middleware("http")
async def ops_middleware(request: Request, call_next):
    """追踪 ID + 限流 + 指标 + 结构化访问日志（一次中件完成）。"""
    tid = new_trace_id()
    set_trace_id(tid)
    start = time.perf_counter()
    ip = request.client.host if request.client else "-"
    path = request.url.path
    status = 500
    try:
        if path.startswith(settings.api_prefix):
            key = f"{ip}:{path.split('/')[2] if path.startswith(f'{settings.api_prefix}/') else ''}"
            # 登录端点单独限流，其余按 IP 全局限流
            if path.endswith("/auth/login"):
                if not _login_limiter.allow(f"login:{ip}"):
                    return JSONResponse(status_code=429, content={"detail": "登录尝试过于频繁，请稍后再试"})
            elif settings.api_rate_limit_per_minute and not _global_limiter.allow(f"api:{ip}"):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
        resp = await call_next(request)
        status = resp.status_code
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        metrics.observe(status, latency_ms)
        logging.getLogger("medconsult.access").info(
            "%s %s %s %d %.1fms", request.method, path, ip, status, latency_ms)
    resp.headers["X-Trace-Id"] = tid
    return resp


for r in (auth.router, agent.router, patients.router, consultations.router,
          intake.router, feedback.router, knowledge.router, library.router, media.router,
          admin.router, tools.router, system.router):
    app.include_router(r, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health")
def health():
    db_up = "unknown"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_up = "up"
    except Exception:
        db_up = "down"
    return {
        "ok": True,
        "app": settings.app_name,
        "db": db_up,
        "llm_configured": settings.llm_configured,
        "version": "1.0.0",
    }


@app.get(f"{settings.api_prefix}/metrics")
def metrics_endpoint():
    """Prometheus 文本指标，供采集器（k8s/独立 scraper）抓取。"""
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # 生产模式不要把内部细节抛给客户端；开发模式保留详情
    detail = str(exc) if settings.debug else "服务器内部错误"
    from fastapi.responses import JSONResponse
    from fastapi import status as st
    logging.getLogger("medconsult").exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=st.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": detail})
