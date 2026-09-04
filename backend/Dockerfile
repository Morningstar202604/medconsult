# 汇诊后端镜像
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 优先使用锁定文件保证可复现构建；无 lock 时回退 requirements.txt
# 注：requirements.lock 由本机 Python 3.14 生成，若镜像基础版本不同请在 3.11 环境重新生成
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 非 root 运行（等保/运维基线）
RUN useradd --create-home --uid 10001 meduser && mkdir -p /app/data && chown meduser:meduser /app/data
COPY --chown=meduser:meduser backend/app /app/app
USER meduser

# 挂载数据卷：数据库 + PHI 密钥
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
