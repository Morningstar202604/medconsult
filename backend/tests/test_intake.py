"""采集式问诊引擎测试：分类、定向追问、红旗拦截、病历生成。"""
import json
from app.clinical import intake


def test_classify_chest_pain():
    assert intake.classify_chief_complaint("我胸口闷痛了2小时") == intake.CHEST_PAIN
    assert intake.classify_chief_complaint("肚子疼得厉害") == intake.ABDOMINAL
    assert intake.classify_chief_complaint("一直发烧咳嗽") == intake.FEVER
    assert intake.classify_chief_complaint("头疼想吐") == intake.HEADACHE
    assert intake.classify_chief_complaint("咳嗽有痰") == intake.COUGH
    assert intake.classify_chief_complaint("摔了一跤") == intake.TRAUMA
    assert intake.classify_chief_complaint("就是浑身没劲") == intake.OTHER


def test_first_question_has_reason():
    st = intake.init_state("胸痛")
    q = intake.first_question(st)
    assert q is not None
    # 每个问题都必须带"为什么要问"（鉴别诊断理由）——垂直差异核心
    assert q["reason"] and len(q["reason"]) > 5
    assert q["field"] in ("nature", "onset")


def test_full_protocol_collects_soap_fields():
    st = intake.init_state("胸痛")
    total = len(st.protocol)
    # 走完全部协议问题（回答避开高危征象词，避免触发红旗拦截）
    guard = 0
    while True:
        q = intake.first_question(st) if not st.answers else None
        r = intake.apply_answer(st, "轻微隐痛，活动后略加重，休息能缓解，没有出汗，无放射，无胸闷")
        guard += 1
        assert guard < 40, "协议未收敛"
        if r["done"]:
            break
    assert st.status == "complete"
    # SOAP 关键字段应已采集
    assert "nature" in st.fields and "aggravating" in st.fields
    # 病历生成应包含主诉与现病史
    built = intake.build_record(st)
    assert built["record"]["chief_complaint"]
    assert built["record"]["history"]


def test_red_flag_interrupts_intake():
    st = intake.init_state("胸痛")
    q = intake.first_question(st)
    assert q is not None
    # 回答中出现危急征象：胸痛伴大汗（触发 emergent ACS 规则）
    r = intake.apply_answer(st, "胸痛，痛的时候冒冷汗，觉得快不行了")
    assert r["interrupt"] is True
    assert st.status == "redflag"
    assert st.flags_urgent is True
    assert any(f["severity"] == "emergent" for f in st.red_flags)
    # 中断后不应再有下一问
    assert r["next_question"] is None


def test_red_flag_severity_urgent_not_emergent():
    # 主诉"胸痛"启动即触发 urgent 拦截（initial_flags 一次性提示），非 emergent
    st = intake.init_state("胸痛")
    assert st.initial_flags, "主诉胸痛应在启动时给出 urgent 拦截提示"
    assert any(f["severity"] == "urgent" for f in st.initial_flags)
    assert st.flags_urgent is False
    # 后续普通回答（含"胸闷"但无新增危险词）不重复中断
    r = intake.apply_answer(st, "就有点胸闷，不严重")
    assert r["interrupt"] is False
    assert st.status != "redflag"


def test_protocol_persistable_json():
    st = intake.init_state("腹痛")
    protocol = [dict(q) for q in st.protocol]
    s = json.dumps(protocol, ensure_ascii=False)
    assert "reason" in s
    # 还原
    restored = intake.state_from_json("腹痛", "abdominal", {}, [], json.loads(s),
                                      "collecting", [], False)
    assert restored.protocol == protocol


def test_build_record_encounter_fields():
    st = intake.init_state("咳嗽")
    while not intake.apply_answer(st, "干咳，伴低热，有吸烟史").get("done") and not st.status == "redflag":
        intake.apply_answer(st, "没有咯血")
    built = intake.build_record(st)
    ef = built["encounter_fields"]
    assert set(ef.keys()) == {"chief_complaint", "history", "meds", "exams", "vitals"}


def test_red_flag_fires_on_fragment_answer():
    """逐轮回答为片段（无"胸痛"前缀）也应结合主诉命中红旗，杜绝漏检。"""
    st = intake.init_state("胸痛2小时")
    # 主诉含胸痛，回答片段"放射到左肩、出冷汗"独立看无"胸痛"二字
    r = intake.apply_answer(st, "放射到左肩，出冷汗")
    assert r["interrupt"] is True
    assert any(f["severity"] == "emergent" for f in st.red_flags)
    # 不含任何危险词的普通回答不误拦
    st2 = intake.init_state("胸痛2小时")
    r2 = intake.apply_answer(st2, "轻微隐痛，无放射，无出汗")
    assert r2["interrupt"] is False
