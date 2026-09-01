"""API 集成测试：认证/RBAC、PHI 加密、沙箱会诊、反馈审核流。"""
from tests.conftest import auth


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200


def test_unauthorized_access_blocked(client):
    """致命点修复：未登录不能访问任何业务 API。"""
    for path in ("/api/patients", "/api/consultations", "/api/feedback", "/api/library"):
        r = client.get(path)
        assert r.status_code == 401, path


def test_login_and_me(client, admin_token):
    r = client.get("/api/auth/me", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_create_user_requires_admin(client, admin_token):
    # 无 token
    assert client.post("/api/auth/register", json={"username": "a", "password": "123456", "role": "doctor"}).status_code in (401, 403)
    # admin 创建 chief
    r = client.post("/api/auth/register", headers=auth(admin_token),
                    json={"username": "chief01", "password": "Chief123!", "full_name": "张主任", "role": "chief"})
    assert r.status_code == 200, r.text
    # 再创建医生
    r = client.post("/api/auth/register", headers=auth(admin_token),
                    json={"username": "doc01", "password": "Doc12345!", "full_name": "李医生", "role": "doctor"})
    assert r.status_code == 200


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_patient_phi_encrypted(client, admin_token):
    """PHI 落库必须加密：直接查表读不到明文。"""
    r = client.post("/api/patients", headers=auth(admin_token), json={
        "name": "测试患者张三", "gender": "男", "hospital_no": "H0001",
        "id_card": "440000199001011234", "phone": "13800000000"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # API 返回解密明文（有权限时）
    r = client.get(f"/api/patients/{pid}", headers=auth(admin_token))
    assert r.json()["name"] == "测试患者张三"

    # 直接查 DB：应为密文
    from app.db import SessionLocal
    from app import models
    db = SessionLocal()
    row = db.get(models.Patient, pid)
    assert row.name_enc is not None and "张三" not in row.name_enc, "PHI 必须以密文落库"
    db.close()


def test_sandbox_consultation_works_without_llm(client, admin_token):
    """沙箱模式无需 LLM，报告必须 is_demo=True。"""
    r = client.post("/api/consultations", headers=auth(admin_token), json={
        "mode": "sandbox",
        "text": "58岁男性，胸痛伴冷汗3小时，高血压病史",
        "specialties": ["internal", "cardio"],
        "style": "brief", "rounds": 1,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "sandbox"
    assert body["status"] == "completed"
    assert body["is_demo"] is True
    assert body["report"]["is_demo"] is True
    # 红旗应在事件里
    roles = [e["role"] for e in body["events"]]
    assert "triage" in roles


def test_production_without_llm_rejected(client, admin_token):
    """生产模式未配置 LLM 必须拒绝，绝不静默降级。"""
    r = client.post("/api/consultations", headers=auth(admin_token), json={
        "mode": "production",
        "text": "胸痛3小时",
    })
    assert r.status_code == 400
    assert "配置" in r.json()["detail"] or "LLM" in r.json()["detail"]


def test_feedback_requires_review_before_inject(client, admin_token):
    """致命点修复：反馈必须主任审核通过后才能进入可注入状态。"""
    # 医生提交反馈
    doc_token = _login(client, "doc01", "Doc12345!")
    r = client.post("/api/feedback", headers=auth(doc_token), json={
        "title": "胸痛会诊", "diagnosis": "ACS", "helpful": True, "note": "按指南处理"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert r.json()["status"] == "pending_review"

    # 医生不能审核
    r = client.post(f"/api/feedback/{fid}/review", headers=auth(doc_token), json={"approve": True})
    assert r.status_code == 403

    # 主任审核通过
    chief_token = _login(client, "chief01", "Chief123!")
    r = client.post(f"/api/feedback/{fid}/review", headers=auth(chief_token), json={"approve": True})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
