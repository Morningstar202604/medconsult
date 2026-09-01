"""RAG 阈值检索与报告结构校验测试。"""
from app.llm.validate import extract_json, validate_report
from app.rag import clear, index_doc, search


def test_rag_threshold_filters_irrelevant():
    clear()
    index_doc("房颤指南", "房颤患者抗凝治疗：CHA2DS2-VASc评分用于评估卒中风险，华法林需要监测INR")
    index_doc("儿科营养", "婴儿配方奶粉的冲调比例与温度控制说明")
    # 与房颤完全无关的查询：不应命中（低于阈值）
    hits = search("如何冲调婴儿奶粉", k=5)
    assert all(h["doc"] != "房颤指南" for h in hits)


def test_rag_finds_relevant():
    hits = search("房颤抗凝 CHA2DS2 卒中风险", k=5)
    assert any(h["doc"] == "房颤指南" for h in hits)


def test_report_json_parsing_fence():
    raw = '```json\n{"final_diagnosis":"ACS","confidence":"高","recommended_dept":"心内科","key_findings":["a"],"plan":["b"],"red_flags":[],"disagreements":"无","warnings":"仅供参考"}\n```'
    data = extract_json(raw)
    assert data is not None
    rep = validate_report(data)
    assert rep is not None
    assert rep.final_diagnosis == "ACS"


def test_report_rejects_missing_fields():
    data = {"final_diagnosis": "X"}  # 缺必填之外的字段会默认，confidence 默认
    rep = validate_report(data)
    assert rep is not None


def test_report_rejects_garbage():
    assert extract_json("not json at all") is None
