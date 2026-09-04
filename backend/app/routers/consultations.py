"""会诊路由：发起 MDT / 列表 / 详情 / 报告追问 / 过程流式回放 / 删除 / 导出。"""
import asyncio
from datetime import datetime
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .. import models
from ..config import get_settings
from ..deps import DbDep
from ..deps import CurrentUser, client_ip, data_scope, scope_filter, write_audit
from ..llm import FOLLOWUP_SYSTEM, chat, role_config, role_system, wrap_untrusted
from ..schemas import ConsultRequest, FollowupRequest
from ..services import mdt as mdt_service
from ..services.agnes import agnes_followup
from ..shared import storage_dir

router = APIRouter(tags=["consultations"])


async def perform_consultation(db, user, *, text: str, mode: str,
                               specialties: list, skills: list[int], doc_ids: list[int],
                               style: str = "brief", rounds: int = 2,
                               encounter_id: int | None = None,
                               request: Request | None = None) -> dict:
    """发起 MDT 会诊（供 /consultations 与 /agent 统一入口复用）。"""
    if mode not in ("production", "sandbox"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode 必须为 production 或 sandbox")
    if not (text or "").strip() and encounter_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请提供病情描述或关联就诊记录")
    if mode == "production" and not (text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "生产模式需要病情描述")

    # 技能
    skill_rows = []
    if skills:
        rows = db.scalars(select(models.Skill).where(
            models.Skill.id.in_(skills), models.Skill.active.is_(True))).all()
        skill_rows = [{"name": s.name, "prompt": s.prompt} for s in rows]
    # 文档
    doc_texts = []
    if doc_ids:
        docs = db.scalars(select(models.Document).where(models.Document.id.in_(doc_ids))).all()
        for d in docs:
            content = _read_doc_content(d)
            if content:
                doc_texts.append({"name": d.name, "content": content[:3000]})

    m = models.ConsultationMode(mode)
    try:
        c = await mdt_service.run_consultation(
            db,
            user_text=(text or "").strip(),
            mode=m,
            encounter_id=encounter_id,
            specialties=specialties,
            skills=skill_rows,
            doc_texts=doc_texts,
            style=style,
            created_by=user.id,
            rounds=rounds,
        )
    except mdt_service.ConsultError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    write_audit(db, user, "consult.create", "consultation", str(c.id),
                f"mode={mode} specs={len(specialties)}", client_ip(request) if request else "")
    return _c_detail(c)


@router.post("/consultations")
async def create_consultation(body: ConsultRequest, db: DbDep, user: CurrentUser, request: Request):
    return await perform_consultation(
        db, user, text=(body.text or "").strip(), mode=body.mode,
        specialties=body.specialties, skills=body.skills, doc_ids=body.doc_ids,
        style=body.style, rounds=body.rounds, encounter_id=body.encounter_id,
        request=request,
    )


@router.get("/consultations")
def list_consultations(db: DbDep, user: CurrentUser, limit: int = 50, mode: str = ""):
    scope = data_scope(db, user)
    cond = scope_filter(scope, models.Consultation.created_by)
    q = select(models.Consultation).order_by(models.Consultation.id.desc()).limit(limit)
    if cond is not None:
        q = q.where(cond)
    if mode in ("production", "sandbox"):
        q = q.where(models.Consultation.mode == models.ConsultationMode(mode))
    rows = db.scalars(q).all()
    return {"items": [{
        "id": c.id, "title": c.title, "mode": c.mode.value,
        "status": c.status, "is_demo": c.is_demo,
        "data_completeness": c.data_completeness,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows]}


def _c_visible(db, cid: int, user) -> models.Consultation | None:
    """按可见性范围取会诊；无权限返回 None。"""
    c = db.get(models.Consultation, cid)
    if c is None:
        return None
    scope = data_scope(db, user)
    if scope is not None and c.created_by not in scope:
        return None
    return c


@router.get("/consultations/{cid}")
def get_consultation(cid: int, db: DbDep, user: CurrentUser):
    c = _c_visible(db, cid, user)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")
    c = db.get(
        models.Consultation, cid,
        options=[joinedload(models.Consultation.evidence_items),
                 joinedload(models.Consultation.tool_call_logs)],
    )
    return _c_detail(c)


@router.post("/consultations/{cid}/followup")
async def followup(cid: int, body: FollowupRequest, db: DbDep, user: CurrentUser):
    c = _c_visible(db, cid, user)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")
    report = c.get_report() or {}
    events = db.scalars(select(models.ConsultationEvent)
                        .where(models.ConsultationEvent.consultation_id == cid)
                        .order_by(models.ConsultationEvent.id.desc()).limit(6)).all()
    context = ["【会诊报告】" + json.dumps(report, ensure_ascii=False)[:2500]]
    for e in reversed(events):
        if e.role != "report":
            context.append(f"【{e.name}】{e.text[:400]}")
    system = role_system(FOLLOWUP_SYSTEM)
    prompt_text = ("医生正在阅读会诊报告并提出追问，请基于上下文作答，250 字内，直接回答。\n\n"
                   + "\n\n".join(context) + "\n\n【医生追问】" + body.text)

    settings = get_settings()
    if not settings.llm_configured:
        # Agnes作为LLM后端：使用内置智能追问
        context_text = "\n".join(context)
        reply = agnes_followup(context_text, body.text)
    else:
        try:
            reply = await chat(role_config("moderator"), system, prompt_text)
        except Exception as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"模型调用失败：{e}")

    db.add(models.ConsultationEvent(
        consultation_id=cid, role="specialist", name="会诊主持人（追问）",
        emoji="⚖️", round=0, text=reply))
    db.commit()
    write_audit(db, user, "consult.followup", "consultation", str(cid))
    return {"reply": reply}


@router.get("/consultations/{cid}/export")
def export_consultation_html(cid: int, db: DbDep, user: CurrentUser):
    """导出会诊报告为打印友好 HTML（可直接打印 / Ctrl+P 另存 PDF）。

    企业交付场景：报告归档、病案打印、向院方演示。沙箱演示报告强制水印，
    与平台"沙箱禁止打印/入病案"的规则保持一致。
    """
    c = _c_visible(db, cid, user)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")
    report = c.get_report() or {}
    creator = db.get(models.User, c.created_by)
    creator_name = creator.full_name or creator.username if creator else "?"
    hospital = get_settings().hospital_name

    def esc(v) -> str:
        return (v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts = [f"<h1>{esc(c.title)}</h1>"]
    meta = (f"<div class='meta'>会诊 #{c.id} · {hospital} · 创建人 {esc(creator_name)} · "
            f"模式 {c.mode.value} · {c.created_at.isoformat() if c.created_at else ''}</div>")
    if c.is_demo:
        meta += "<div class='demo-stamp'>⚠ 沙箱演示报告 · 仅供演示学习 · 禁止打印 / 入病案 / 用于临床决策</div>"
    parts.append(meta)

    if report:
        rows = [
            ("倾向判断（供参考）", report.get("final_diagnosis")),
            ("置信度", report.get("confidence")),
            ("建议就诊科室", report.get("recommended_dept")),
            ("资料完备度", report.get("data_completeness")),
            ("缺失信息", report.get("missing_info")),
            ("建议检查", report.get("exam_suggestions")),
            ("药物相互作用核查", report.get("drug_interactions")),
            ("分歧与风险", report.get("disagreements")),
            ("警示", report.get("warnings")),
        ]
        for k, v in rows:
            if v:
                parts.append(f"<h2>{esc(k)}</h2><p>{esc(v)}</p>")
        for label, key in (("主要依据", "key_findings"), ("方案建议", "plan"),
                           ("红旗警示", "red_flags"), ("工具计算", "calculations")):
            items = report.get(key) or []
            if items:
                lis = "".join(f"<li>{esc(i)}</li>" for i in items)
                parts.append(f"<h2>{label}</h2><ul>{lis}</ul>")

    # 证据链
    evidence = db.scalars(select(models.EvidenceItem)
                          .where(models.EvidenceItem.consultation_id == cid)
                          .order_by(models.EvidenceItem.id)).all()
    if evidence:
        parts.append("<h2>证据链</h2><ul>")
        for e in evidence:
            parts.append(
                f"<li><b>{esc(e.claim)}</b>（依据：{esc(e.basis_type)}，置信度 {esc(e.confidence)}）"
                f"<br><span class='small'>{esc(e.source)} · 局限：{esc(e.limitation)}</span></li>")
        parts.append("</ul>")

    # 会诊全过程
    events = db.scalars(select(models.ConsultationEvent)
                        .where(models.ConsultationEvent.consultation_id == cid)
                        .order_by(models.ConsultationEvent.id)).all()
    if events:
        parts.append("<h2>会诊过程</h2><div class='events'>")
        for e in events:
            parts.append(f"<p><b>{esc(e.name)}</b>：{esc(e.text)}</p>")
        parts.append("</div>")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{esc(c.title)} - 会诊报告</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    max-width: 800px; margin: 24px auto; padding: 0 20px; color: #1e293b; line-height: 1.7; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }}
  h2 {{ font-size: 15px; margin: 18px 0 6px; color: #1e40af; }}
  .meta {{ color: #64748b; font-size: 12.5px; margin-bottom: 16px; }}
  .demo-stamp {{ color: #b91c1c; border: 1px solid #fecaca; background: #fef2f2;
    border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-weight: 600; }}
  .small {{ color: #64748b; font-size: 12px; }}
  .events p {{ margin: 4px 0; }}
  p {{ margin: 4px 0; }}
  footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #e2e8f0;
    color: #94a3b8; font-size: 11.5px; }}
  @media print {{ body {{ margin: 0; }} .no-print {{ display: none; }} }}
  .no-print {{ text-align: center; margin-bottom: 16px; }}
</style></head><body>
<div class="no-print"><button onclick="window.print()">🖨 打印 / 另存 PDF</button></div>
{''.join(parts)}
<footer>本报告由「{esc(hospital)}」AI 辅助会诊系统生成，仅供临床医师参考，不构成处方或最终诊断。生成时间 {datetime.now().strftime("%Y-%m-%d %H:%M")}</footer>
</body></html>"""
    write_audit(db, user, "consult.export", "consultation", str(cid))
    return HTMLResponse(html)


def _read_doc_content(d: models.Document) -> str:
    p = storage_dir("documents") / d.storage_name
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _c_detail(c: models.Consultation) -> dict:
    events = [{"role": e.role, "name": e.name, "emoji": e.emoji,
               "round": e.round, "text": e.text} for e in c.events]
    evidence = [{"id": e.id, "claim": e.claim, "basis_type": e.basis_type,
                 "source": e.source, "confidence": e.confidence,
                 "limitation": e.limitation} for e in c.evidence_items]
    tool_calls = [{"id": t.id, "tool_name": t.tool_name,
                   "input": json.loads(t.input_json or "{}"),
                   "output": json.loads(t.output_json or "{}"),
                   "confidence": t.confidence, "note": t.note} for t in c.tool_call_logs]
    return {
        "id": c.id,
        "title": c.title,
        "mode": c.mode.value,
        "status": c.status,
        "is_demo": c.is_demo,
        "data_completeness": c.data_completeness,
        "error_msg": c.error_msg,
        "specialties": json.loads(c.specialties_json or "[]"),
        "report": c.get_report(),
        "events": events,
        "evidence": evidence,
        "tool_calls": tool_calls,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/consultations/{cid}/stream")
async def stream_consultation(cid: int, db: DbDep, user: CurrentUser):
    """会诊过程 SSE 流：逐步回放事件 + 报告打字机输出。

    前端用 fetch + ReadableStream 读取（携带 Authorization 头），
    完成后以 done 事件收尾。按真实顺序回放已在库的过程事件，
    报告以分块形式流式输出，模拟打字机聚焦阅读。
    """
    c = _c_visible(db, cid, user)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")

    async def event_gen():
        async def sse(event: str, data: dict) -> str:
            payload = json.dumps(data, ensure_ascii=False)
            return f"event: {event}\ndata: {payload}\n\n"

        # 1) 过程事件回放（triage → tools → specialists → moderator）
        rows = db.scalars(
            select(models.ConsultationEvent)
            .where(models.ConsultationEvent.consultation_id == cid)
            .order_by(models.ConsultationEvent.id)).all()
        for e in rows:
            yield await sse("event", {"role": e.role, "name": e.name,
                                      "emoji": e.emoji, "round": e.round, "text": e.text})
            await asyncio.sleep(0.25)

        # 2) 报告打字机流
        report = c.get_report() or {}
        if report:
            blob = json.dumps(report, ensure_ascii=False, indent=1)
            for i in range(0, len(blob), 12):
                yield await sse("report_chunk", {"chunk": blob[i:i + 12]})
                await asyncio.sleep(0.02)
            yield await sse("report_chunk", {"chunk": ""})

        yield await sse("done", {"id": cid, "status": c.status, "is_demo": c.is_demo})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.delete("/consultations/{cid}")
def delete_consultation(cid: int, db: DbDep, user: CurrentUser):
    """删除会诊（仅创建者或管理员；级联清理事件/证据/工具日志）。"""
    c = _c_visible(db, cid, user)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")
    if c.created_by != user.id and user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅创建者或管理员可删除")
    db.delete(c)
    db.commit()
    write_audit(db, user, "consult.delete", "consultation", str(cid))
    return {"deleted": True, "id": cid}
