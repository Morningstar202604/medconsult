"""检查合理性规则引擎（垂直临床 agent 工具层差异化）。

通用 agent 只会"推荐检查"；这里把"建议检查"变成可审计的临床决策：
- 对主诉/症状判定：必要检查（高优先）、可选检查（中）、不适用/待定（低）。
- 每条建议带"为什么做"（对应鉴别诊断）与"不适用情形"（防止过度检查）。
- 与红旗/计算器同走 tool_call_logs 审计。

本模块为确定性规则（无需 LLM），规则聚焦常见急慢症，真实场景以指南为准。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class ExamSuggestion:
    exam: str                    # 检查项目
    priority: str                # high|medium|low
    reason: str                  # 为什么做（对应鉴别）
    not_applicable: str = ""     # 不适用情形
    matched: str = ""            # 命中的主诉/症状原文


# (触发关键词, 建议列表)
_RULES: list[tuple[list[str], list[ExamSuggestion]]] = [
    (
        [r"胸[痛闷压]", r"心前区", r"胸闷"],
        [
            ExamSuggestion("心电图（静息 12 导联）", "high", "鉴别急性冠脉综合征/心律失常的基础检查，10 分钟内可完成", "既往已做且结果明确可跳过", ""),
            ExamSuggestion("心肌损伤标志物（肌钙蛋白 I/T）", "high", "ACS 的核心生物标志物，胸痛伴冷汗/放射时必查", "无症状且年龄<40、低危人群可评估后决定", ""),
            ExamSuggestion("胸部 CT 血管成像（CTA）", "medium", "胸痛呈撕裂样/放射后背、血压不对称时排除主动脉夹层", "肾功能不全者需评估造影剂风险", ""),
            ExamSuggestion("D-二聚体", "medium", "伴呼吸困难/单侧下肢肿痛时排除肺栓塞", "低临床概率者阳性预测价值低", ""),
        ],
    ),
    (
        [r"腹[痛胀]", r"肚子", r"胃痛", r"右下腹", r"脐周"],
        [
            ExamSuggestion("腹部体格检查 + 生命体征", "high", "急腹症首诊必做，评估腹膜刺激征（反跳痛/肌紧张）", "", ""),
            ExamSuggestion("血常规 + CRP", "high", "判断感染/炎症，支持阑尾炎、胆囊炎等外科急症判断", "", ""),
            ExamSuggestion("腹部 CT（平扫或增强）", "medium", "腹痛定位不清、怀疑穿孔/胰腺炎/主动脉瘤时", "育龄女性先查尿 hCG 排除妊娠", ""),
            ExamSuggestion("血淀粉酶/脂肪酶", "medium", "上腹痛放射背部、怀疑急性胰腺炎时", "", ""),
        ],
    ),
    (
        [r"头痛", r"头疼"],
        [
            ExamSuggestion("神经查体 + 血压测量", "high", "评估神经系统定位体征与高血压急症", "", ""),
            ExamSuggestion("头颅 CT（平扫）", "high", "突发剧烈头痛（雷击样/最痛一次）时排除蛛网膜下腔出血", "慢性搏动性偏头痛典型者可不急诊做", ""),
            ExamSuggestion("头颅 MRI", "medium", "慢性头痛伴神经功能缺损、怀疑颅内占位/静脉窦血栓时", "急症首选 CT，MRI 不用于急诊", ""),
        ],
    ),
    (
        [r"发热", r"发烧", r"高热"],
        [
            ExamSuggestion("血常规 + CRP/PCT", "high", "区分细菌/病毒/非感染性发热，指导抗生素决策", "", ""),
            ExamSuggestion("尿常规", "medium", "老年/儿童发热不明原因时排查泌尿系感染", "", ""),
            ExamSuggestion("胸片", "medium", "伴咳嗽咳痰、疑下呼吸道感染时", "症状轻微且年轻可观察", ""),
            ExamSuggestion("血培养（寒战时）", "medium", "伴寒战、疑脓毒症时，抗生素前留取", "门诊轻症发热常规不查", ""),
        ],
    ),
    (
        [r"咳嗽", r"咳痰", r"干咳"],
        [
            ExamSuggestion("胸片（正侧位）", "high", "持续咳嗽/伴发热气促时评估肺炎、肺结核", "普通感冒早期无气促可观察 48h", ""),
            ExamSuggestion("血常规 + CRP", "medium", "鉴别细菌感染与病毒感染", "", ""),
            ExamSuggestion("痰培养 + 药敏", "medium", "黄脓痰/慢性咳痰、疑似细菌感染且反复时", "初治轻症不常规做", ""),
        ],
    ),
    (
        [r"外伤", r"摔伤", r"撞伤", r"跌", r"骨折", r"出血"],
        [
            ExamSuggestion("受伤部位 X 线", "high", "评估骨折/脱位，疼痛无法负重时必查", "轻伤无压痛无肿胀可临床观察", ""),
            ExamSuggestion("伤口清创与破伤风评估", "high", "开放性伤口按污染程度决定清创与破伤风预防", "", ""),
            ExamSuggestion("头颅 CT（外伤伴意识障碍）", "high", "头部外伤伴意识丧失/呕吐/逆行性遗忘时排除颅内出血", "意识清楚、轻症可观察", ""),
            ExamSuggestion("B 超/CT（胸腹内脏损伤）", "medium", "高处坠落/高能量撞击疑内脏出血时", "", ""),
        ],
    ),
]

_FALLBACK: list[ExamSuggestion] = [
    ExamSuggestion("生命体征测量", "high", "任何主诉的客观基线", "", ""),
    ExamSuggestion("血常规", "medium", "感染/贫血等常见病因初筛", "", ""),
]


def suggest_exams(text: str) -> list[dict]:
    """对主诉/病情文本给出检查建议（带优先级/理由/不适用情形）。"""
    t = text or ""
    out: list[ExamSuggestion] = []
    seen: set[str] = set()
    for kws, suggestions in _RULES:
        hit = next((k for k in kws if re.search(k, t)), None)
        if hit:
            for s in suggestions:
                if s.exam not in seen:
                    seen.add(s.exam)
                    s.matched = hit
                    out.append(s)
    if not out:
        for s in _FALLBACK:
            if s.exam not in seen:
                seen.add(s.exam)
                out.append(s)
    # 优先级排序
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda s: order[s.priority])
    return [s.__dict__ for s in out]


def summary_text(suggestions: list[dict]) -> str:
    """供证据链/事件展示的摘要文本。"""
    if not suggestions:
        return "暂无明确检查建议"
    parts = []
    for s in suggestions:
        tag = {"high": "建议必查", "medium": "建议考虑", "low": "可选"}[s["priority"]]
        line = f"{tag}：{s['exam']}（{s['reason']}"
        if s.get("not_applicable"):
            line += f"；不适用：{s['not_applicable']}"
        parts.append(line + "）")
    return "；".join(parts)
