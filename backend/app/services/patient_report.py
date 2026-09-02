"""患者版报告（双视角差异化）：专业报告 → 患者易懂版本。

通用 agent 的报告"能看懂"；临床 agent 必须"患者也能看懂、也知道什么时候必须回医院"。
- 确定性模板优先（专业结论→通俗解释 + 行动清单 + 就医警示）。
- 可选 LLM 增强（配置模型时对长段做更自然的通俗改写）。
"""
from __future__ import annotations
import json
from dataclasses import dataclass


_CONFIDENCE_PLAIN = {"高": "把握较大", "中": "有一定把握", "低": "需进一步检查确认"}
_RISK_PLAIN = {
    "emergent": "⚠️ 有情况需要立即去急诊，不要等待！",
    "urgent": "尽快去医院就诊评估",
    "review": "需要关注，建议近期就诊",
}


def _plain_chief(flag: dict) -> str:
    sev = flag.get("severity", "review")
    msg = flag.get("message", "")
    return f"{_RISK_PLAIN.get(sev, '需关注')}：{msg}"


@dataclass
class PatientReport:
    summary: str                 # 一句话结论
    what_it_may_be: str          # 可能是什么
    what_to_do: list[str]        # 行动清单
    when_to_seek_care: list[str] # 什么情况马上去医院
    questions_to_ask: list[str]  # 就诊时问医生的问题
    is_demo: bool = False


def build_patient_report(report: dict, completeness: dict | None = None,
                         encounter_text: str = "") -> PatientReport:
    """由专业报告生成患者版。纯确定性实现（无 LLM 依赖）。"""
    diag = (report.get("final_diagnosis") or "").strip()
    conf = report.get("confidence") or "中"
    plain_conf = _CONFIDENCE_PLAIN.get(conf, conf)
    dept = report.get("recommended_dept") or "相应专科门诊"

    if report.get("is_demo"):
        return PatientReport(
            summary="这是沙箱演示报告，不是真实诊断结果，仅供参考流程展示。",
            what_it_may_be="演示模式未调用真实模型，未生成真实诊断。",
            what_to_do=["如需真实评估，请联系医生完成正式就诊与检查。"],
            when_to_seek_care=["出现任何持续加重的不适，请及时就医。"],
            questions_to_ask=["请医生解释我的情况需要做哪些检查。"],
            is_demo=True,
        )

    # 一句话结论
    if diag:
        summary = f"AI 综合意见认为，您的情况（{plain_conf}）可能是：{diag}。"
    else:
        summary = "基于目前信息，AI 尚未形成明确诊断，需要进一步检查确认。"
    if dept:
        summary += f"建议到{dept}就诊。"

    # 主要依据 → 通俗说明
    findings = report.get("key_findings") or []
    what_it_may_be = "；".join(str(f) for f in findings[:3]) or "信息有限，需进一步检查。"

    # 行动清单（诊疗方案）
    plan = report.get("plan") or []
    to_do = [str(p) for p in plan[:5]]
    if not to_do:
        to_do = ["带上现有检查资料，到医院就诊明确诊断。"]

    # 就医警示（红旗）
    seek: list[str] = []
    red_flags = report.get("red_flags") or []
    for rf in red_flags:
        if isinstance(rf, dict):
            seek.append(_plain_chief(rf))
        elif isinstance(rf, str):
            seek.append(f"需及时就医：{rf}")
    if not seek:
        seek = ["如果症状明显加重、出现新的严重不适，请立即就医或拨打 120。"]

    # 问医生的问题
    ask = [
        "我这个情况还需要做什么检查来确认？",
        "这些药该怎么吃？有没有需要注意的副作用？",
    ]
    if completeness and completeness.get("missing"):
        ask.append(f"就诊时请补充完善：{'、'.join(completeness['missing'])}。")

    return PatientReport(
        summary=summary,
        what_it_may_be=what_it_may_be,
        what_to_do=to_do,
        when_to_seek_care=seek,
        questions_to_ask=ask,
        is_demo=False,
    )


def to_dict(pr: PatientReport) -> dict:
    return pr.__dict__
