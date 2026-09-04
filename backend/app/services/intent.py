"""系统级意图识别：把一句话分流到 会诊 / 问诊 / 医学计算 / 用药 / 知识问答 / 循证检索。

双通道设计：
- 确定性规则通道：领域关键词命中即高置信度分流（可解释、可测试、零延迟）；
- 默认通道：无强信号时归为「会诊」并给出低置信度提示，由上游（前端）让医生确认。

与 clinical/intake.py 的 classify 不同：那是问诊内部的「话题分类」，
本模块是顶层「能力路由」，决定走哪条产品链路。
"""
import enum
import re


class Intent(str, enum.Enum):
    CONSULT = "consult"          # 多学科会诊（MDT）
    INTAKE = "intake"            # 采集式问诊
    CALCULATOR = "calculator"    # 医学计算器/评分
    DRUG = "drug"                # 用药安全 / 相互作用
    KNOWLEDGE = "knowledge"      # 知识问答 / 指南 / 参考值
    LITERATURE = "literature"    # 循证检索 / 最新文献


_INTENT_LABEL = {
    Intent.CONSULT: "多学科会诊",
    Intent.INTAKE: "采集式问诊",
    Intent.CALCULATOR: "医学计算",
    Intent.DRUG: "用药安全",
    Intent.KNOWLEDGE: "知识问答",
    Intent.LITERATURE: "循证检索",
}

# 强信号关键词：命中即高置信度
_STRONG: dict[Intent, list[str]] = {
    Intent.CALCULATOR: [
        "bmi", "curb", "curb-65", "curb65", "timi", "grace", "chads", "chadsvasc",
        "mews", "gcs", "qrisk", "wells", "dvt评分", "计算", "评分", "算一下", "评估量表",
    ],
    Intent.DRUG: [
        "相互作用", "配伍", "药物", "用药", "药品", "剂量", "处方",
        "华法林", "阿司匹林", "二甲双胍", "禁忌", "重复用药",
    ],
    Intent.LITERATURE: [
        "文献", "循证", "检索", "最新研究", "pubmed", "论文", "证据等级",
        "查一下资料", "临床证据", "meta分析", "meta 分析", "随机对照",
    ],
    Intent.KNOWLEDGE: [
        "指南", "共识", "正常值", "参考值", "什么是", "如何治疗", "治疗方案",
        "科普", "标准", "hbA1c是什么意思",
    ],
    Intent.INTAKE: [
        "问诊", "采集", "挂号", "导诊", "分诊", "问几个问题", "病史采集",
    ],
}

_WEAK: dict[Intent, list[str]] = {
    Intent.CALCULATOR: ["多少分", "得分", "风险度", "危险分层"],
    Intent.DRUG: ["能一起吃吗", "换药", "停药", "副作用"],
    Intent.LITERATURE: ["最新", "研究", "证据", "数据支持"],
    Intent.KNOWLEDGE: ["怎么办", "注意什么", "饮食", "运动建议", "建议"],
    Intent.INTAKE: ["我该怎么办", "应该挂什么科"],
}


class IntentDecision:
    """一次意图判定结果，含分流依据，便于前端展示「为什么走这条链路」。"""

    def __init__(self, intent: Intent, confidence: float, reason: str, matched: str):
        self.intent = intent
        self.confidence = round(confidence, 2)
        self.reason = reason
        self.matched = matched

    @property
    def label(self) -> str:
        return _INTENT_LABEL[self.intent]

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "label": self.label,
            "confidence": self.confidence,
            "reason": self.reason,
            "matched": self.matched,
        }


# 公开标签表（供 /agent/rules 能力公示等场景使用）
INTENT_LABELS = {i.value: label for i, label in _INTENT_LABEL.items()}


def _hit(text: str, kws: list[str]) -> str:
    low = text.lower()
    for kw in kws:
        if kw.lower() in low:
            return kw
    return ""


def classify_intent(text: str) -> IntentDecision:
    """意图判定：强关键词 0.92 / 弱关键词 0.65 / 默认会诊 0.30。"""
    text = text or ""
    for intent in (Intent.CALCULATOR, Intent.DRUG, Intent.LITERATURE,
                   Intent.KNOWLEDGE, Intent.INTAKE):
        kw = _hit(text, _STRONG[intent])
        if kw:
            return IntentDecision(intent, 0.92, f"命中「{kw}」关键词", kw)
        kw = _hit(text, _WEAK[intent])
        if kw:
            return IntentDecision(intent, 0.6, f"命中「{kw}」弱信号", kw)
    # 显式点名会诊
    if _hit(text, ["会诊", "mdt", "多学科", "病例讨论", "疑难病例"]):
        return IntentDecision(Intent.CONSULT, 0.9, "明确要求多学科会诊", "会诊")
    return IntentDecision(Intent.CONSULT, 0.35, "未命中专用能力关键词，默认进入会诊", "")