"""资料完备度：6 要素结构化核查。

相对原版改进：生命体征/检查等要素要求"关键词 + 具体数值/检查名"，避免
"出现'血压'两个字就算齐全"的假完备。
"""
import re

_ELEMENTS: list[tuple[str, str]] = [
    ("年龄性别", r"\d{1,3}\s*岁|\b(男|女)性|male|female"),
    ("病程时间", r"\d+\s*(分钟|小时|天|日|周|月|年)"),
    ("既往史", r"既往|病史|高血压|糖尿病|冠心病|肝炎|结核|手术史"),
    ("用药过敏", r"服药|用药|服用|口服|静滴|静注|皮下注射|过敏|对.{0,6}过敏"),
    ("辅助检查", r"(心电图|CT|MRI|B超|彩超|胸片|造影|血常规|生化|肝肾功能|肌钙蛋白|D[-—]二聚体|超声|超声心动)"),
    ("生命体征", r"(血压|体温|心率|脉搏|呼吸|血氧|SaO2)\s*[:：]?\s*\d+"),
]


def assess(text: str) -> dict:
    t = text or ""
    present, missing, hints = [], [], []
    for name, pat in _ELEMENTS:
        if re.search(pat, t):
            present.append(name)
        else:
            missing.append(name)
            hints.append(_HINTS.get(name, ""))
    return {
        "score": len(present),
        "total": len(_ELEMENTS),
        "present": present,
        "missing": missing,
        "hints": [h for h in hints if h],
    }


_HINTS = {
    "年龄性别": "请补充年龄与性别",
    "病程时间": "请说明症状持续了多久",
    "既往史": "请补充慢性病史/手术史",
    "用药过敏": "请说明当前用药与过敏史",
    "辅助检查": "请提供已有检查（心电图/化验/影像）",
    "生命体征": "请提供生命体征数值（血压/体温/心率等）",
}
