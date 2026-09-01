"""生产模式多智能体链路集成测试（核心回归）：
使用本地 mock OpenAI 服务模拟真实 LLM，验证完整调用链真正跑通——
摘要(1) → 8 专科第一轮并发 → 8 专科第二轮并发 → 主持人 JSON 报告。
并验证"多智能体"为真实独立调用（每个专科一次独立 LLM 请求），非单模型换提示词。
"""
import os
import tempfile
import threading
import time
import urllib.request

import pytest

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from tests.mock_llm_server import CALLS  # noqa: E402


@pytest.fixture(scope="module")
def mock_llm_env():
    """为生产链路测试单独注入 mock LLM 配置，并重置 settings 缓存，
    避免污染其他测试文件（test_api 依赖"未配置 LLM"环境）。"""
    import tempfile
    from app.config import get_settings
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/mdt.db"
    os.environ["DEBUG"] = "true"
    os.environ["SEED_ADMIN_USERNAME"] = "admin"
    os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"
    os.environ["LLM_API_KEY"] = "mock-key"
    os.environ["LLM_BASE_URL"] = "http://127.0.0.1:8513/v1"
    os.environ["LLM_DEFAULT_MODEL"] = "mock-model"
    os.environ["ALLOW_SANDBOX_WITHOUT_LLM"] = "true"
    get_settings.cache_clear()
    yield
    # 清理，避免影响后续模块
    for k in ("DATABASE_URL", "DEBUG", "SEED_ADMIN_USERNAME", "SEED_ADMIN_PASSWORD",
              "LLM_API_KEY", "LLM_BASE_URL", "LLM_DEFAULT_MODEL", "ALLOW_SANDBOX_WITHOUT_LLM"):
        os.environ.pop(k, None)
    get_settings.cache_clear()


def _wait_up(port: int, timeout: float = 30.0) -> None:
    """TCP 探测端口就绪（避免 HTTP 422 被误判为失败）。"""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("mock LLM server 未启动")


@pytest.fixture(scope="module")
def mock_server(mock_llm_env):
    import uvicorn
    from tests.mock_llm_server import app as mock_app

    config = uvicorn.Config(mock_app, host="127.0.0.1", port=8513, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    _wait_up(8513)
    yield server
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="module")
def client(mock_llm_env):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client, mock_llm_env):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "TestPass123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_production_mdt_full_chain(mock_server, client, token):
    """生产模式完整链路：多专科两轮 + 主持人报告，全部真实 LLM 调用。"""
    CALLS.clear()
    r = client.post("/api/consultations", headers=_auth(token), json={
        "mode": "production",
        "text": "患者男 45 岁，发热咳嗽 3 天，无呼吸困难。",
        "specialties": ["internal", "surgery", "pharmacy", "labimaging",
                        "neurology", "cardio", "pediatrics", "obgyn"],
        "rounds": 2,
        "style": "evidence",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "completed"
    assert d["is_demo"] is False          # 生产模式绝不冒充沙箱
    assert d["report"]["final_diagnosis"] == "社区获得性肺炎（CAP）"  # 主持人 JSON 被解析

    # 事件流：triage → summary → 8专科×2轮 → report
    roles = [e["role"] for e in d["events"]]
    assert "triage" in roles
    assert roles.count("summary") == 1
    assert roles.count("specialist") == 16   # 8 专科 × 2 轮
    assert "report" in roles
    r1 = [e for e in d["events"] if e["role"] == "specialist" and e["round"] == 1]
    r2 = [e for e in d["events"] if e["role"] == "specialist" and e["round"] == 2]
    assert len(r1) == 8 and len(r2) == 8

    # LLM 真实调用次数：1 摘要 + 16 专科 + 1 主持人 = 18（可含重试，≥18）
    assert len(CALLS) >= 18, f"LLM 调用次数不足：{len(CALLS)}"
    # 验证 8 个专科各有独立调用（非单模型换皮）
    spec_systems = [c["system"] for c in CALLS if "你是会诊中的" in c["system"]]
    names = set()
    for s in spec_systems:
        for n in ("内科专家", "外科专家", "药学专家", "影像与检验专家",
                  "神经内科专家", "心内科专家", "儿科专家", "妇产科专家"):
            if n in s:
                names.add(n)
    assert len(names) == 8, f"专科角色不齐：{names}"
    # 主持人 JSON 校验通过
    assert any("会诊共识报告" in c["user"] for c in CALLS)


def test_production_followup_uses_llm(mock_server, client, token):
    """报告追问走真实模型。"""
    CALLS.clear()
    r = client.post("/api/consultations", headers=_auth(token), json={
        "mode": "production",
        "text": "患者女 30 岁，咽痛低热 2 天。",
        "specialties": ["internal"],
        "rounds": 1,
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    CALLS.clear()
    r = client.post(f"/api/consultations/{cid}/followup", headers=_auth(token), json={
        "consultation_id": cid, "text": "还需要做什么检查确认？",
    })
    assert r.status_code == 200, r.text
    assert "肺炎" in r.json()["reply"]
    assert len(CALLS) >= 1


def test_production_context_injection(mock_server, client, token):
    """RAG 检索 / 技能包 / 已审核反馈 三类上下文真实注入到模型请求中。"""
    from app.rag import clear, remove_doc
    clear()

    # 1) 上传文档 → 建 RAG 索引
    r = client.post("/api/library/upload", headers=_auth(token),
                    files={"files": ("肺炎指南.txt",
                                     "社区获得性肺炎：完善血常规、CRP、PCT 与胸部影像。".encode("utf-8"),
                                     "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["id"] > 0

    # 2) 创建技能包（admin 可建）
    r = client.post("/api/skills", headers=_auth(token), json={
        "name": "感染会诊", "desc": "感染专科审查要求",
        "prompt": "注意鉴别病毒性与细菌性感染，关注 PCT/CRP 动态趋势。"})
    assert r.status_code == 200, r.text
    skill_id = r.json()["id"]

    # 3) 提交反馈并让管理员（兼主任权限）审核通过
    r = client.post("/api/feedback", headers=_auth(token), json={
        "consultation_id": None, "title": "CAP 经验",
        "diagnosis": "CAP 需动态复查 CRP/PCT", "helpful": True, "note": "48h 后评估疗效"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    r = client.post(f"/api/feedback/{fid}/review", headers=_auth(token),
                    json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    # 4) 发起生产会诊：文本含"肌钙蛋白"关键词命中 RAG 文档、带技能包
    CALLS.clear()
    r = client.post("/api/consultations", headers=_auth(token), json={
        "mode": "production",
        "text": "患者男 50 岁发热咳嗽，查血常规 CRP 升高，建议按社区获得性肺炎处理。",
        "specialties": ["internal", "pharmacy"],
        "rounds": 1,
        "skills": [skill_id],
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    # 5) 断言三类上下文都进入了模型请求
    joined_user = "\n".join(c["user"] for c in CALLS)
    joined_system = "\n".join(c["system"] for c in CALLS)
    assert "不可信数据引用" in joined_user, "RAG/经验引用未包裹隔离"
    assert "社区获得性肺炎" in joined_user, "RAG 检索片段未注入"
    assert "会诊技能:感染会诊" in joined_system, "技能包未注入 system"
    assert "本院已审核经验" in joined_user, "已审核反馈未注入"
    assert "CRP/PCT" in joined_user, "已审核反馈内容缺失"
    # 防注入护栏：不可信块在引用分隔符内，且出现在数据引用块中
    assert joined_user.count("不可信数据引用") >= 2  # 开 + 闭（或多次）

    # 清理索引，避免污染其他测试
    remove_doc("肺炎指南.txt")
