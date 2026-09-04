"""采集式问诊引擎（垂直临床 agent 对话层差异化核心）。

与"自由聊天"的本质区别：
1. 主诉驱动的定向问诊：按主诉类别走固定的鉴别诊断采集协议（SOAP 结构化）。
2. 每个追问都带"为什么要问"：对应某个鉴别诊断，不是闲聊。
3. 实时红旗拦截：患者任何一轮回答出现危急征象，立即中断常规采集，切换急诊路径。
4. 对话自动落成结构化病历：S(主观)/O(客观)/A(评估)/P(计划) 五段式，可直接建就诊记录。

本模块为确定性实现（无需 LLM 也能完成一次合格的基础问诊），
后续可加 LLM 增强：对自由长文本回答自动抽取字段。
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..models import IntakeStatus

# ---------------------------------------------------------------- 主诉分类
CHEST_PAIN = "chest_pain"
ABDOMINAL = "abdominal"
HEADACHE = "headache"
FEVER = "fever"
COUGH = "cough"
TRAUMA = "trauma"
OTHER = "other"

CATEGORY_LABEL = {
    CHEST_PAIN: "胸痛",
    ABDOMINAL: "腹痛",
    HEADACHE: "头痛",
    FEVER: "发热",
    COUGH: "咳嗽",
    TRAUMA: "外伤",
    OTHER: "其他不适",
}

_KEYWORDS = {
    CHEST_PAIN: [r"胸[痛闷压]", r"胸口闷", r"心前区", r"左胸", r"心口", r"胸闷"],
    ABDOMINAL: [r"腹[痛胀]", r"肚[子痛胀]", r"胃痛", r"右下腹", r"左上腹", r"脐周"],
    HEADACHE: [r"头痛", r"头疼", r"偏头痛", r"头胀"],
    FEVER: [r"发热", r"发烧", r"体温.{0,4}高", r"高热"],
    COUGH: [r"咳嗽", r"咳痰", r"干咳", r"咯血"],
    TRAUMA: [r"外伤", r"摔伤", r"摔跤", r"摔了", r"跌", r"撞伤", r"刀伤", r"烫伤", r"烧伤", r"骨折", r"出血"],
}


def classify_chief_complaint(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return OTHER
    scored: list[tuple[int, str]] = []
    for cat, kws in _KEYWORDS.items():
        score = sum(1 for k in kws if re.search(k, t))
        if score:
            scored.append((score, cat))
    if not scored:
        return OTHER
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


# ---------------------------------------------------------------- 问诊协议
@dataclass
class IntakeQuestion:
    field: str                  # 采集字段名（写入 fields_json）
    question: str               # 问题文本
    reason: str                 # 为什么问（对应鉴别诊断）
    priority: int = 1           # 越大越优先
    options: list[str] = field(default_factory=list)


# 各类主诉的定向采集协议。reason 即"为什么要问"，向用户展示采集理由。
_QUESTIONS: dict[str, list[IntakeQuestion]] = {
    CHEST_PAIN: [
        IntakeQuestion("nature", "这种胸痛是什么感觉？（压榨样闷痛 / 针刺样 / 撕裂样 / 刀割样 / 说不清）",
                       "性质是区分心绞痛、心包炎、主动脉夹层、气胸的关键线索", 5,
                       ["压榨样闷痛", "针刺样", "撕裂样", "刀割样", "说不清"]),
        IntakeQuestion("onset", "疼痛是突然出现的还是逐渐加重？大概持续了多久？",
                       "突发剧烈疼痛提示急性心肌梗死、主动脉夹层或肺栓塞等急症", 5),
        IntakeQuestion("radiation", "疼痛有没有往别的地方放射？比如左肩、左臂、后背、下颌？",
                       "向左肩臂/下颌放射是心肌缺血的特征性表现", 4,
                       ["左肩左臂", "后背", "下颌", "没有"]),
        IntakeQuestion("sweat", "有没有同时出冷汗、心慌、头晕或呼吸困难？",
                       "胸痛伴冷汗/濒死感是急性冠脉综合征的危险信号，必须紧急处理", 5,
                       ["有", "没有"]),
        IntakeQuestion("aggravating", "什么情况下会加重？活动后、劳累后还是休息时也痛？",
                       "劳力诱发提示心绞痛；与呼吸相关提示胸膜炎/心包炎；与体位相关提示心包炎", 3),
        IntakeQuestion("relieving", "有没有办法能缓解？含服硝酸甘油/休息后是否好转？",
                       "硝酸甘油缓解支持心绞痛诊断", 3),
        IntakeQuestion("past_history", "以前有没有高血压、糖尿病、冠心病、血脂异常这些病史？",
                       "心血管危险因素显著影响胸痛的危险分层", 2),
        IntakeQuestion("meds", "目前在吃什么药？（特别是有没有阿司匹林、抗凝药）",
                       "抗凝/抗血小板用药影响出血风险与急诊处理决策", 1),
    ],
    ABDOMINAL: [
        IntakeQuestion("location", "主要痛在哪个位置？（上腹 / 下腹 / 右下腹 / 左上腹 / 脐周 / 说不清）",
                       "疼痛部位是急腹症定位诊断的第一线索（右下腹提示阑尾炎、上腹提示胰腺/胆囊等）", 5,
                       ["上腹", "下腹", "右下腹", "左上腹", "脐周", "说不清"]),
        IntakeQuestion("nature", "疼痛是什么感觉？（绞痛一阵阵 / 刀割样 / 隐痛 / 胀痛 / 说不清）",
                       "绞痛提示空腔脏器痉挛（胆结石/肠梗阻），刀割样提示穿孔或胰腺炎", 4,
                       ["绞痛一阵阵", "刀割样", "隐痛", "胀痛", "说不清"]),
        IntakeQuestion("aggravating", "有没有伴发烧、恶心呕吐、拉肚子或大便变黑？",
                       "伴发热提示感染（阑尾炎/胆囊炎）；黑便提示上消化道出血", 5),
        IntakeQuestion("relieving", "按压的时候更痛，还是放松的时候更痛？",
                       "反跳痛/腹肌紧张提示腹膜炎，需要外科紧急评估", 3),
        IntakeQuestion("past_history", "以前有没有胃溃疡、胆囊结石、胰腺炎、阑尾炎这些病史？",
                       "既往病史帮助鉴别溃疡复发、胆绞痛、慢性胰腺炎急性发作", 2),
        IntakeQuestion("gender_preg", "如果是育龄女性，有可能怀孕吗？（末次月经情况）",
                       "育龄女性腹痛必须排除宫外孕破裂等妇产科急症", 2),
    ],
    HEADACHE: [
        IntakeQuestion("onset", "头痛是突然爆发的，还是慢慢加重的？持续了多久？",
                       "突发剧烈头痛（雷击样）提示蛛网膜下腔出血，需要立即急诊", 5),
        IntakeQuestion("severity", "头痛程度有多重？是这辈子最痛的一次吗？",
                       "「最剧烈头痛」是蛛网膜下腔出血的经典表现", 5),
        IntakeQuestion("associated", "有没有伴恶心呕吐、视物模糊、肢体麻木无力、说话不清？",
                       "伴神经系统症状提示脑血管事件、颅内占位或偏头痛先兆", 4),
        IntakeQuestion("laterality", "是单侧痛还是整个头痛？有没有搏动感？",
                       "单侧搏动性头痛是偏头痛特征；双侧紧箍样痛提示紧张型头痛", 3),
        IntakeQuestion("past_history", "以前有没有偏头痛、高血压病史？最近血压怎么样？",
                       "高血压急症可表现为头痛；既往偏头痛帮助鉴别", 2),
    ],
    FEVER: [
        IntakeQuestion("temp", "最高体温到多少度？发热持续几天了？",
                       "体温高度与持续时间帮助判断感染严重度与热型", 5),
        IntakeQuestion("chill", "有没有发冷寒战？", "寒战提示菌血症/脓毒症可能，需要更积极处理", 4),
        IntakeQuestion("associated", "有没有伴咳嗽咳痰、咽痛、腹痛腹泻、尿频尿痛或皮疹？",
                       "伴随症状帮助定位感染灶（呼吸道/消化道/泌尿道/皮肤）", 5),
        IntakeQuestion("meds", "发热期间吃了什么药？有没有效果？",
                       "用药史评估退热效果与潜在药物热", 2),
    ],
    COUGH: [
        IntakeQuestion("sputum", "是干咳还是有痰？痰是什么颜色？有没有带血？",
                       "黄脓痰提示细菌感染，铁锈色痰提示肺炎链球菌，血痰需排查结核/肿瘤/肺栓塞", 5),
        IntakeQuestion("fever", "有没有伴发热、胸痛或呼吸困难？",
                       "伴发热/胸痛/气促提示肺炎、胸膜炎等需要影像学评估", 5),
        IntakeQuestion("duration", "咳嗽持续多久了？（急性/亚急性/慢性）",
                       "病程长短区分急性呼吸道感染、亚急性(百日咳/支原体)、慢性(慢阻肺/反流/咳嗽变异性哮喘)", 4),
        IntakeQuestion("smoking", "有吸烟史吗？吸多少年、每天多少支？",
                       "吸烟是慢阻肺/肺癌/慢性咳嗽的重要危险因素", 2),
    ],
    TRAUMA: [
        IntakeQuestion("mechanism", "是怎么受伤的？摔伤/撞伤/切割伤？受伤时间多久了？",
                       "受伤机制与能量大小决定是否需排查骨折、内出血、颅脑损伤", 5),
        IntakeQuestion("loss_conscious", "受伤当时或之后有没有晕倒、意识不清、记不清？",
                       "意识丧失提示颅脑损伤（脑震荡/颅内出血），需急诊评估", 5),
        IntakeQuestion("bleeding", "有没有明显出血或伤口？出血量大吗？有没有包扎止血？",
                       "活动性出血/大出血需立即止血并急诊；伤口深度决定破伤风/清创需求", 4),
        IntakeQuestion("pain_move", "受伤部位能不能正常活动？有没有明显肿胀、畸形、麻木？",
                       "无法活动/畸形提示骨折；麻木提示神经损伤", 4),
        IntakeQuestion("tetanus", "最近 5-10 年内打过破伤风疫苗吗？",
                       "破伤风预防取决于伤口类型与疫苗史", 2),
    ],
    OTHER: [
        IntakeQuestion("onset", "这个不适大概从什么时候开始？持续多久了？",
                       "病程帮助区分急性与慢性问题，影响紧急性判断", 5),
        IntakeQuestion("location", "主要不舒服在哪个部位？有没有往别的地方扩散？",
                       "定位与扩散方向是诊断的第一线索", 4),
        IntakeQuestion("associated", "有没有伴其他症状？比如发热、头晕、乏力、体重变化？",
                       "伴随症状帮助缩小鉴别诊断范围", 4),
        IntakeQuestion("past_history", "以前有没有类似情况或相关疾病史？",
                       "复发模式与基础疾病是重要鉴别信息", 3),
        IntakeQuestion("meds", "最近在吃什么药？有没有新换药或停药？",
                       "药物相关不良反应是常见且易被忽视的原因", 2),
    ],
}

# 通用补全问题（各类都问，确保完备度）
_COMMON_QUESTIONS: list[IntakeQuestion] = [
    IntakeQuestion("allergy", "有没有药物或食物过敏史？（特别是青霉素、头孢、磺胺类）",
                   "过敏史是安全用药的硬前提，直接决定处方禁忌", 4),
    IntakeQuestion("vitals", "有没有量过体温、血压、心率？最近一次数值是多少？",
                   "生命体征是客观状态基线，影响评估与计算器调用", 2),
    IntakeQuestion("exams", "针对这个情况，近期做过什么检查吗？结果如何？（血常规、心电图、CT 等）",
                   "已有检查结果避免重复检查，且直接进入证据链", 3),
]


def protocol_for(category: str, chief_complaint: str) -> list[IntakeQuestion]:
    qs = list(_QUESTIONS.get(category, _QUESTIONS[OTHER]))
    qs = qs + list(_COMMON_QUESTIONS)
    # 去重（同 field 只保留一次）
    seen: set[str] = set()
    out: list[IntakeQuestion] = []
    for q in qs:
        if q.field not in seen:
            seen.add(q.field)
            out.append(q)
    return out


# ---------------------------------------------------------------- 会话状态
@dataclass
class IntakeState:
    chief_complaint: str = ""
    category: str = OTHER
    fields: dict[str, str] = field(default_factory=dict)   # 已采集字段
    answers: list[dict] = field(default_factory=list)      # 对话记录 [{q, a, reason}]
    protocol: list[dict] = field(default_factory=list)     # 协议问题快照
    status: IntakeStatus = IntakeStatus.COLLECTING                       # collecting|redflag|complete
    red_flags: list[dict] = field(default_factory=list)
    flags_urgent: bool = False
    # 每次回答命中的红旗会优先返回（即使协议未走完）
    initial_flags: list[dict] = field(default_factory=list)   # 启动时主诉命中（一次性提示）
    _reported: set[str] = field(default_factory=set)          # 已报告红旗 message，避免主诉红旗每轮重复触发

    def to_dict(self) -> dict:
        return {
            "chief_complaint": self.chief_complaint,
            "category": self.category,
            "category_label": CATEGORY_LABEL.get(self.category, "其他"),
            "fields": self.fields,
            "answers": self.answers[-8:],          # 前端只回显最近 8 轮
            "status": self.status,
            "red_flags": self.red_flags,
            "flags_urgent": self.flags_urgent,
            "initial_flags": self.initial_flags,
        }


def init_state(chief_complaint: str) -> IntakeState:
    cat = classify_chief_complaint(chief_complaint)
    state = IntakeState(
        chief_complaint=chief_complaint.strip(),
        category=cat,
    )
    state.protocol = [asdict(q) for q in protocol_for(cat, chief_complaint)]
    # 启动时对主诉做一次红旗扫描：命中即记录（一次性），供前端在首问前提示
    from .triage import scan
    for h in scan(state.chief_complaint):
        item = {"severity": h.severity, "message": h.message, "matched": h.matched}
        state.initial_flags.append(item)
        state._reported.add(h.message)
    if state.initial_flags:
        state.red_flags = list(state.initial_flags)
        state.flags_urgent = any(f["severity"] == "emergent" for f in state.initial_flags)
    return state


def _next_unasked(state: IntakeState) -> Optional[dict]:
    """返回协议中下一个未采集且未回答过的问题（按优先级降序）。"""
    asked = {q["field"] for q in state.answers if q.get("field")}
    filled = set(state.fields.keys())
    for q in state.protocol:
        f = q["field"]
        if f in asked or f in filled:
            continue
        return q
    return None


def apply_answer(state: IntakeState, answer: str) -> dict:
    """处理一轮回答。返回 {reply, interrupt, red_flags, next_question, done}。

    1) 先做红旗拦截：回答中出现危急征象 → 中断常规采集。
    2) 无红旗：记录回答，取下一个问题；协议走完 → complete。
    """
    answer = (answer or "").strip()
    from .triage import scan
    # 拼接"主诉 + 已采集回答 + 本轮回答"整体扫描，避免逐轮片段漏检红旗
    # （如"放射到左肩/出冷汗"单看无"胸痛"二字，但结合主诉即为 ACS 高危）。
    # 只报告"新增命中"的红旗（主诉红旗已在启动时报告过），避免每轮重复中断。
    # 用空格拼接（而非分号）：triage 正则 [^。；] 不允许跨分号匹配，
    # 用分号会导致"主诉胸痛 + 回答放射/冷汗"的 ACS 跨片段规则漏检。
    context = " ".join(
        [state.chief_complaint or ""]
        + [a.get("answer", "") for a in state.answers]
        + [answer]
    )
    hits = [h for h in scan(context) if h.message not in state._reported]
    if hits:
        for h in hits:
            state._reported.add(h.message)
        state.red_flags = [{"severity": h.severity, "message": h.message, "matched": h.matched}
                           for h in hits]
        state.flags_urgent = any(h.severity == "emergent" for h in hits)
        state.status = IntakeStatus.REDFLAG
        top = state.red_flags[0]
        reply = (
            "⚠️ 您刚才的描述出现了需要立即处理的征象，请不要再继续线上问诊流程。\n"
            f"【{ '立即急诊' if top['severity']=='emergent' else '尽快就医' }】{top['message']}\n"
            "建议：立即到急诊科就诊（必要时拨打 120），并带上现有病历与用药清单。\n"
            "本系统已停止常规采集，但会保留已录入的信息供急诊医生参考。"
        )
        return {"reply": reply, "interrupt": True, "red_flags": state.red_flags,
                "next_question": None, "done": False}

    current = _next_unasked(state)
    if current:
        state.answers.append({
            "field": current["field"],
            "question": current["question"],
            "reason": current["reason"],
            "answer": answer,
        })
        state.fields[current["field"]] = answer
        nxt = _next_unasked(state)
        if nxt:
            return {"reply": None, "interrupt": False, "red_flags": [],
                    "next_question": nxt, "done": False}
        # 协议走完
        state.status = IntakeStatus.COMPLETE
        return {"reply": None, "interrupt": False, "red_flags": [],
                "next_question": None, "done": True}
    # 无待问问题：完成
    state.status = IntakeStatus.COMPLETE
    return {"reply": None, "interrupt": False, "red_flags": [],
            "next_question": None, "done": True}


def first_question(state: IntakeState) -> dict | None:
    """会话启动后返回第一个待问问题。"""
    return _next_unasked(state)


# ---------------------------------------------------------------- 病历生成
def build_record(state: IntakeState) -> dict:
    """由采集字段生成结构化病历（SOAP 五段式，与 Encounter 字段对齐）。"""
    f = state.fields
    chief = state.chief_complaint or f.get("location", "")
    def g(*keys: str) -> str:
        vals = [f.get(k, "").strip() for k in keys if f.get(k, "").strip()]
        return "；".join(vals) if vals else "未见"

    history_parts = []
    if f.get("onset"):
        history_parts.append("起病：" + f["onset"])
    if f.get("nature"):
        history_parts.append("性质：" + f["nature"])
    if f.get("radiation"):
        history_parts.append("放射：" + f["radiation"])
    if f.get("aggravating"):
        history_parts.append("加重因素：" + f["aggravating"])
    if f.get("relieving"):
        history_parts.append("缓解因素：" + f["relieving"])
    if f.get("associated"):
        history_parts.append("伴随症状：" + f["associated"])
    if f.get("sweat"):
        history_parts.append("伴出汗：" + f["sweat"])
    if f.get("laterality"):
        history_parts.append("部位特点：" + f["laterality"])
    history = "；".join(history_parts) if history_parts else "现病史信息待补充"

    past = []
    for k in ("past_history", "allergy", "meds", "smoking", "tetanus", "gender_preg"):
        if f.get(k, "").strip():
            past.append(f"{k}：" + f[k])
    meds = f.get("meds", "")
    exams = f.get("exams", "")
    vitals = f.get("vitals", "")

    record = {
        "chief_complaint": chief,
        "history": history,
        "past_history": "；".join(past) if past else "未见",
        "meds": meds or "未见",
        "exams": exams or "未见",
        "vitals": vitals or "未见",
    }
    # 供 Encounter 落库的五段式
    enc_text = {
        "chief_complaint": chief,
        "history": history + ("；既往史：" + "；".join(past) if past else ""),
        "meds": meds,
        "exams": exams,
        "vitals": vitals,
    }
    return {"record": record, "encounter_fields": enc_text}


# ---------------------------------------------------------------- 序列化辅助
def state_from_json(chief_complaint: str, category: str, fields: dict,
                    answers: list[dict], protocol: list[dict],
                    status: IntakeStatus, red_flags: list[dict], flags_urgent: bool,
                    initial_flags: list[dict] | None = None,
                    reported: list[str] | None = None) -> IntakeState:
    st = IntakeState(
        chief_complaint=chief_complaint,
        category=category or classify_chief_complaint(chief_complaint),
        fields=fields or {},
        answers=answers or [],
        protocol=protocol or [],
        status=status or IntakeStatus.COLLECTING,
        red_flags=red_flags or [],
        flags_urgent=flags_urgent or False,
        initial_flags=initial_flags or [],
        _reported=set(reported or []),
    )
    if not st.protocol:
        st.protocol = [asdict(q) for q in protocol_for(st.category, st.chief_complaint)]
    # 兼容旧数据：无 reported 时，把既有 red_flags 视为已报告，避免恢复后重复中断
    if not st._reported and st.red_flags:
        st._reported = {f["message"] for f in st.red_flags}
    return st
