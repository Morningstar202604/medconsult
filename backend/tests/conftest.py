"""测试配置：使用独立临时数据库，避免污染开发数据。"""
import os
import tempfile

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("SEED_ADMIN_PASSWORD", "TestPass123!")
os.environ.setdefault("ALLOW_SANDBOX_WITHOUT_LLM", "true")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "TestPass123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}
