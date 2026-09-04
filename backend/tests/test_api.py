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
                    json={"username": "chief01", "password": "Chief@12345!", "full_name": "张主任", "role": "chief"})
    assert r.status_code == 200, r.text
    # 再创建医生
    r = client.post("/api/auth/register", headers=auth(admin_token),
                    json={"username": "doc01", "password": "Doc@12345!", "full_name": "李医生", "role": "doctor"})
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
    doc_token = _login(client, "doc01", "Doc@12345!")
    r = client.post("/api/feedback", headers=auth(doc_token), json={
        "title": "胸痛会诊", "diagnosis": "ACS", "helpful": True, "note": "按指南处理"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert r.json()["status"] == "pending_review"

    # 医生不能审核
    r = client.post(f"/api/feedback/{fid}/review", headers=auth(doc_token), json={"approve": True})
    assert r.status_code == 403

    # 主任审核通过
    chief_token = _login(client, "chief01", "Chief@12345!")
    r = client.post(f"/api/feedback/{fid}/review", headers=auth(chief_token), json={"approve": True})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def make_consult(client, token, text="咳嗽3天伴发热"):
    """沙箱会诊助手，返回 detail。"""
    return client.post("/api/consultations", headers=auth(token), json={
        "mode": "sandbox", "text": text, "specialties": ["internal", "cardio"],
        "style": "brief", "rounds": 1})


def test_consultation_stream_sse(client, admin_token):
    """会诊过程 SSE：包含过程事件回放 + report_chunk + done 收尾。"""
    r = make_consult(client, admin_token)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    with client.stream("GET", f"/api/consultations/{cid}/stream",
                       headers=auth(admin_token)) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(resp.iter_text())
    assert "event:" in body
    assert "report_chunk" in body
    assert "done" in body


def test_consultation_delete_permission(client, admin_token):
    """删除权限：他人不可删，创建者（admin）可删且级联清理。"""
    r = make_consult(client, admin_token)
    cid = r.json()["id"]
    # 无权限者（主任）不可删
    chief_token = _login(client, "chief01", "Chief@12345!")
    resp = client.delete(f"/api/consultations/{cid}", headers=auth(chief_token))
    assert resp.status_code == 403
    # 管理员可删
    resp = client.delete(f"/api/consultations/{cid}", headers=auth(admin_token))
    assert resp.status_code == 200
    assert client.get(f"/api/consultations/{cid}", headers=auth(admin_token)).status_code == 404


def test_agent_entry_routes_by_intent(client, admin_token):
    """Agent 统一入口：计算器意图直接执行，会诊意图走 MDT。"""
    r = client.post("/api/agent", headers=auth(admin_token), json={"text": "计算 BMI 25.5 分"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"]["intent"] == "calculator"
    assert body["action"] == "calculator"

    r = client.post("/api/agent", headers=auth(admin_token), json={
        "text": "58岁男性，胸痛伴冷汗3小时", "mode": "sandbox"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"]["intent"] == "consult"
    assert body["action"] == "consult"
    assert body["data"]["status"] == "completed"

    r = client.post("/api/agent", headers=auth(admin_token),
                    json={"text": "华法林和阿司匹林相互作用"})
    assert r.status_code == 200
    assert r.json()["action"] == "drug"


# ---------------------------------------------------------------- 企业交付合规
def test_phi_masked_for_doctor(client, admin_token):
    """隐私最小化：普通医生看不到完整身份证/手机号（脱敏），管理员可见完整。"""
    doc_token = _login(client, "doc01", "Doc@12345!")
    # 医生创建患者（在其可见范围内）
    r = client.post("/api/patients", headers=auth(doc_token), json={
        "name": "合规患者", "gender": "女", "hospital_no": "H2001",
        "id_card": "440000199001011234", "phone": "13800000000"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # 管理员：完整 PHI（可见性范围含该患者，created_by=doc01，doctor 数据 admin 全院可见）
    r = client.get(f"/api/patients/{pid}", headers=auth(admin_token))
    assert r.json()["id_card"] == "440000199001011234"
    assert r.json()["phone"] == "13800000000"

    # 普通医生：脱敏
    r = client.get(f"/api/patients/{pid}", headers=auth(doc_token))
    body = r.json()
    assert body["id_card"] != "440000199001011234"
    assert "***" in body["id_card"] and body["id_card"].endswith("1234")
    assert "****" in body["phone"] and body["phone"].endswith("0000")

    # 列表同样脱敏
    r = client.get("/api/patients", headers=auth(doc_token))
    item = next(x for x in r.json()["items"] if x["id"] == pid)
    assert "***" in item["id_card"]


def test_db_info_requires_auth(client):
    """运维信息端点必须登录后才能访问（防匿名泄露表清单/路径）。"""
    r = client.get("/api/db/info")
    assert r.status_code == 401


def test_agent_rules_public_capabilities(client, admin_token):
    """系统内置规则公示：安全基线/红旗/药互/证据分级/意图/计算器清单一次给出。"""
    r = client.get("/api/agent/rules", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "safety_baseline" in body and "不得虚构" in body["safety_baseline"]
    assert body["red_flags"]["total"] >= 10
    assert "emergent" in body["red_flags"]["by_severity"]
    assert body["drug_interactions"]["total"] >= 10
    assert set(body["evidence_levels"]) >= {"A", "B", "C", "D"}
    intent_ids = {i["intent"] for i in body["intents"]}
    assert intent_ids >= {"consult", "intake", "calculator", "drug", "knowledge", "literature"}
    assert len(body["calculators"]) >= 5


def test_doctor_scope_isolated(client, admin_token):
    """数据可见性：医生默认只见自己创建的患者/会诊，不能越权看他人记录。"""
    # admin 创建患者 A
    ra = client.post("/api/patients", headers=auth(admin_token), json={
        "name": "隔离患者A", "gender": "男", "hospital_no": "ISO-A",
        "id_card": "440000199001011234"})
    pa = ra.json()["id"]

    # doc01（已有）创建患者 B
    doc_token = _login(client, "doc01", "Doc@12345!")
    rb = client.post("/api/patients", headers=auth(doc_token), json={
        "name": "隔离患者B", "gender": "女", "hospital_no": "ISO-B"})
    pb = rb.json()["id"]

    # 医生看列表：只有自己的 B
    items = client.get("/api/patients", headers=auth(doc_token)).json()["items"]
    ids = [x["id"] for x in items]
    assert pb in ids and pa not in ids, "医生不应看到他人创建的患者"

    # 医生直接读 A → 404（不存在语义，防泄露）
    assert client.get(f"/api/patients/{pa}", headers=auth(doc_token)).status_code == 404

    # 医生创建会诊，admin 创建的会诊不可见
    rc = make_consult(client, doc_token, "隔离会诊B")
    cid_doc = rc.json()["id"]
    ra2 = make_consult(client, admin_token, "隔离会诊A")
    cid_admin = ra2.json()["id"]

    clist = client.get("/api/consultations", headers=auth(doc_token)).json()["items"]
    cids = [x["id"] for x in clist]
    assert cid_doc in cids and cid_admin not in cids

    # 主任/管理员可见全部
    chief_token = _login(client, "chief01", "Chief@12345!")
    cids_all = [x["id"] for x in client.get("/api/consultations", headers=auth(chief_token)).json()["items"]]
    assert cid_admin in cids_all and cid_doc in cids_all


def test_doctor_scope_same_hospital_visible(client, admin_token):
    """同机构医生互见：hospital 配置后，同院其他医生数据可见（协作场景）。"""
    r = client.post("/api/auth/register", headers=auth(admin_token), json={
        "username": "doc_hos1", "password": "Doc@12345!", "full_name": "一院医生1",
        "role": "doctor", "hospital": "康复医院"})
    assert r.status_code == 200
    r = client.post("/api/auth/register", headers=auth(admin_token), json={
        "username": "doc_hos2", "password": "Doc@12345!", "full_name": "一院医生2",
        "role": "doctor", "hospital": "康复医院"})
    assert r.status_code == 200
    t1 = _login(client, "doc_hos1", "Doc@12345!")
    t2 = _login(client, "doc_hos2", "Doc@12345!")

    r1 = client.post("/api/patients", headers=auth(t1), json={
        "name": "同院患者1", "gender": "男", "hospital_no": "HOS-1"})
    p1 = r1.json()["id"]
    items = client.get("/api/patients", headers=auth(t2)).json()["items"]
    assert any(x["id"] == p1 for x in items), "同院医生应可见彼此患者"


def test_consultation_export_html(client, admin_token):
    """报告导出：打印友好 HTML，含标题/报告内容/证据链/免责说明；沙箱带演示水印。"""
    r = make_consult(client, admin_token, "导出测试：胸痛伴冷汗2小时")
    cid = r.json()["id"]
    r = client.get(f"/api/consultations/{cid}/export", headers=auth(admin_token))
    assert r.status_code == 200
    body = r.text
    assert "<html" in body and "会诊 #" in body
    assert "仅供临床医师参考" in body
    assert "沙箱演示报告" in body, "沙箱报告导出必须带禁止打印水印（合规）"
    assert "window.print()" in body


def test_stream_and_detail_scope(client, admin_token):
    """流式/详情越权：医生不能通过 ID 直接流式回放或导出他人会诊。"""
    rc = make_consult(client, admin_token, "scope 流式测试")
    cid = rc.json()["id"]
    doc_token = _login(client, "doc01", "Doc@12345!")
    assert client.get(f"/api/consultations/{cid}/stream", headers=auth(doc_token)).status_code == 404
    assert client.get(f"/api/consultations/{cid}/export", headers=auth(doc_token)).status_code == 404
    assert client.get(f"/api/consultations/{cid}", headers=auth(doc_token)).status_code == 404


def test_library_delete_requires_chief(client, admin_token):
    """知识库删除：普通医生无权限，主任可删（文档库为共享知识资产）。"""
    # 上传一份文档
    files = {"files": ("jieji.txt", "kalium jinyi".encode(), "text/plain")}
    r = client.post("/api/library/upload", headers=auth(admin_token), files=files)
    assert r.status_code == 200, r.text
    doc_id = r.json()["items"][0]["id"]

    doc_token = _login(client, "doc01", "Doc@12345!")
    assert client.delete(f"/api/library/{doc_id}", headers=auth(doc_token)).status_code == 403
    chief_token = _login(client, "chief01", "Chief@12345!")
    assert client.delete(f"/api/library/{doc_id}", headers=auth(chief_token)).status_code == 200


def test_feedback_detail_requires_chief(client, admin_token):
    """反馈详情：普通医生不可读他人反馈（与列表权限一致）。"""
    doc_token = _login(client, "doc01", "Doc@12345!")
    r = client.post("/api/feedback", headers=auth(doc_token), json={
        "title": "权限测试反馈", "diagnosis": "肺炎", "helpful": True})
    fid = r.json()["id"]
    assert client.get(f"/api/feedback/{fid}", headers=auth(doc_token)).status_code == 403
    chief_token = _login(client, "chief01", "Chief@12345!")
    assert client.get(f"/api/feedback/{fid}", headers=auth(chief_token)).status_code == 200
