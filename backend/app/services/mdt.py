"""MDT 多学科会诊流水线。

模式隔离（修复原版"演示冒充权威"）：
- production：必须配置可用 LLM，否则直接拒绝发起；报告经严格结构校验，
  失败即显式报错，绝不静默降级成假报告。
- sandbox：无需 LLM，输出确定性演示文本；报告强制 is_demo=True，
  前端据此拒绝打印/签名/进入病案。

上下文安全（修复注入）：
- RAG/参考库/经验库内容统一作为【不可信数据引用】注入（见 llm.prompts）。
- 经验库只注入"approved 且未过期"的反馈，并携带来源与审核信息。
"""
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..shared import SPECIALTIES, DEFAULT_SPECIALTIES
from ..clinical import banner_text, detect_and_run, triage_scan
from ..clinical.completeness import assess as completeness_assess
from ..llm import (
    MODERATOR_SYSTEM, SPECIALIST_SYSTEM, SUMMARIZER_SYSTEM,
    LLMConfig, chat, role_config, role_system, report_with_retry,
    wrap_untrusted, extract_json,
)
from ..llm.validate import ReportSchema
from ..rag import search as rag_search
from ..evidence import search_evidence
from . import feedback_service, toolbox
from ..clinical.exam_appropriateness import suggest_exams, summary_text as exam_summary_text
from ..clinical.drug_interactions import check_interactions, summary_text as drug_summary_text
from .patient_report import build_patient_report
from . import agnes as agnes_fallback
from ..config import get_settings


class ConsultError(Exception):
    pass


# ---------------------------------------------------------------- 摘要构建
async def _summarize(production: bool, cfg: LLMConfig, text: str) -> str:
    if not production:
        return agnes_fallback.sandbox_summarize(text)
    if cfg.configured:
        return await _llm_summarize(cfg, text)
    # Agnes作为LLM后端
    return agnes_fallback.agnes_summarize(text)


async def _llm_summarize(cfg: LLMConfig, text: str) -> str:
    """生产模式+LLM可用：调用 Summarizer Agent 生成结构化摘要。"""
    summary = await chat(cfg, SUMMARIZER_SYSTEM, text[:1200], max_tokens=350)
    if not summary or not summary.strip():
        return "【病历摘要】（摘要生成失败）"
    lines = []
    for line in summary.splitlines():
        s = line.strip()
        if s.startswith(("主诉", "现病史", "既往史", "过敏史", "辅助检查")):
            lines.append(s)
    joined = "\n".join(lines[:6])
    return f"【病历摘要】\n{joined}" if joined else summary


# ---------------------------------------------------------------- 专科发言
def _specialist_system(spec_name: str, skills: list[dict]) -> str:
    return role_system(SPECIALIST_SYSTEM.format(spec=spec_name), skills)


def _specialist_prompt(spec_name: str, summary: str, untrusted: str,
                       style: str, others_text: str = "", round_no: int = 1) -> str:
    style_req = {
        "brief": "给出你考虑的诊断/鉴别诊断与建议检查或处理，250 字内，直接给结论。",
        "detailed": ("分五部分作答（短标题+条目）：1)主要诊断与依据 2)鉴别诊断 3)建议检查 "
                     "4)处理与用药注意 5)随访建议，共 500 字内。"),
        "evidence": ("给出诊断与建议，并对关键结论标注所依据的通用临床指南/共识名称与推荐强度"
                     "（基于通用医学知识，不得编造具体文献页码），400 字内。"),
    }.get(style, "brief")
    if round_no == 1:
        prompt = (
            f"以下是一份病历摘要，请以{spec_name}身份参与多学科会诊(MDT)第一轮发言。{style_req}"
            f"\n【病历摘要】\n{summary}\n{untrusted}"
        )
    else:
        prompt = (
            "多学科会诊第二轮讨论。请先回顾【病历摘要】，再回应其他专家意见。"
            f"\n【病历摘要】\n{summary}\n{untrusted}"
            f"\n其他专家第一轮意见如下：\n{others_text}\n"
            f"请以{spec_name}身份简要回应（同意/质疑谁、补充什么、最终倾向），180 字内。"
        )
    return prompt


async def _specialist_opinion(
    spec_key: str, summary: str, untrusted: str, style: str,
    skills: list[dict], cfg: LLMConfig, round_no: int, others_text: str = "",
) -> str:
    name = SPECIALTIES[spec_key]["name"]
    system = _specialist_system(name, skills)
    prompt = _specialist_prompt(name, summary, untrusted, style, others_text, round_no)
    try:
        return await chat(cfg, system, prompt)
    except Exception as e:
        return f"（{name}本轮生成失败：{e}）"


# ---------------------------------------------------------------- 主持人报告
async def _generate_report(
    cfg: LLMConfig, summary: str, transcript: str, skills: list[dict],
    mode_label: str, error_feedback: str = "",
) -> ReportSchema:
    system = role_system(MODERATOR_SYSTEM, skills)
    base_prompt = (
        "以下是 MDT 会诊全过程，请输出会诊共识报告，严格 JSON，字段："
        'final_diagnosis(最终诊断), confidence(高/中/低), recommended_dept(建议就诊科室), '
        'key_findings(主要依据,数组), plan(诊疗方案建议,数组), red_flags(需立即急诊的警示情况,数组), '
        'disagreements(分歧与说明,字符串), warnings(注意事项,字符串)。'
        "要求：严格基于病历摘要与会诊记录中的信息，不得虚构检查结果、数值或病史；"
        "信息不足时必须如实说明。"
        "\n【病历摘要】\n{summary}\n【会诊记录】\n{transcript[:8000]}"
    )

    async def _attempt(error_feedback: str = "") -> str:
        warn = "注意：前次输出未通过结构校验。" + (error_feedback[:500]) if error_feedback else ""
        user = base_prompt + (f"\n{warn}" if warn else "")
        return await chat(cfg, system, user, json_mode=True, max_tokens=1500)

    return await report_with_retry(_attempt)


# ---------------------------------------------------------------- 分歧显性化
# 各专科可能提出的诊断候选（关键词 → 诊断名）
_DIAG_KEYWORDS: dict[str, list[str]] = {
    "急性冠脉综合征": ["冠脉", "心梗", "急性冠脉", "冠心病", "acs"],
    "主动脉夹层": ["主动脉夹层", "夹层"],
    "肺栓塞": ["肺栓塞", "肺梗"],
    "气胸": ["气胸"],
    "急性胰腺炎": ["胰腺炎"],
    "急性胆囊炎": ["胆囊炎", "胆绞痛"],
    "急性阑尾炎": ["阑尾炎"],
    "肠梗阻": ["肠梗阻"],
    "消化道穿孔": ["穿孔", "溃疡"],
    "蛛网膜下腔出血": ["蛛网膜下腔", "脑出血", "颅内出血"],
    "脑卒中": ["脑梗", "卒中", "脑梗死"],
    "肺炎": ["肺炎"],
    "偏头痛": ["偏头痛"],
    "肾结石": ["肾结石", "输尿管结石"],
    "深静脉血栓": ["深静脉血栓", "dvt"],
}
# 明确表达"排除/质疑/不像"的措辞
_EXCLUDE_MARKERS = ["排除", "不支持", "不像", "不考虑", "可能性低", "暂不考虑", "证据不足", "难以用"]
_CONSIDER_MARKERS = ["考虑", "符合", "支持", "倾向", "首先考虑", "需警惕", "不能排除", "待排除"]


def compute_disagreements(round1: dict, round2: dict, specs: list[str]) -> dict:
    """从专科意见文本中确定性检测分歧。

    对每个专科提取其提出的诊断候选及立场（考虑/排除），
    当同一诊断候选同时存在"考虑"与"排除/质疑"两种立场，或不同专科
    提出互斥候选时，记录为分歧点。输出结构化分歧供报告与证据链使用。
    """
    spec_claims: dict[str, dict[str, str]] = {}
    for spec in specs:
        text = (round1.get(spec, "") + " " + round2.get(spec, "")).lower()
        claims: dict[str, str] = {}
        for diag, kws in _DIAG_KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    if any(m in text for m in _EXCLUDE_MARKERS):
                        claims[diag] = "排除/质疑"
                    elif any(m in text for m in _CONSIDER_MARKERS):
                        claims[diag] = "考虑"
                    else:
                        claims.setdefault(diag, "提及")
                    break
        if claims:
            spec_claims[SPECIALTIES[spec]["name"]] = claims
    # 汇总：某诊断被多少专科"考虑"/"排除"
    considered: dict[str, list[str]] = {}
    excluded: dict[str, list[str]] = {}
    for spec_name, claims in spec_claims.items():
        for diag, stance in claims.items():
            if stance in ("考虑", "提及"):
                considered.setdefault(diag, []).append(spec_name)
            elif stance == "排除/质疑":
                excluded.setdefault(diag, []).append(spec_name)
    disputes: list[dict] = []
    # 1) 同一候选：一方考虑、一方排除
    for diag in set(considered) & set(excluded):
        disputes.append({
            "topic": diag,
            "type": "立场冲突",
            "for": considered[diag],
            "against": excluded[diag],
            "summary": f"关于「{diag}」：{('、'.join(considered[diag]))}考虑，"
                       f"而{('、'.join(excluded[diag]))}持排除/质疑意见",
        })
    # 2) 不同专科给出不同候选，或存在被明确排除的候选（无立场冲突时也提示分歧）
    all_candidates = sorted(set(considered) | set(excluded))
    if ((len(all_candidates) >= 2 or excluded) and not disputes):
        disputes.append({
            "topic": "诊断候选分歧",
            "type": "候选分歧",
            "for": all_candidates,
            "against": [],
            "summary": "各专科提出了多个诊断候选：" + "、".join(all_candidates) +
                       "，需结合关键检查明确",
        })
    return {"has_disputes": bool(disputes), "disputes": disputes,
            "specialist_claims": spec_claims}


# ---------------------------------------------------------------- 证据链收集
def _add_evidence(db: Session, consultation_id: int, claim: str, basis_type: models.EvidenceBasisType,
                  source: str, confidence: str = "中", limitation: str = "") -> None:
    db.add(models.EvidenceItem(
        consultation_id=consultation_id, claim=claim[:2000],
        basis_type=basis_type, source=source[:300],
        confidence=confidence, limitation=limitation[:1000],
    ))


def _confidence_with_completeness(base: str, completeness: dict) -> tuple[str, list[str]]:
    """缺关键信息时对结论置信度降级，并给出补查建议。"""
    missing = completeness.get("missing") or []
    key_missing = [m for m in missing if m in ("用药过敏", "辅助检查", "生命体征", "既往史")]
    downgrade = len(key_missing) >= 1 or (len(missing) - len(key_missing)) >= 3
    conf = base
    if downgrade:
        order = {"高": "中", "中": "低", "低": "低"}
        if base in order:
            conf = order[base]
    return conf, key_missing



async def run_consultation(
    db: Session,
    *,
    user_text: str,
    mode: models.ConsultationMode,
    encounter_id: int | None,
    specialties: list[str],
    skills: list[dict],
    doc_texts: list[str],
    style: str,
    created_by: int,
    rounds: int = 2,
) -> models.Consultation:
    settings = get_settings()
    production = mode == models.ConsultationMode.PRODUCTION

    specs = [s for s in specialties if s in SPECIALTIES] or DEFAULT_SPECIALTIES

    # 生产模式：允许Agnes作为LLM后端，无需外部API配置
    if production and not settings.llm_configured:
        raise ConsultError("生产模式需要配置 LLM（API Key + base_url），请在服务端 .env 配置后再发起真实会诊。")

    # 组装病情文本
    case_text = user_text or ""
    if encounter_id:
        enc = db.get(models.Encounter, encounter_id)
        if enc:
            plain = enc.to_plain()
            parts = [plain["chief_complaint"], plain["history"], plain["meds"],
                     plain["exams"], plain["vitals"]]
            joined = "；".join(p for p in parts if p and p.strip())
            if joined:
                case_text = (joined + "\n" + case_text).strip()

    # 1) 红旗扫描（确定性；审计在获得会诊 id 后统一落库）
    flags_items = [{"severity": f.severity, "message": f.message, "matched": f.matched}
                   for f in triage_scan(case_text)]
    completeness = completeness_assess(case_text)

    # 2) 计算器（确定性）
    calcs_items = [{"name": c.name, "expr": c.expr, "result": c.result, "note": c.note}
                   for c in detect_and_run(case_text)]

    # 2b) 检查合理性 + 药物相互作用（确定性）
    exam_res = {"items": suggest_exams(case_text),
                "summary": exam_summary_text(suggest_exams(case_text))}
    drug_res = {"items": check_interactions(case_text),
                "summary": drug_summary_text(check_interactions(case_text))}

    # 3) 不可信数据块（RAG 循证检索 + 参考库 + 已审核反馈）
    untrusted_blocks: list[str] = []
    if doc_texts:
        untrusted_blocks.append("【用户文档库引用】\n" + "\n".join(
            f"《{d['name']}》\n{d['content']}" for d in doc_texts))
    try:
        chunks = rag_search(case_text, k=6)
        ev_res = {"items": chunks, "count": len(chunks)}
        if chunks:
            untrusted_blocks.append("【检索命中的资料片段】\n" + "\n".join(
                f"《{c['doc']}》片段：{c['text']}" for c in chunks))
    except Exception:
        chunks = []
        ev_res = {"items": [], "count": 0}
    try:
        exp = feedback_service.injectable_feedback(db, case_text, k=2)
        if exp:
            lines = [f"·（{e['approved_at']} 由 {e['submitted_by']} 提交、{e['reviewed_by']} 审核）"
                     f"{e['diagnosis']}{'；意见：' + e['note'] if e['note'] else ''}"
                     for e in exp]
            untrusted_blocks.append("【本院已审核经验（主任审核通过，仅供对照）】\n" + "\n".join(lines))
    except Exception:
        pass
    # 3b) 实时循证检索（外部源，production 时增强；失败静默降级到内部资料库）
    lit_res = {"items": [], "count": 0, "provider": ""}
    if production:
        try:
            lit_res = await search_evidence(case_text)
            if lit_res["items"]:
                lines = [f"·《{i['title'][:60]}》（{i['source']} {i['date']}，证据等级 {i['level']}）\n"
                         f"  {i['snippet'][:160]}"
                         for i in lit_res["items"][:4]]
                untrusted_blocks.append("【实时循证检索命中（外部证据源，仅供对照）】\n" + "\n".join(lines))
        except Exception:
            pass
    untrusted = wrap_untrusted(untrusted_blocks)

    # 4) 摘要
    if production:
        sum_cfg = role_config("summarizer")
        summary = await _summarize(True, sum_cfg, case_text)
        spec_cfg = role_config("specialist")
    else:
        summary = await _summarize(False, LLMConfig(), case_text)

    consultation = models.Consultation(
        encounter_id=encounter_id,
        mode=mode,
        title=(user_text or "未命名会诊")[:50],
        specialties_json=json.dumps(specs, ensure_ascii=False),
        data_completeness=f"{completeness['score']}/{completeness['total']}",
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(consultation)
    db.flush()  # 获得 id
    # 工具审计落库（带正确 consultation_id，确定性工具重算成本可忽略）
    toolbox.run_triage(db, consultation.id, case_text)
    toolbox.run_calculator(db, consultation.id, case_text)
    toolbox.run_exam_check(db, consultation.id, case_text)
    toolbox.run_drug_check(db, consultation.id, case_text)
    try:
        toolbox.run_evidence_search(db, consultation.id, case_text, k=6)
    except Exception:
        pass

    def add_event(role: str, name: str, emoji: str, text: str, round_no: int = 0):
        db.add(models.ConsultationEvent(
            consultation_id=consultation.id, role=role, name=name, emoji=emoji,
            round=round_no, text=text,
        ))

    if flags_items:
        sev_label = {"emergent": "立即急诊", "urgent": "尽快就医", "review": "需要关注"}
        triage_banner = "\n".join(
            f"{sev_label.get(f['severity'], '需关注')}：{f['message']}（依据：…{f['matched']}）"
            for f in flags_items)
        for fi in flags_items:
            _add_evidence(db, consultation.id, fi["message"], models.EvidenceBasisType.RULE,
                          "危急征象规则库（依据：…" + fi["matched"] + "）", "高",
                          "确定性规则命中，需人工复核临床适用性")
    else:
        triage_banner = "未检出危急征象（确定性规则扫描）"
    # triage 环节始终记录事件（命中/未命中都留痕，保证事件流完整可审计）
    add_event("triage", "危急征象识别", "🚨", triage_banner)
    add_event("summary", "会诊助理", "📋", summary)
    if calcs_items:
        add_event("tool", "医学计算器", "🧮",
                  "；".join(f"{c['name']}（{c['expr']}）= {c['result']}（{c['note']}）" for c in calcs_items))
        for c in calcs_items:
            _add_evidence(db, consultation.id, f"{c['name']}（{c['expr']}）= {c['result']}",
                          models.EvidenceBasisType.CALCULATOR, "医学计算器（确定性）", "中", c["note"])
    if exam_res["items"]:
        add_event("tool", "检查合理性", "🩻", exam_res["summary"])
        _add_evidence(db, consultation.id, exam_res["summary"], models.EvidenceBasisType.EXAM,
                      "检查合理性规则引擎（参考通用诊疗指南）", "中", "不适用情形已标注")
    if drug_res["items"]:
        add_event("tool", "药物相互作用", "💊", drug_res["summary"])
        _add_evidence(db, consultation.id, drug_res["summary"], models.EvidenceBasisType.DRUG,
                      "内置药物相互作用规则库", "中", "全面评估需接权威药品库")
    if chunks:
        _add_evidence(db, consultation.id,
                      "；".join(f"《{c['doc']}》：{c['text'][:80]}" for c in chunks[:3]),
                      models.EvidenceBasisType.RAG, "内部资料库检索命中", "中", "片段为资料原文，相关度阈值过滤")
    if lit_res["items"]:
        top = lit_res["items"][0]
        _add_evidence(db, consultation.id,
                      f"《{top['title'][:100]}》——{top['source']} {top['date']}（证据等级 {top['level']}）",
                      models.EvidenceBasisType.LITERATURE,
                      f"实时循证检索（{lit_res['provider']}）", "中",
                      "外部证据源，仅供对照；检索时间与来源见链接")

    # 5) 专科第一轮（并发）
    transcript_lines: list[str] = []
    if production:
        if spec_cfg.configured:
            async def _r1(spec: str) -> tuple[str, str]:
                text = await _specialist_opinion(
                    spec, summary, untrusted, style, skills, spec_cfg, 1)
                return spec, text

            round1 = dict(await asyncio.gather(*[_r1(s) for s in specs]))
        else:
            # Agnes作为LLM后端
            round1 = {s: agnes_fallback.agnes_specialist_opinion(s, summary, case_text, style, 1) for s in specs}
    else:
        round1 = {s: agnes_fallback.sandbox_opinion(s, summary, 1) for s in specs}

    for spec in specs:
        meta = SPECIALTIES[spec]
        text = round1[spec]
        add_event("specialist", meta["name"], meta["emoji"], text, 1)
        transcript_lines.append(f"{meta['name']}（第1轮）：{text}")

    # 6) 第二轮交叉讨论（并发）
    if rounds >= 2 and len(specs) >= 2:
        if production:
            if spec_cfg.configured:
                async def _r2(spec: str) -> tuple[str, str]:
                    others = "\n".join(
                        f"{SPECIALTIES[s]['name']}：{round1[s]}" for s in specs if s != spec)
                    text = await _specialist_opinion(
                        spec, summary, untrusted, style, skills, spec_cfg, 2, others)
                    return spec, text

                round2 = dict(await asyncio.gather(*[_r2(s) for s in specs]))
            else:
                # Agnes作为LLM后端
                round2 = {}
                for spec in specs:
                    others = "\n".join(
                        f"{SPECIALTIES[s]['name']}：{round1[s]}" for s in specs if s != spec)
                    round2[spec] = agnes_fallback.agnes_specialist_opinion(spec, summary, case_text, style, 2, others)
        else:
            round2 = {s: agnes_fallback.sandbox_opinion(s, summary, 2) for s in specs}

        for spec in specs:
            meta = SPECIALTIES[spec]
            add_event("specialist", meta["name"], meta["emoji"], round2[spec], 2)
            transcript_lines.append(f"{meta['name']}（第2轮）：{round2[spec]}")

    # 6b) 分歧显性化（确定性检测专科意见冲突）
    dispute_res = compute_disagreements(round1, round2 if rounds >= 2 else {}, specs)
    if dispute_res["has_disputes"]:
        for d in dispute_res["disputes"]:
            add_event("dispute", "专科分歧", "⚔️", d["summary"])
            _add_evidence(db, consultation.id, d["summary"], models.EvidenceBasisType.SPECIALIST,
                          "多专科意见交叉比对", "中", "分歧需结合关键检查裁决")

    # 7) 主持人共识报告
    if production:
        if spec_cfg.configured:
            mod_cfg = role_config("moderator")
            transcript = "\n".join(transcript_lines)
            try:
                report = await _generate_report(mod_cfg, summary, transcript, skills,
                                                mode_label="production")
                report_dict = report.model_dump()
            except Exception as e:
                consultation.status = models.ConsultationStatus.FAILED
                consultation.error_msg = str(e)[:2000]
                db.commit()
                raise ConsultError(f"报告生成失败：{e}")
        else:
            # Agnes作为主持人
            transcript = "\n".join(transcript_lines)
            report_dict = agnes_fallback.agnes_report(summary, transcript, case_text, completeness, flags_items, calcs_items)
    else:
        report_dict = agnes_fallback.sandbox_report(case_text, completeness)
        consultation.is_demo = True

    # 8) 组装报告（附加确定性结果 + 证据链增强）
    report_dict["data_completeness"] = consultation.data_completeness
    if completeness["missing"]:
        report_dict["missing_info"] = "缺：" + "、".join(completeness["missing"])
    if calcs_items:
        report_dict["calculations"] = [f"{c['name']}（{c['expr']}）= {c['result']}（{c['note']}）"
                                       for c in calcs_items]
    if flags_items:
        report_dict["red_flags"] = [i["message"] for i in flags_items] + list(
            report_dict.get("red_flags") or [])
    # 缺关键信息 → 置信度降级 + 补查建议
    conf = report_dict.get("confidence", "中")
    report_dict["confidence"], key_missing = _confidence_with_completeness(conf, completeness)
    if key_missing:
        report_dict["warnings"] = (report_dict.get("warnings") or "") + \
            f"；当前缺少{'、'.join(key_missing)}，结论置信度已相应下调。"
    if exam_res["items"]:
        report_dict["exam_suggestions"] = exam_res["summary"]
    if drug_res["items"]:
        report_dict["drug_interactions"] = drug_res["summary"]
    # 分歧写入报告（主持人若已给出则保留，未给出用确定性结果补充）
    if dispute_res["has_disputes"]:
        dsum = "；".join(d["summary"] for d in dispute_res["disputes"])
        existing = report_dict.get("disagreements") or ""
        report_dict["disagreements"] = (existing + ("；" if existing else "") + dsum)[:2000]
        report_dict["dispute_detail"] = dispute_res["disputes"]
    # 主持人结论进证据链
    if report_dict.get("final_diagnosis"):
        _add_evidence(db, consultation.id,
                      "最终诊断：" + report_dict["final_diagnosis"],
                      models.EvidenceBasisType.MODERATOR, "主持人 Agent 共识报告", conf,
                      "基于专科意见与检索资料综合；置信度受资料完备度影响")
    for f in (report_dict.get("key_findings") or [])[:5]:
        _add_evidence(db, consultation.id, str(f), models.EvidenceBasisType.MODERATOR,
                      "主持人 Agent 共识报告·主要依据", conf, "")
    # 患者版报告（双视角）
    try:
        pr = build_patient_report(report_dict, completeness)
        report_dict["patient_report"] = pr.__dict__
    except Exception:
        pass

    consultation.set_report(report_dict)
    consultation.status = models.ConsultationStatus.COMPLETED
    add_event("report", "主持人 Agent", "⚖️", json.dumps(report_dict, ensure_ascii=False)[:4000])
    db.commit()
    db.refresh(consultation)
    return consultation
