"""垂直临床工具与差异化层测试：检查合理性、药物互作、分歧检测、患者版报告。"""
from app.clinical import exam_appropriateness as ea
from app.clinical import drug_interactions as di
from app.services import mdt
from app.services.patient_report import build_patient_report


# ---- 检查合理性 ----
def test_exam_chest_pain_prioritizes_ecg():
    res = ea.suggest_exams("胸痛2小时，伴冷汗")
    exams = [s["exam"] for s in res]
    assert "心电图（静息 12 导联）" in exams
    assert "心肌损伤标志物（肌钙蛋白 I/T）" in exams
    # 高优先级在前
    assert res[0]["priority"] == "high"


def test_exam_has_reason_and_not_applicable():
    res = ea.suggest_exams("头痛剧烈")
    assert res and res[0]["reason"]
    assert any(s["not_applicable"] for s in res)


def test_exam_fallback_when_no_match():
    res = ea.suggest_exams("没什么特别的，就是有点累")
    assert res and any(s["priority"] == "high" for s in res)


# ---- 药物相互作用 ----
def test_warfarin_nsaid_major():
    hits = di.check_interactions("正在吃华法林和阿司匹林")
    majors = [h for h in hits if h["severity"] == "major"]
    assert majors, hits
    assert "出血" in majors[0]["consequence"]


def test_metformin_contrast_major():
    hits = di.check_interactions("二甲双胍，明天要拍CT增强造影剂")
    assert any(h["severity"] == "major" and "乳酸" in h["consequence"] for h in hits)


def test_no_interaction_returns_empty():
    assert di.check_interactions("只吃维生素C") == []


def test_drug_english_alias():
    # 英文缩写/名也能命中（区别于纯中文分词）
    hits = di.check_interactions("on warfarin and ibuprofen")
    assert hits and any("华法林" in h["drugs"] for h in hits)


# ---- 分歧显性化 ----
def test_disagreement_detected():
    round1 = {
        "internal": "考虑急性冠脉综合征，需查肌钙蛋白",
        "surgery": "症状像主动脉夹层，建议CTA排除",
    }
    res = mdt.compute_disagreements(round1, {}, ["internal", "surgery"])
    assert res["has_disputes"] is True


def test_disagreement_stance_conflict():
    round1 = {
        "internal": "符合急性冠脉综合征表现，考虑心梗",
        "pharmacy": "不支持急性冠脉综合征，更像肺栓塞",
    }
    res = mdt.compute_disagreements(round1, {}, ["internal", "pharmacy"])
    assert res["has_disputes"] is True
    topics = [d["topic"] for d in res["disputes"]]
    assert any("急性冠脉综合征" in t for t in topics)


def test_no_disagreement_when_consensus():
    round1 = {
        "internal": "考虑急性冠脉综合征，需查肌钙蛋白",
        "cardio": "同意，支持急性冠脉综合征，建议心电图",
    }
    res = mdt.compute_disagreements(round1, {}, ["internal", "cardio"])
    assert res["has_disputes"] is False


# ---- 置信度降级 ----
def test_confidence_downgrade_when_key_missing():
    completeness = {"missing": ["辅助检查", "用药过敏"], "score": 4, "total": 6}
    conf, key = mdt._confidence_with_completeness("高", completeness)
    assert conf == "中" and "辅助检查" in key
    conf2, _ = mdt._confidence_with_completeness("高", {"missing": [], "score": 6, "total": 6})
    assert conf2 == "高"


# ---- 患者版报告 ----
def test_patient_report_plain_language():
    report = {
        "final_diagnosis": "急性冠脉综合征",
        "confidence": "中",
        "recommended_dept": "心内科",
        "key_findings": ["肌钙蛋白升高", "心电图ST段改变"],
        "plan": ["立即收入院", "抗血小板治疗"],
        "red_flags": [{"severity": "emergent", "message": "胸痛伴大汗"}],
        "disagreements": "",
        "warnings": "",
    }
    pr = build_patient_report(report, {"missing": [], "score": 6, "total": 6})
    assert "心内科" in pr.summary
    assert any("急诊" in s for s in pr.when_to_seek_care)
    assert pr.what_to_do
    assert not pr.is_demo


def test_patient_report_demo_marked():
    pr = build_patient_report({"is_demo": True}, None)
    assert pr.is_demo is True
