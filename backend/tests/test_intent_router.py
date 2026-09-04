"""意图识别单元测试：确定性规则分流，回归保护。"""
from app.services.intent import Intent, classify_intent


def _assert(intent, text):
    d = classify_intent(text)
    assert d.intent == intent, f"{text!r} → {d.intent.value} (期望 {intent.value})：{d.reason}"


def test_calculator_intents():
    for t in ("58岁男性，帮我算一下 BMI", "curb-65 评分多少", "GCS 昏迷评分计算",
              "评估一下 timi 危险分层", "CHADS2 评分"):
        _assert(Intent.CALCULATOR, t)


def test_drug_intents():
    for t in ("华法林和阿司匹林能一起吃吗", "二甲双胍与造影剂相互作用",
              "这几种药有没有配伍禁忌", "检查一下处方里的重复用药"):
        _assert(Intent.DRUG, t)


def test_literature_intents():
    for t in ("检索一下胸痛的最新循证证据", "查一下关于房颤抗凝的文献",
              "有没有 pubmed 上的随机对照研究", "meta 分析支持吗"):
        _assert(Intent.LITERATURE, t)


def test_knowledge_intents():
    for t in ("血糖正常值是多少", "高血压诊疗指南推荐什么", "什么是房颤", "HbA1c 参考值"):
        _assert(Intent.KNOWLEDGE, t)


def test_intake_intents():
    for t in ("帮我做一个采集式问诊", "我想走问诊流程", "应该挂什么科"):
        _assert(Intent.INTAKE, t)


def test_consult_default():
    d = classify_intent("58岁男性，胸痛伴冷汗3小时，高血压病史，既往冠心病")
    assert d.intent == Intent.CONSULT
    # 无强信号的病情描述默认进会诊，但置信度标注偏低以便前端确认
    assert d.confidence < 0.5


def test_consult_explicit():
    d = classify_intent("请组织一次多学科会诊：患者黄疸伴发热2天")
    assert d.intent == Intent.CONSULT
    assert d.confidence >= 0.9