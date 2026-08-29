"""MDT 多学科会诊 pipeline.

流程：用户提交病情描述 -> 平台整理病历摘要 -> 各专科专家依次发表意见
-> 交叉讨论（互相看到彼此观点后补充/反驳）-> 主持人 Agent 汇总共识报告。

mock 模式：脚本生成（如关联病例库病例则围绕该病例标准答案收敛）。
llm  模式：每个专科用真实模型独立推理，讨论轮看到彼此意见。
"""
import json
import re

from . import cases as cases_mod
from . import config as app_config
from . import library
from . import llm
from . import rag
from . import tools as toolmod

SPECIALTIES = {
    "internal":   {"name": "内科专家",     "emoji": "🫀"},
    "surgery":    {"name": "外科专家",     "emoji": "🦴"},
    "pharmacy":   {"name": "药学专家",     "emoji": "💊"},
    "labimaging": {"name": "影像与检验专家", "emoji": "🩻"},
    "neurology":  {"name": "神经内科专家",  "emoji": "🧠"},
    "cardio":     {"name": "心内科专家",    "emoji": "❤️"},
    "pediatrics": {"name": "儿科专家",     "emoji": "🧒"},
    "obgyn":      {"name": "妇产科专家",    "emoji": "🤰"},
}
DEFAULT_SPECIALTIES = ["internal", "surgery", "pharmacy", "labimaging"]


def _cfg(settings):
    s = settings or {}
    specs = s.get("mdt_specialties") or DEFAULT_SPECIALTIES
    specs = [k for k in specs if k in SPECIALTIES] or DEFAULT_SPECIALTIES
    rounds = 2 if int(s.get("mdt_rounds") or 2) >= 2 else 1
    base = {
        "specialties": specs,
        "rounds": rounds,
        "temperature": float(s.get("temperature") or 0.3),
        "max_tokens": int(s.get("max_tokens") or 700),
        "timeout": float(s.get("request_timeout") or 120),
        "moderator_prompt": (s.get("moderator_prompt") or "").strip() or None,
        "spec_style": s.get("spec_style") or "brief",
        "tool_doc_search": s.get("tool_doc_search") is not False,
        "tool_calculator": s.get("tool_calculator") is not False,
    }
    d = app_config.llm_defaults()
    base["api_key"] = (s.get("api_key") or "").strip() or d.get("api_key")
    base["base_url"] = (s.get("base_url") or "").strip() or d.get("base_url")
    default_model = (s.get("model") or "").strip() or d.get("model") or "gpt-4o-mini"
    base["moderator_model"] = (s.get("moderator_model") or "").strip() or default_model
    if s.get("mode") == "llm" and base["api_key"]:
        base["llm"] = True
    else:
        base["llm"] = False
    return base


def _zh_demographics(text):
    if not text:
        return "患者"
    m = re.match(r"\s*(\d+)\s*岁\s*(男|女)", text)
    if m:
        return "{}岁{}性".format(m.group(1), m.group(2))
    return text


def _summarize(text, case=None):
    """整理病历摘要（mock：结构化排版；llm：模型生成）。"""
    head = []
    if case is not None:
        head.append("【病例来源】平台病例库 {} #{}".format(case.dataset, case.id + 1))
        if case.demographics:
            head.append("【基本信息】" + _zh_demographics(case.demographics))
        hist = case.patient_info.get("History") if isinstance(case.patient_info, dict) else ""
        if hist:
            head.append("【现病史】" + str(hist)[:300])
        if case.tests:
            head.append("【已有检查】" + "；".join(list(case.flattened_tests().keys())[:6]))
    head.append("【用户提交】" + text.strip()[:600])
    return "\n".join(head)


# ---------------------------------------------------------------------------
# mock 生成
# ---------------------------------------------------------------------------

def _mock_opinion(spec, case, text, summary):
    key = case.diagnosis if case is not None else ""
    demo = _zh_demographics(case.demographics) if case is not None else ""
    if spec == "internal":
        if key:
            return ("从内科角度：患者（{}）以本次提交的症状为主要表现，结合现有资料，"
                    "首先考虑「{}」，需注意与其他常见内科疾病鉴别，建议按下方检查计划完善评估后明确。").format(demo or "情况如摘要", key)
        return "从内科角度：结合摘要，症状暂无单一指向性，建议先完善血常规、生化、心电图等基础检查，再聚焦鉴别诊断。"
    if spec == "surgery":
        if key:
            return ("外科意见：目前摘要中未见急腹症或明确手术指征，倾向{}方向保守诊治；"
                    "若后续出现病情进展再评估干预时机。").format("内科方案（{}）".format(key) if key else "内科")
        return "外科意见：暂无手术指征描述，建议先行内科评估，排除外科情况后再定。"
    if spec == "pharmacy":
        return ("药学意见：明确诊断前不建议自行长期用药；确诊后用药需注意剂量个体化、"
                "药物相互作用与肝肾功能，建议由主治医生开具处方并随访。")
    if spec == "labimaging":
        if case is not None and case.tests:
            names = list(case.flattened_tests().keys())
            return "影像与检验意见：建议优先完善：{}；已有的相关检查结果可供参考。".format("、".join(names[:3]))
        return "影像与检验意见：建议完善常规实验室检查与相关部位影像学检查，为临床提供客观依据。"
    name = SPECIALTIES.get(spec, {}).get("name", spec)
    return "{}意见：同意上述分析，建议结合专科查体进一步评估。".format(name)


def _mock_response(spec, others, case):
    key = case.diagnosis if case is not None else ""
    first = others[0] if others else "内科"
    if spec == "pharmacy":
        return "同意{}的分析。补充一点：若确诊{}，起始用药应小剂量观察，并告知患者常见不良反应与复诊指征。".format(first, key or "相关疾病")
    if spec == "surgery":
        return "同意{}的意见。我从外科角度确认：目前无手术干预必要，随诊中如出现变化可再召会诊。".format(first)
    if spec == "labimaging":
        return "同意{}的判断。检查方面按我上述清单执行即可，结果回报后建议再次提交会诊平台复核。".format(first)
    if key:
        return ("感谢各位意见。综合各方观点，我对「{}」的诊断信心进一步增强，"
                "按共识方案执行并随访。").format(key)
    return "感谢各位意见。按共识检查计划推进，结果回报后再明确诊断方向。"


def _mock_report(case, text, specs=None):
    if case is not None and case.diagnosis:
        dx = case.diagnosis
        conf = "中高（演示脚本结论，供参考流程展示）"
    else:
        dx = "待完善检查后明确（演示模式无法给出真实诊断）"
        conf = "低（演示模式）"
    dept_map = {"internal": "内科门诊", "surgery": "外科门诊", "pharmacy": "药学门诊",
                "labimaging": "检验/影像科", "neurology": "神经内科门诊", "cardio": "心内科门诊",
                "pediatrics": "儿科门诊", "obgyn": "妇产科门诊"}
    if specs:
        dept = "或 ".join(dept_map.get(s, "全科门诊") for s in specs[:2])
    else:
        dept = "全科门诊 / 内科门诊"
    return {
        "final_diagnosis": dx,
        "confidence": conf,
        "recommended_dept": dept,
        "key_findings": [
            "用户提交的病情描述已由会诊助理整理为病历摘要",
            "各专科基于摘要独立发表意见并完成一轮交叉讨论",
        ],
        "plan": [
            "按影像与检验专家建议完善相关检查",
            "由主治医生结合检查结果明确诊疗方案",
            "病情变化时随时复诊或再次发起会诊",
        ],
        "disagreements": "本轮讨论无明显分歧（演示模式）",
        "red_flags": ["若出现高热不退、剧烈胸痛、呼吸困难、意识模糊等症状，请立即前往急诊就医。"],
        "warnings": "本平台输出由脚本模拟生成，仅供产品流程演示，不构成医疗建议。",
    }


# ---------------------------------------------------------------------------
# LLM 生成
# ---------------------------------------------------------------------------

def _chat(cfg, model, prompt, system=None):
    return llm.chat(model or cfg["moderator_model"],
                    system or cfg.get("moderator_prompt") or "你是一名严谨的临床医学专家，参与多学科会诊，用中文回答。",
                    prompt, cfg["api_key"], cfg["base_url"],
                    max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
                    timeout=cfg.get("timeout", 120))


def _llm_summary(cfg, text):
    try:
        return _chat(cfg, cfg["moderator_model"],
                     "请将以下病情描述整理为简洁的病历摘要（基本信息/主诉/现病史/既往史/辅助检查，缺项写'未见'），300字内：\n" + text,
                     "你是会诊主持人助理，负责整理病历。")
    except Exception:
        return _summarize(text)


STYLE_REQUEST = {
    "brief": "给出你考虑的诊断/鉴别诊断与建议的检查或处理，250字内，直接给结论。",
    "detailed": ("分五个部分作答，用短标题+条目：1)主要诊断与依据 2)鉴别诊断 3)建议检查 "
                 "4)处理与用药注意 5)随访建议，共500字内。"),
    "evidence": ("给出诊断与建议，并对关键结论标注所依据的通用临床指南/共识名称与推荐强度"
                 "（基于通用医学知识表述，不得编造具体文献页码），400字内。"),
}


def _llm_opinion(cfg, spec_name, summary, round_no, others_text):
    style_req = STYLE_REQUEST.get(cfg.get("spec_style") or "brief", STYLE_REQUEST["brief"])
    if round_no == 1:
        prompt = ("以下是一份病历摘要，请以{}身份参与多学科会诊(MDT)第一轮发言：{}"
                  "\n【病历摘要】\n{}").format(spec_name, style_req, summary)
    else:
        prompt = ("多学科会诊第二轮讨论。其他专家第一轮意见如下：\n{}\n"
                  "请以{}身份简要回应（同意/质疑谁、补充什么、最终倾向），180字内。").format(others_text, spec_name)
    return _chat(cfg, cfg["moderator_model"], prompt,
                 "你是会诊中的{}，发言专业、简洁、直接，不要复述任务，不要输出思考过程。"
                 "严格基于【病历摘要】与【参考资料】中给出的信息作答，"
                 "不得虚构资料中没有的检查结果、数值或病史。".format(spec_name))


def _parse_json_loose(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    return None


def _llm_report(cfg, summary, transcript_text):
    prompt = ("以下是MDT会诊全过程。请输出会诊共识报告，严格JSON格式，字段："
              'final_diagnosis(最终诊断), confidence(高/中/低), recommended_dept(建议就诊科室), '
              'key_findings(主要依据,数组), plan(诊疗方案建议,数组), '
              'red_flags(需要立即急诊的警示情况,数组), '
              'disagreements(分歧与说明,字符串), warnings(注意事项,字符串)。'
              "要求：严格基于病历摘要与会诊记录中的信息，不得虚构资料中没有的检查结果、数值或病史。"
              "\n【病历摘要】\n{}\n【会诊记录】\n{}").format(summary, transcript_text[:6000])
    try:
        raw = _chat(cfg, cfg["moderator_model"], prompt, "你是MDT主持人，只输出JSON。")
        data = _parse_json_loose(raw)
        if data:
            data.setdefault("final_diagnosis", "见上")
            data.setdefault("confidence", "中")
            data.setdefault("recommended_dept", "内科门诊")
            data.setdefault("key_findings", [])
            data.setdefault("plan", [])
            data.setdefault("red_flags", [])
            data.setdefault("disagreements", "无明显分歧")
            data.setdefault("warnings", "本报告由AI生成，仅供研究演示，不构成医疗建议。")
            for k in ("key_findings", "plan", "red_flags"):
                if isinstance(data.get(k), list):
                    data[k] = [str(x) for x in data[k]][:8]
                elif data.get(k):
                    data[k] = [str(data[k])]
            return data
    except Exception:
        pass
    return {"final_diagnosis": "（生成失败，请检查模型配置）", "confidence": "低",
            "recommended_dept": "内科门诊", "key_findings": [], "plan": [],
            "red_flags": [], "disagreements": "无",
            "warnings": "本报告由AI生成，仅供研究演示，不构成医疗建议。"}


# ---------------------------------------------------------------------------
# 预问诊追问：会诊前先补全关键信息
# ---------------------------------------------------------------------------

def clarify(text, settings=None):
    """返回 2-3 个关键追问；LLM 生成失败时按缺失信息兜底。"""
    cfg = _cfg(settings)
    if cfg["llm"]:
        try:
            raw = _chat(cfg, cfg["moderator_model"],
                        "以下是患者的病情描述。请提出 2-3 个最关键的补充问题（如病程、伴随症状、"
                        "既往史、用药过敏），帮助明确会诊所需信息。只输出 JSON 数组，每项一个问题，"
                        "每个问题不超过 30 字，中文。\n病情描述：" + text[:800],
                        "你是医院预问诊助理，只输出 JSON 数组。")
            m = re.search(r"\[.*\]", raw, re.S)
            if m:
                qs = json.loads(m.group(0))
                qs = [str(q).strip() for q in qs if str(q).strip()][:3]
                if qs:
                    return qs
        except Exception:
            pass
    qs = []
    if not re.search(r"\d+\s*(天|周|月|年|小时|日)", text):
        qs.append("这些症状持续多久了？")
    if not re.search(r"发热|发烧|畏寒|体温", text):
        qs.append("有没有发热、畏寒等全身症状？")
    if not re.search(r"既往|病史|过敏|服药|用药", text):
        qs.append("有没有慢性病史、药物过敏，目前是否在服药？")
    if not qs:
        qs.append("症状有没有加重或缓解的诱因（如进食、活动、夜间）？")
    return qs[:3]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def consult(text, settings=None, dataset=None, case_id=None, doc_ids=None):
    cfg = _cfg(settings)
    case = None
    if dataset and case_id is not None:
        try:
            case = cases_mod.get_case(dataset, int(case_id))
        except (KeyError, IndexError, TypeError, ValueError):
            case = None

    events = []
    docs = library.get_texts_by_ids(doc_ids)
    ref_names = [d["name"] for d in docs]
    ref_text = ""
    if cfg.get("tool_doc_search", True):
        # 检索工具：按病情自动检索文档库分块（选中文档优先，否则检索全库）
        allow = ref_names or None
        try:
            chunks = rag.search(text, allow, k=6)
        except Exception:
            chunks = []
        if chunks:
            ref_text = "\n\n【检索工具命中的资料片段（会诊必须基于以下真实内容）】\n" + \
                "\n".join("《{}》片段：{}".format(c["doc"], c["text"]) for c in chunks)
    if not ref_text and docs:
        ref_text = "\n\n【参考资料（用户文档库，会诊必须基于以下真实内容）】\n" + \
            "\n".join("《{}》\n{}".format(d["name"], d["content"]) for d in docs)
    if cfg["llm"]:
        summary = _llm_summary(cfg, text + ref_text)
    else:
        summary = _summarize(text, case)
    if ref_text:
        summary += ref_text
    events.append({"role": "summary", "name": "会诊助理", "emoji": "📋", "round": 0, "text": summary})

    specs = cfg["specialties"]
    first_round = {}
    for spec in specs:
        meta = SPECIALTIES[spec]
        if cfg["llm"]:
            opinion = _llm_opinion(cfg, meta["name"], summary, 1, "")
        else:
            opinion = _mock_opinion(spec, case, text, summary)
        first_round[spec] = opinion
        events.append({"role": "specialist", "name": meta["name"], "emoji": meta["emoji"],
                       "round": 1, "text": opinion})

    if cfg["rounds"] >= 2:
        others_text = "\n".join("{}：{}".format(SPECIALTIES[s]["name"], first_round[s]) for s in specs)
        for spec in specs:
            meta = SPECIALTIES[spec]
            if cfg["llm"]:
                others_wo_self = "\n".join("{}：{}".format(SPECIALTIES[s]["name"], first_round[s])
                                           for s in specs if s != spec)
                reply = _llm_opinion(cfg, meta["name"], summary, 2, others_wo_self)
            else:
                reply = _mock_response(spec, [SPECIALTIES[s]["name"] for s in specs if s != spec], case)
            events.append({"role": "specialist", "name": meta["name"], "emoji": meta["emoji"],
                           "round": 2, "text": reply})

    if cfg["llm"]:
        transcript = "\n".join("{}（第{}轮）：{}".format(e["name"], e["round"], e["text"])
                               for e in events if e["role"] == "specialist")
        report = _llm_report(cfg, summary, transcript)
    else:
        report = _mock_report(case, text, specs)
    if cfg.get("tool_calculator", True):
        # 计算器工具：从病情与摘要中检测可计算指标，自动计算并留痕
        try:
            calcs = toolmod.detect_and_run(summary + " " + text)
        except Exception:
            calcs = []
        if calcs:
            line = "；".join("{}（{}）= {}".format(c["name"], c["expr"], c["result"]) for c in calcs)
            events.append({"role": "tool", "name": "医学计算器", "emoji": "🧮", "round": 0,
                           "text": "工具自动计算：" + line})
            report["calculations"] = ["{}（{}）= {}".format(c["name"], c["expr"], c["result"]) for c in calcs]
    events.append({"role": "report", "name": "主持人 Agent", "emoji": "⚖️", "round": 0, "report": report})
    return {"events": events, "report": report}
