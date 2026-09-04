"""Agent 统一入口：一条输入自动分流到 会诊 / 问诊 / 计算 / 用药 / 知识 / 循证检索。

企业级交互范式的关键入口——医生只需要输入任何内容，
系统（确定性意图识别）决定走哪条能力链路，前端据此渲染对应交互。
"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import models
from ..clinical import detect_and_run, get_calculator_catalog
from ..clinical.drug_interactions import check_interactions, summary_text as drug_summary_text
from ..clinical.triage import _RULES as REDFLAG_RULES
from ..deps import CurrentUser, DbDep, client_ip, write_audit
from ..schemas import AgentRequest
from ..services.intent import Intent, INTENT_LABELS, classify_intent

router = APIRouter(tags=["agent"])


@router.get("/agent/rules")
def agent_rules(user: CurrentUser):
    """系统内置规则与能力清单（差异化公示）。

    为什么这个端点存在：企业与评审最关心"AI 有没有底线"。
    这里把系统内置的安全基线提示词、危急红旗规则、药物相互作用规则、
    证据分级、意图路由、内置计算器一次性公示，证明系统是"规则驱动"的
    确定性系统，而不是黑盒套壳。
    """
    from ..llm.prompts import SAFETY_LAYER
    from ..evidence.providers import LEVEL_LABEL
    from ..clinical import drug_interactions as di

    redflag_summary = {}
    for _, sev, msg in REDFLAG_RULES:
        redflag_summary.setdefault(sev, {"count": 0, "examples": []})
        redflag_summary[sev]["count"] += 1
        if len(redflag_summary[sev]["examples"]) < 3:
            redflag_summary[sev]["examples"].append(msg)

    drug_sev = {"major": 0, "moderate": 0, "minor": 0}
    for r in di._RULES:
        drug_sev[r.severity] = drug_sev.get(r.severity, 0) + 1

    return {
        "safety_baseline": SAFETY_LAYER,
        "red_flags": {"total": len(REDFLAG_RULES), "by_severity": redflag_summary},
        "drug_interactions": {"total": len(di._RULES), "by_severity": drug_sev},
        "evidence_levels": {k: v for k, v in LEVEL_LABEL.items()},
        "intents": [{"intent": i.value, "label": INTENT_LABELS.get(i.value, i.value)}
                    for i in Intent],
        "calculators": [{"name": c["name"], "desc": c.get("desc", "")}
                        for c in get_calculator_catalog()],
        "roles": ["triage 危急红旗扫描", "intake 采集式问诊", "specialist 多专科意见",
                  "moderator 共识报告", "tool 医学计算/用药核查", "report 双视图报告(专业/患者)"],
    }


@router.post("/agent")
async def agent_entry(body: AgentRequest, db: DbDep, user: CurrentUser, request: Request):
    """统一意图入口：识别意图 → 执行对应能力 → 返回结构化结果。"""
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入内容")

    # 意图判定：可人工强制覆盖（前端提供「改用会诊/改用问诊」纠偏按钮）
    if body.force_intent:
        try:
            intent = Intent(body.force_intent)
            decision = type("D", (), {"to_dict": lambda self: {
                "intent": intent.value, "label": intent.value,
                "confidence": 1.0, "reason": "人工指定", "matched": ""}})()
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "未知意图")
    else:
        decision = classify_intent(text)
        intent = decision.intent

    write_audit(db, user, "agent.invoke", "agent", intent.value,
                f"confidence={decision.to_dict()['confidence']} text={text[:80]}", client_ip(request))

    if intent == Intent.CONSULT:
        from .consultations import perform_consultation
        data = await perform_consultation(
            db, user, text=text, mode=body.mode, specialties=body.specialties,
            skills=body.skills, doc_ids=body.doc_ids, style=body.style,
            rounds=body.rounds, request=request)
        return {"intent": decision.to_dict(), "action": "consult", "data": data}

    if intent == Intent.INTAKE:
        return {"intent": decision.to_dict(), "action": "redirect",
                "redirect": "/intake", "data": {
                    "message": "已识别为采集式问诊意图，将进入结构化病史采集，"
                               "请补充患者年龄、症状持续时间、伴随表现等信息。"}}

    if intent == Intent.CALCULATOR:
        items = [{"name": c.name, "expr": c.expr, "result": c.result, "note": c.note}
                 for c in detect_and_run(text)]
        return {"intent": decision.to_dict(), "action": "calculator", "data": {"items": items}}

    if intent == Intent.DRUG:
        items = check_interactions(text)
        return {"intent": decision.to_dict(), "action": "drug", "data": {
            "items": [i._asdict() if hasattr(i, "_asdict") else dict(i) for i in items],
            "summary": drug_summary_text(items)}}

    if intent == Intent.LITERATURE:
        from ..evidence import search_evidence, LEVEL_LABEL
        ev = await search_evidence(text)
        return {"intent": decision.to_dict(), "action": "literature", "data": {
            "provider": ev["provider"], "count": ev["count"], "degraded": ev["degraded"],
            "level_labels": dict(LEVEL_LABEL),
            "results": [{"title": i["title"], "source": i["source"], "date": i["date"],
                         "url": i["url"], "snippet": i["snippet"][:400], "level": i["level"]}
                        for i in ev["items"]],
            "note": "实时循证检索（PubMed 优先，内部资料库兜底）；结果仅供对照，点击链接溯源原文献"}}

    if intent == Intent.KNOWLEDGE:
        refs = db.scalars(select(models.ReferenceItem)
                          .where(models.ReferenceItem.item.contains(text[:20]), )
                          .limit(5)).all()
        return {"intent": decision.to_dict(), "action": "knowledge", "data": {
            "references": [{"item": r.item, "en": r.en, "unit": r.unit,
                            "range": r.range, "note": r.note} for r in refs]}}

    raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法处理该意图")