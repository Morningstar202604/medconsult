"""会诊技能包（Skills）：可复用的专科会诊指令集，医院可自行沉淀科室经验。

每个技能 = {id, name, desc, prompt}，勾选后注入本场会诊所有专家与主持人的
系统提示词（提示词工程资产，与角色提示词分层：安全基线 > 医院规范 > 技能 > 角色）。
存储于 library/skills/*.json；首次运行自动播种四个常见技能。
"""
import json
import os
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_BASE, "library", "skills")

_lock = threading.Lock()

SEED = [
    {"id": "anticoag", "name": "抗凝管理", "desc": "房颤/VTE 抗凝决策与出血评估",
     "prompt": "涉及抗凝决策时：先完成血栓风险（CHA₂DS₂-VASc）与出血风险（HAS-BLED 要素）双评估；"
               "药物选择给出优先级（非瓣膜性优先 DOAC，机械瓣/中重度二尖瓣狭窄用华法林）；"
               "明确启动时机、肾功能剂量调整、桥接指征；提示需监测项与患者教育要点。"},
    {"id": "chest_pain", "name": "胸痛鉴别", "desc": "致命性胸痛红旗与时间敏感决策",
     "prompt": "涉及胸痛时：优先排除五类致命病因——ACS、主动脉夹层、肺栓塞、张力性气胸、心包填塞；"
               "按时间敏感顺序安排心电图/高敏肌钙蛋白/D-二聚体/CTA；明确各自的立即处理与禁忌；"
               "不可在排除致命病因前给出良性结论。"},
    {"id": "peds_dose", "name": "儿童用药", "desc": "儿科体重剂量与禁忌核查",
     "prompt": "涉及儿科患者时：所有推荐剂量必须按体重(kg)或体表面积给出并附计算式；"
               "标注儿童禁用/慎用药物；成人剂型不可直接折算；超范围剂量必须提示复核并请药师确认。"},
    {"id": "infection", "name": "感染会诊", "desc": "脓毒症筛查与抗菌药物原则",
     "prompt": "涉及感染时：先做脓毒症筛查（qSOFA/SOFA 要素、乳酸、器官灌注）；"
               "经验性抗菌方案需覆盖感染部位+本地耐药风险，并说明降阶梯策略与停药指征；"
               "给出肝肾功能调整建议； 48-72h 复评治疗反应。"},
]


def _ensure():
    os.makedirs(DIR, exist_ok=True)


def _path(sid):
    return os.path.join(DIR, sid + ".json")


def seed_if_empty():
    """首次运行播种默认技能；已存在的文件不覆盖。"""
    _ensure()
    if os.listdir(DIR):
        return
    with _lock:
        if os.listdir(DIR):
            return
        for sk in SEED:
            with open(_path(sk["id"]), "w", encoding="utf-8") as f:
                json.dump(sk, f, ensure_ascii=False)


def list_skills():
    seed_if_empty()
    out = []
    for fn in sorted(os.listdir(DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DIR, fn), "r", encoding="utf-8") as f:
                sk = json.load(f)
            if sk.get("id") and sk.get("name") and sk.get("prompt"):
                out.append({"id": sk["id"], "name": sk["name"],
                            "desc": sk.get("desc", ""), "prompt": sk["prompt"]})
        except Exception:
            continue
    return out


def get(sid):
    for sk in list_skills():
        if sk["id"] == sid:
            return sk
    return None


def save(name, desc, prompt, sid=None):
    name = (name or "").strip()
    prompt = (prompt or "").strip()
    if not name or not prompt:
        return None
    with _lock:
        _ensure()
        sid = (sid or "").strip() or "sk_" + str(abs(hash(name)) % 10**8)
        sk = {"id": sid, "name": name, "desc": (desc or "").strip(), "prompt": prompt}
        with open(_path(sid), "w", encoding="utf-8") as f:
            json.dump(sk, f, ensure_ascii=False)
    return sk


def delete(sid):
    with _lock:
        _ensure()
        p = _path(sid)
        if os.path.exists(p):
            os.remove(p)
            return True
    return False
