"""医学计算器工具：从文本中检测可计算的指标并自动计算（确定性、可复核）。"""
import re


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def map_calc(sys_, dia):
    try:
        return round((float(sys_) + 2 * float(dia)) / 3, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def bmi(w_kg, h_cm):
    try:
        w, h = float(w_kg), float(h_cm) / 100
        if w <= 0 or h <= 0:
            return None
        return round(w / (h * h), 1)
    except (TypeError, ValueError):
        return None


def crcl(age, w_kg, is_female, scr_umol):
    """Cockcroft-Gault 肌酐清除率 (mL/min)。scr_umol: 血肌酐 μmol/L"""
    try:
        age, w, scr = float(age), float(w_kg), float(scr_umol)
        if age <= 0 or w <= 0 or scr <= 0:
            return None
        v = (140 - age) * w * (0.85 if is_female else 1.0) / (0.818 * scr)
        return round(v, 1)
    except (TypeError, ValueError):
        return None


def detect_and_run(text):
    """扫描文本，返回 [{"tool","name","expr","result"}]；结果均为确定性计算。"""
    import re
    out, seen = [], set()
    t = text or ""

    # 平均动脉压 MAP：血压 120/80
    for m in re.finditer(r"血压[^0-9]{0,6}(\d{2,3})\s*[/／]\s*(\d{2,3})", t):
        v = map_calc(m.group(1), m.group(2))
        if v:
            out.append({"tool": "med_calculator", "name": "平均动脉压(MAP)",
                        "expr": "血压 {}/{}".format(m.group(1), m.group(2)),
                        "result": "{} mmHg".format(v)})

    # BMI：身高 xxx cm / xxx m，体重 xxx kg
    mh = re.search(r"身高\s*([\d.]+)\s*(cm|厘米|m|米)", t)
    mw = re.search(r"体重\s*([\d.]+)\s*(kg|公斤|千克)", t)
    if mh and mw:
        h = _f(mh.group(1))
        if mh.group(2) in ("m", "米"):
            h = h * 100 if h and h < 3 else h
        v = bmi(mw.group(1), h)
        if v:
            out.append({"tool": "med_calculator", "name": "BMI",
                        "expr": "体重{}kg / 身高{}cm".format(mw.group(1), h),
                        "result": "{} kg/m²".format(v)})

    # 肌酐清除率：年龄 + 体重 + 性别 + 血肌酐 μmol/L
    ma = re.search(r"(\d{1,3})\s*岁", t)
    mscr = re.search(r"(?:血肌酐|肌酐)\s*([\d.]+)\s*(?:μmol|umol|umo|µmol)", t)
    if ma and mscr and mw:
        female = bool(re.search(r"女", t)) and not bool(re.search(r"男性|男性患者", t))
        v = crcl(ma.group(1), mw.group(1), female, mscr.group(1))
        if v:
            out.append({"tool": "med_calculator", "name": "肌酐清除率(CrCl, Cockcroft-Gault)",
                        "expr": "年龄{}岁/体重{}kg/血肌酐{}μmol/L".format(ma.group(1), mw.group(1), mscr.group(1)),
                        "result": "{} mL/min".format(v)})

    out += _detect_scores(t)
    dedup = []
    for c in out:
        key = (c["name"], c["expr"])
        if key not in seen:
            seen.add(key)
            dedup.append(c)
    return dedup


# ---------------------------------------------------------------------------
# 临床评分工具（确定性规则，触发条件保守：需出现对应疾病上下文，避免误算）
# ---------------------------------------------------------------------------

def _has(t, *patterns):
    return any(re.search(p, t) for p in patterns)


def _detect_scores(t):
    res = []
    age_m = re.search(r"(\d{1,3})\s*岁", t)
    age = int(age_m.group(1)) if age_m else None

    # CHA₂DS₂-VASc（房颤患者卒中风险）：心衰/高血压/糖尿病/卒中史/血管疾病
    if age is not None and _has(t, r"房颤|心房(纤维性)?颤动|AF\b"):
        score = 0
        items = []
        if _has(t, r"心衰|心力衰竭|心功能不全|LVEF"):
            score += 1; items.append("心衰+1")
        if _has(t, r"高血压"):
            score += 1; items.append("高血压+1")
        if age >= 75:
            score += 2; items.append("年龄≥75(+2)")
        elif age >= 65:
            score += 1; items.append("年龄65-74(+1)")
        if _has(t, r"糖尿病"):
            score += 1; items.append("糖尿病+1")
        # 卒中/栓塞史需明确"既往/病史"语义，避免"评估卒中风险"这类表述误判
        if _has(t, r"卒中史|中风史|栓塞史|TIA病史|脑梗(死)?史|(既往|病史|曾经|去年|前年|今年|\d+年前|曾患)[^。；]{0,12}(卒中|中风|TIA|脑梗|栓塞)"):
            score += 2; items.append("卒中/栓塞史+2")
        if _has(t, r"心梗|心肌梗死|外周动脉|主动脉|斑块"):
            score += 1; items.append("血管疾病+1")
        female = bool(re.search(r"女", t)) and not bool(re.search(r"男", t))
        if female:
            score += 1; items.append("女性+1")
        res.append({"tool": "med_calculator", "name": "CHA₂DS₂-VASc 评分",
                    "expr": "；".join(items) if items else "仅年龄性别",
                    "result": "{} 分{}".format(score, "（≥2 分建议抗凝，男性≥1 分考虑抗凝）" if score else "（低危）")})

    # CURB-65（社区获得性肺炎严重程度）
    if _has(t, r"肺炎|community.acquired"):
        score, items = 0, []
        if _has(t, r"意识模糊|意识障碍|谵妄|confusion"):
            score += 1; items.append("意识模糊+1")
        if _has(t, r"尿素氮|BUN") and re.search(r"尿素氮[^0-9]{0,6}([7-9]|\d{2,})", t):
            score += 1; items.append("尿素氮>7mmol/L+1")
        if re.search(r"呼吸[^0-9]{0,8}([3-9]\d|30)\s*次", t):
            score += 1; items.append("呼吸≥30次/分+1")
        sbp = re.search(r"收缩压[^0-9]{0,6}(\d{2,3})", t)
        if sbp and int(sbp.group(1)) < 90:
            score += 1; items.append("收缩压<90+1")
        dbp = re.search(r"舒张压[^0-9]{0,6}(\d{2,3})", t)
        if dbp and int(dbp.group(1)) <= 60:
            score += 1; items.append("舒张压≤60+1")
        if age is not None and age >= 65:
            score += 1; items.append("年龄≥65+1")
        advice = ["0-1分：门诊治疗", "2分：住院或密切随访", "3分：住院治疗", "4-5分：住院/ICU，评估重症"][
            min(3, 0 if score <= 1 else 1 if score == 2 else 2 if score == 3 else 3)]
        res.append({"tool": "med_calculator", "name": "CURB-65 评分",
                    "expr": "；".join(items) if items else "各项均为阴性",
                    "result": "{} 分（{}）".format(score, advice)})

    # Wells 评分（DVT/肺栓塞临床可能性）
    if _has(t, r"DVT|深静脉血栓|肺栓塞|PE\b|静脉血栓"):
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
        res.append({"tool": "med_calculator", "name": "Wells 评分(DVT/PE)",
                    "expr": "；".join(items) if items else "各项均为阴性",
                    "result": "{} 分（{}）".format(score, level)})
    return res
