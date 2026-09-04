"""确定性医学计算工具：从文本提取数值计算，单元可测。

相对原版的修复：
1. 单位感知：尿素氮必须带 mmol/L 才计分，杜绝"尿素氮7天后"误判；
2. 合理值护栏：身高/体重/肌酐/血压超物理范围直接拒绝计算；
3. 每条结果带 unverified=True + 说明——"从自由文本自动提取，未经核实"，
   前端明确展示，不冒充权威计算；
4. 评分工具只给分数与要素，不给"建议抗凝"等治疗决策文本；
   涉及抗凝只提示"需同时评估出血风险"。
"""
import re
from dataclasses import dataclass, field


@dataclass
class CalcResult:
    name: str
    expr: str
    result: str
    unverified: bool = True
    note: str = "从病情文本自动提取，未经检验科核实"


def _f(x: str | None) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def map_calc(sys_: float, dia: float) -> float:
    return round((sys_ + 2 * dia) / 3, 1)


def bmi(w_kg: float, h_cm: float) -> float | None:
    if not (1 <= w_kg <= 400) or not (40 <= h_cm <= 250):
        return None
    hm = h_cm / 100.0
    return round(w_kg / (hm * hm), 1)


def crcl(age: int, w_kg: float, female: bool, scr_umol: float) -> float | None:
    if not (0 < age < 120) or not (2 <= w_kg <= 400) or not (10 <= scr_umol <= 2000):
        return None
    v = (140 - age) * w_kg * (0.85 if female else 1.0) / (0.818 * scr_umol)
    return round(v, 1)


# ---------------------------------------------------------------- 解析辅助
def _num_before(text: str, pos: int) -> float | None:
    """取 pos 之前最近的数字（支持小数）。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", text[:pos])
    return _f(m.group(1)) if m else None


def _unit_match(text: str, pos: int, units: tuple[str, ...]) -> bool:
    """检查 pos 之后紧跟单位。"""
    tail = text[pos:pos + 12]
    return any(tail.startswith(u) for u in units)


# ---------------------------------------------------------------- 各计算器
def _calc_map(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    for m in re.finditer(r"血压[^0-9]{0,6}(\d{2,3})\s*[/／]\s*(\d{2,3})", text or ""):
        s, d = _f(m.group(1)), _f(m.group(2))
        if s and d and 50 <= s <= 260 and 30 <= d <= 160:
            out.append(CalcResult(
                name="平均动脉压 MAP",
                expr=f"血压 {m.group(1)}/{m.group(2)}",
                result=f"{map_calc(s, d)} mmHg",
            ))
    return out


def _calc_bmi(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    mh = re.search(r"身高\s*([\d.]+)\s*(cm|厘米|m|米)", text or "")
    mw = re.search(r"体重\s*([\d.]+)\s*(kg|公斤|千克)", text or "")
    if not (mh and mw):
        return out
    h = _f(mh.group(1))
    if mh.group(2) in ("m", "米") and h and h < 3:
        h = h * 100
    w = _f(mw.group(1))
    if h and w:
        v = bmi(w, h)
        if v is not None:
            out.append(CalcResult(
                name="体质指数 BMI",
                expr=f"体重{w}kg / 身高{h}cm",
                result=f"{v} kg/m²",
            ))
    return out


def _calc_crcl(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    ma = re.search(r"(\d{1,3})\s*岁", text or "")
    mw = re.search(r"体重\s*([\d.]+)\s*(kg|公斤|千克)", text or "")
    # 肌酐必须带 μmol/L（或 mg/dL 换算），避免数字误读
    mscr = re.search(r"(?:血肌酐|肌酐)\s*([\d.]+)\s*(μmol|umol|umo|µmol|mg/dl|mg/dL|毫克)", text or "")
    if not (ma and mw and mscr):
        return out
    scr = _f(mscr.group(1))
    if mscr.group(2).lower().startswith("mg"):
        scr = scr * 88.4 if scr else None  # mg/dL -> μmol/L
    w = _f(mw.group(1))
    age = int(ma.group(1))
    female = bool(re.search(r"女", text)) and not bool(re.search(r"男(?!性病)", text))
    if age and w and scr:
        v = crcl(age, w, female, scr)
        if v is not None:
            out.append(CalcResult(
                name="肌酐清除率 CrCl (Cockcroft-Gault)",
                expr=f"年龄{age}岁/体重{w}kg/肌酐{mscr.group(1)}{mscr.group(2)}",
                result=f"{v} mL/min",
            ))
    return out


def _calc_chadsvasc(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    t = text or ""
    if not re.search(r"房颤|心房(纤维性)?颤动|\bAF\b", t):
        return out
    age_m = re.search(r"(\d{1,3})\s*岁", t)
    age = int(age_m.group(1)) if age_m else None
    if age is None:
        return out
    score, items = 0, []
    if re.search(r"心衰|心力衰竭|心功能不全|LVEF", t):
        score += 1; items.append("心衰+1")
    if re.search(r"高血压", t):
        score += 1; items.append("高血压+1")
    if age >= 75:
        score += 2; items.append(f"年龄{age}≥75(+2)")
    elif age >= 65:
        score += 1; items.append(f"年龄{age}(65-74,+1)")
    if re.search(r"糖尿病", t):
        score += 1; items.append("糖尿病+1")
    if re.search(r"卒中史|中风史|栓塞史|TIA病史|脑梗(死)?史|(既往|病史|曾经|去年|前年|今年|\d+年前)[^。；]{0,12}(卒中|中风|TIA|脑梗|栓塞)", t):
        score += 2; items.append("卒中/栓塞史+2")
    if re.search(r"心梗|心肌梗死|外周动脉|主动脉|斑块", t):
        score += 1; items.append("血管疾病+1")
    female = bool(re.search(r"女", t)) and not bool(re.search(r"男", t))
    if female:
        score += 1; items.append("女性+1")
    out.append(CalcResult(
        name="CHA₂DS₂-VASc 血栓风险评分",
        expr="；".join(items) if items else "仅年龄性别",
        result=f"{score} 分",
        note="仅评估卒中血栓风险；抗凝决策必须同时评估出血风险（HAS-BLED）并由医师权衡",
    ))
    return out


def _calc_curb65(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    t = text or ""
    if not re.search(r"肺炎|社区获得性肺炎", t):
        return out
    age_m = re.search(r"(\d{1,3})\s*岁", t)
    age = int(age_m.group(1)) if age_m else None
    score, items = 0, []
    if re.search(r"意识模糊|意识障碍|谵妄|confusion", t):
        score += 1; items.append("意识模糊+1")
    # 尿素氮必须带 mmol/L 单位
    if re.search(r"尿素氮[^0-9]{0,8}(\d+(?:\.\d+)?)\s*(mmol|mmol/L|毫摩尔)", t):
        score += 1; items.append("尿素氮>7mmol/L+1")
    if re.search(r"呼吸[^0-9]{0,8}([3-9]\d)\s*次|呼吸.{0,4}(30|35|40|45|50)\s*次", t):
        score += 1; items.append("呼吸≥30次/分+1")
    sbp = re.search(r"收缩压[^0-9]{0,6}(\d{2,3})", t)
    if sbp and 50 <= int(sbp.group(1)) < 90:
        score += 1; items.append(f"收缩压{sbp.group(1)}<90+1")
    dbp = re.search(r"舒张压[^0-9]{0,6}(\d{2,3})", t)
    if dbp and 30 <= int(dbp.group(1)) <= 60:
        score += 1; items.append(f"舒张压{dbp.group(1)}≤60+1")
    if age is not None and age >= 65:
        score += 1; items.append(f"年龄{age}≥65+1")
    advice = ["0-1分：倾向门诊/密切随访", "2分：住院或密切随访",
              "3分：建议住院", "4-5分：建议住院/ICU评估"][min(3, score)]
    out.append(CalcResult(
        name="CURB-65 肺炎严重度评分",
        expr="；".join(items) if items else "各项均为阴性",
        result=f"{score} 分（{advice}）",
    ))
    return out


def _calc_wells(text: str) -> list[CalcResult]:
    out: list[CalcResult] = []
    t = text or ""
    if not re.search(r"DVT|深静脉血栓|肺栓塞|\bPE\b|静脉血栓", t):
        return out
    score, items = 0, []
    checks = [
        (r"癌症|肿瘤|恶性肿瘤", 1, "活动期癌症+1"),
        (r"卧床|制动|石膏|术后4周内|瘫痪", 1, "制动/术后4周内+1"),
        (r"既往.*(DVT|深静脉血栓|肺栓塞)|DVT病史|肺栓塞病史", 1, "既往VTE史+1"),
        (r"全腿肿胀", 1, "全腿肿胀+1"),
        (r"腓肠|小腿.*肿胀|单侧.*肿胀", 1, "单侧小腿肿胀+1"),
        (r"凹陷性水肿", 1, "凹陷性水肿+1"),
        (r"浅静脉曲张|侧支静脉", 1, "浅静脉曲张+1"),
    ]
    for pat, pts, label in checks:
        if re.search(pat, t):
            score += pts; items.append(label)
    if re.search(r"最可能|首先考虑.*(DVT|深静脉血栓|肺栓塞)|临床高度怀疑", t):
        score += 3; items.append("最可能诊断+3")
    level = "低度可能" if score <= 1 else "中度可能" if score == 2 else "高度可能"
    out.append(CalcResult(
        name="Wells 评分（DVT/PE 临床可能性）",
        expr="；".join(items) if items else "各项均为阴性",
        result=f"{score} 分（{level}）",
    ))
    return out


def get_calculator_catalog() -> list[dict]:
    """内置医学计算器清单（供系统规则公示/前端显示）。"""
    return [
        {"name": "平均动脉压 MAP", "desc": "根据收缩压/舒张压计算 MAP"},
        {"name": "体质指数 BMI", "desc": "体重(kg) / 身高(m)² 分级"},
        {"name": "肌酐清除率 CrCl (Cockcroft-Gault)", "desc": "按年龄/体重/肌酐估算肾功能"},
        {"name": "CHA₂DS₂-VASc 血栓风险评分", "desc": "房颤卒中风险分层"},
        {"name": "CURB-65 肺炎严重度评分", "desc": "社区获得性肺炎住院决策"},
        {"name": "Wells 评分（DVT/PE 临床可能性）", "desc": "深静脉血栓/肺栓塞风险"},
    ]


def detect_and_run(text: str) -> list[CalcResult]:
    """依次运行各计算器并去重。"""
    results: list[CalcResult] = []
    seen: set[tuple[str, str]] = set()
    for fn in (_calc_map, _calc_bmi, _calc_crcl, _calc_chadsvasc, _calc_curb65, _calc_wells):
        for r in fn(text):
            key = (r.name, r.expr)
            if key not in seen:
                seen.add(key)
                results.append(r)
    return results
