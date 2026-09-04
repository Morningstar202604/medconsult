"""Agnes 内置兜底服务单元测试：摘要、专科意见、报告、追问。"""
from app.services.agnes import (
    should_use_agnes,
    should_use_sandbox,
    agnes_summarize,
    sandbox_summarize,
    agnes_specialist_opinion,
    sandbox_opinion,
    agnes_report,
    sandbox_report,
    agnes_followup,
)


# ---- 模式判断 ----

def test_should_use_agnes_when_production_no_llm():
    assert should_use_agnes(llm_configured=False, production=True) is True


def test_should_use_agnes_when_sandbox_false():
    assert should_use_agnes(llm_configured=False, production=False) is False


def test_should_use_agnes_when_llm_configured_false():
    assert should_use_agnes(llm_configured=True, production=True) is False


def test_should_use_sandbox_when_not_production():
    assert should_use_sandbox(production=False) is True


def test_should_use_sandbox_when_production_true():
    assert should_use_sandbox(production=True) is False


# ---- 摘要 ----

def test_agnes_summarize_extracts_chief():
    text = "主诉：胸痛3小时\n现病史：患者发作性胸痛"
    result = agnes_summarize(text)
    assert "胸痛3小时" in result
    assert "Agnes" in result


def test_agnes_summarize_with_all_fields():
    text = ("主诉：发热咳嗽3天\n"
            "现病史：伴咳痰，无咯血\n"
            "既往史：高血压10年\n"
            "过敏史：青霉素过敏\n"
            "实验室：WBC 12.5，CRP 45")
    result = agnes_summarize(text)
    assert "发热咳嗽3天" in result
    assert "高血压10年" in result
    assert "青霉素过敏" in result
    assert "WBC 12.5" in result


def test_sandbox_summarize_format():
    result = sandbox_summarize("胸痛3小时")
    assert "沙箱演示" in result
    assert "未调用真实模型" in result


# ---- 专科意见 ----

def test_agnes_specialist_opinion_returns_string():
    result = agnes_specialist_opinion("internal", "摘要内容", "胸痛3小时", "brief", 1)
    assert isinstance(result, str)
    assert "内科" in result or "第一轮" in result


def test_agnes_specialist_opinion_round2():
    result = agnes_specialist_opinion("internal", "摘要", "胸痛", "brief", 2)
    assert "第二轮" in result


def test_sandbox_opinion_round1():
    result = sandbox_opinion("internal", "摘要", 1)
    assert "沙箱" in result


def test_sandbox_opinion_round2():
    result = sandbox_opinion("internal", "摘要", 2)
    assert "第二轮" in result


# ---- 报告 ----

def test_agnes_report_with_chest_pain():
    result = agnes_report("摘要", "讨论记录", "胸痛3小时伴冷汗", {"missing": []}, [], [])
    assert "final_diagnosis" in result
    assert "ACS" in result.get("final_diagnosis", "") or "冠脉" in result.get("final_diagnosis", "")


def test_agnes_report_with_abdominal_pain():
    result = agnes_report("摘要", "讨论", "腹痛伴发热", {"missing": []}, [], [])
    assert "final_diagnosis" in result
    assert "阑尾" in result.get("final_diagnosis", "") or "急腹" in result.get("final_diagnosis", "")


def test_sandbox_report_is_demo():
    result = sandbox_report("示例病例", {"missing": [], "score": 3, "total": 6})
    assert result["is_demo"] is True
    assert "沙箱演示" in result["final_diagnosis"]


# ---- 追问 ----

def test_agfollowup_notes():
    result = agnes_followup("胸痛会诊报告", "注意事项")
    assert "注意事项" in result or "密切观察" in result


def test_agnes_followup_examination():
    result = agnes_followup("共识报告", "还需要做什么检查？")
    assert "检查" in result or "血常规" in result


def test_agnes_followup_default():
    result = agnes_followup("", "随便问问")
    assert isinstance(result, str)
    assert len(result) > 10
