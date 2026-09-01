"""红旗扫描与评分工具的回归测试（修复原版误判）。"""
from app.clinical import triage_scan
from app.clinical.calculators import detect_and_run


def test_chest_pain_with_sweat_is_emergent():
    hits = triage_scan("58岁男性，胸痛伴冷汗3小时，向左肩放射")
    assert hits, "应命中红旗"
    assert hits[0].severity == "emergent"


def test_plain_chest_pain_no_longer_silent():
    """原版漏报修复：纯'胸痛'至少进入 urgent。"""
    hits = triage_scan("胸痛3天，无其他特殊")
    assert hits, "纯胸痛不应静默"
    assert hits[0].severity in ("emergent", "urgent")


def test_stroke_fast():
    hits = triage_scan("左侧肢体无力1小时，言语不清")
    assert hits and hits[0].severity == "emergent"


def test_normal_text_no_flag():
    hits = triage_scan("体检咨询，无不适")
    assert hits == []


def test_curb65_urea_bug_fixed():
    """原版误判修复：'尿素氮7天后'不应计入 urea>7。"""
    # 无 mmol/L 单位 → 不计分
    r = [c for c in detect_and_run("58岁，肺炎，尿素氮复查后7天再次检查，呼吸24次/分，血压120/80，体温38.2")]
    curb = [c for c in r if c.name.startswith("CURB")]
    if curb:
        assert "尿素氮>7" not in curb[0].expr, "不应把'7天'当成尿素>7"

    # 带 mmol/L 单位 → 计分
    r2 = [c for c in detect_and_run("58岁，肺炎，尿素氮 8.2 mmol/L，呼吸26次/分，血压120/80")]
    curb2 = [c for c in r2 if c.name.startswith("CURB")]
    assert curb2 and "尿素氮>7" in curb2[0].expr


def test_calculator_unverified_flag():
    """所有自动计算必须标注未核实。"""
    r = detect_and_run("血压 120/80，身高175cm，体重70kg，58岁，血肌酐 88 μmol/L")
    assert r, "应识别到计算项"
    for c in r:
        assert c.unverified is True


def test_chadsvasc_no_treatment_advice():
    """原版把治疗建议写进工具输出；新版只给分数并提示需评估出血。"""
    r = [c for c in detect_and_run("75岁女性，房颤，高血压，糖尿病") if "CHA₂DS₂" in c.name]
    assert r
    assert "建议抗凝" not in r[0].result
    assert "出血风险" in r[0].note


def test_bmi_implausible_guarded():
    r = detect_and_run("身高 999cm，体重 5000kg")
    assert all(c.name != "体质指数 BMI" for c in r)
