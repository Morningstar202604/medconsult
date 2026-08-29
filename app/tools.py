"""医学计算器工具：从文本中检测可计算的指标并自动计算（确定性、可复核）。"""


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
    dedup = []
    for c in out:
        key = (c["name"], c["expr"])
        if key not in seen:
            seen.add(key)
            dedup.append(c)
    return dedup
