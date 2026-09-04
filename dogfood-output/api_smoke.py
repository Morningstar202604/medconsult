"""全链路 API 冒烟测试：覆盖本轮所有改动（隔离/脱敏/导出/规则/限流/鉴权/意图/流式/删除）。"""
import json
import sys

import requests

BASE = "http://127.0.0.1:8000/api"
errors = []


def check(name, cond, extra=""):
    print(f"{'PASS' if cond else 'FAIL'} | {name} {extra}")
    if not cond:
        errors.append(name)


def login(u, p):
    r = requests.post(f"{BASE}/auth/login", json={"username": u, "password": p}, timeout=10)
    if r.status_code != 200:
        raise SystemExit(f"login {u} failed: {r.status_code} {r.text}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


ADMIN = login("admin", "ChangeMe123!")

# 0) 健康检查
check("health", requests.get(f"{BASE}/health", timeout=10).status_code == 200)

# 1) 匿名拦截
for p in ("/patients", "/consultations", "/feedback", "/library", "/agent/rules", "/db/info"):
    check(f"匿名拦截 {p}", requests.get(f"{BASE}{p}", timeout=10).status_code == 401)

# 2) 内置规则公示
r = requests.get(f"{BASE}/agent/rules", headers=ADMIN, timeout=10)
d = r.json()
check("agent/rules", r.status_code == 200 and d["red_flags"]["total"] >= 10 and d["drug_interactions"]["total"] >= 10)

# 3) 建医生并创建患者/会诊
r = requests.post(f"{BASE}/auth/register", headers=ADMIN,
                  json={"username": "doc_final", "password": "Doc@12345!", "full_name": "终检医生", "role": "doctor"}, timeout=10)
check("注册医生", r.status_code == 200, r.text[:80])
DOC = login("doc_final", "Doc@12345!")

r = requests.post(f"{BASE}/patients", headers=DOC,
                  json={"name": "终检患者", "gender": "男", "hospital_no": "FINAL-001",
                        "id_card": "440000199001011234", "phone": "13800138000"}, timeout=10)
pid = r.json()["id"]
check("医生建患者", r.status_code == 200 and pid > 0)

# PHI 脱敏
r = requests.get(f"{BASE}/patients/{pid}", headers=DOC, timeout=10)
b = r.json()
check("PHI 脱敏", "***" in b["id_card"] and "****" in b["phone"])
r = requests.get(f"{BASE}/patients/{pid}", headers=ADMIN, timeout=10)
check("管理员全文 PHI", r.json()["id_card"] == "440000199001011234")

# 4) 意图分流
r = requests.post(f"{BASE}/agent", headers=DOC, json={"text": "计算 BMI 25.5"}, timeout=10)
check("意图-计算器", r.status_code == 200 and r.json()["intent"]["intent"] == "calculator")
r = requests.post(f"{BASE}/agent", headers=DOC, json={"text": "华法林能和阿司匹林一起吃吗"}, timeout=10)
check("意图-用药", r.json()["intent"]["intent"] == "drug")

# 5) 会诊全流程
r = requests.post(f"{BASE}/consultations", headers=DOC,
                  json={"mode": "sandbox", "text": "58岁男性，胸痛伴冷汗3小时", "specialties": ["internal", "cardio"], "style": "brief", "rounds": 1}, timeout=60)
cid = r.json()["id"]
check("创建会诊", r.status_code == 200 and r.json()["status"] == "completed")

# 6) 导出 HTML（沙箱水印）
r = requests.get(f"{BASE}/consultations/{cid}/export", headers=DOC, timeout=10)
check("导出HTML", r.status_code == 200 and "仅供临床医师参考" in r.text and "沙箱演示报告" in r.text)

# 7) 流式 SSE
r = requests.get(f"{BASE}/consultations/{cid}/stream", headers=DOC, timeout=15)
check("SSE 流式", r.status_code == 200 and "text/event-stream" in r.headers.get("content-type", "") and "report_chunk" in r.text)

# 8) 数据隔离：另一医生不可见
U2 = login("doc_final", "Doc@12345!")  # 复用
r = requests.get(f"{BASE}/consultations", headers=U2, timeout=10)
check("列表隔离-可见自己", any(x["id"] == cid for x in r.json()["items"]))
r = requests.get(f"{BASE}/patients/{pid}", headers=U2, timeout=10)
check("同医生读自己 OK", r.status_code == 200)

# admin 建的会诊，另一医生不可见
r = requests.post(f"{BASE}/consultations", headers=ADMIN,
                  json={"mode": "sandbox", "text": "admin 私有会诊", "specialties": ["internal"], "style": "brief", "rounds": 1}, timeout=60)
cid_admin = r.json()["id"]
r = requests.get(f"{BASE}/consultations/{cid_admin}", headers=DOC, timeout=10)
check("医生不可读admin会诊", r.status_code == 404)
r = requests.get(f"{BASE}/consultations/{cid_admin}/stream", headers=DOC, timeout=10)
check("医生不可流式admin会诊", r.status_code == 404)

# 9) 删除（创建者可删）
r = requests.delete(f"{BASE}/consultations/{cid}", headers=DOC, timeout=10)
check("删除会诊", r.status_code == 200 and r.json()["deleted"])

# 10) 反馈权限
r = requests.post(f"{BASE}/feedback", headers=DOC, json={"title": "终检反馈", "diagnosis": "ACS", "helpful": True}, timeout=10)
fid = r.json()["id"]
r = requests.get(f"{BASE}/feedback/{fid}", headers=DOC, timeout=10)
check("医生不可读反馈详情", r.status_code == 403)
r = requests.get(f"{BASE}/feedback/{fid}", headers=ADMIN, timeout=10)
check("管理员可读反馈", r.status_code == 200)

# 11) db/info 鉴权+展示
r = requests.get(f"{BASE}/db/info", headers=ADMIN, timeout=10)
check("db/info", r.status_code == 200 and "database" in r.json())

# 12) db/info 匿名 401 已在上面覆盖
print("\n===== API 冒烟测试总结 =====")
if errors:
    print(f"FAIL: {len(errors)} 项未通过 -> {errors}")
    sys.exit(1)
print("全部通过")