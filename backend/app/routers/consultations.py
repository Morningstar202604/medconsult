"""会诊路由：发起 MDT / 列表 / 详情 / 报告追问。"""
import json

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser, client_ip, write_audit
from ..llm import FOLLOWUP_SYSTEM, chat, role_config, role_system, wrap_untrusted
from ..schemas import ConsultRequest, FollowupRequest
from ..services import mdt as mdt_service

router = APIRouter(tags=["consultations"])


@router.post("/consultations")
async def create_consultation(body: ConsultRequest, db: DbDep, user: CurrentUser, request: Request):
    if body.mode not in ("production", "sandbox"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode 必须为 production 或 sandbox")
    if not (body.text or "").strip() and body.encounter_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请提供病情描述或关联就诊记录")
    if body.mode == "production" and not (body.text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "生产模式需要病情描述")

    # 技能
    skills = []
    if body.skills:
        rows = db.scalars(select(models.Skill).where(
            models.Skill.id.in_(body.skills), models.Skill.active.is_(True))).all()
        skills = [{"name": s.name, "prompt": s.prompt} for s in rows]
    # 文档
    doc_texts = []
    if body.doc_ids:
        docs = db.scalars(select(models.Document).where(models.Document.id.in_(body.doc_ids))).all()
        for d in docs:
            content = _read_doc_content(d)
            if content:
                doc_texts.append({"name": d.name, "content": content[:3000]})

    mode = models.ConsultationMode(body.mode)
    try:
        c = await mdt_service.run_consultation(
            db,
            user_text=(body.text or "").strip(),
            mode=mode,
            encounter_id=body.encounter_id,
            specialties=body.specialties,
            skills=skills,
            doc_texts=doc_texts,
            style=body.style,
            created_by=user.id,
            rounds=body.rounds,
        )
    except mdt_service.ConsultError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    write_audit(db, user, "consult.create", "consultation", str(c.id),
                f"mode={body.mode} specs={len(body.specialties)}", client_ip(request))
    return _c_detail(c)


@router.get("/consultations")
def list_consultations(db: DbDep, user: CurrentUser, limit: int = 50, mode: str = ""):
    q = select(models.Consultation).order_by(models.Consultation.id.desc()).limit(limit)
    if mode in ("production", "sandbox"):
        q = q.where(models.Consultation.mode == models.ConsultationMode(mode))
    rows = db.scalars(q).all()
    return {"items": [{
        "id": c.id, "title": c.title, "mode": c.mode.value,
        "status": c.status, "is_demo": c.is_demo,
        "data_completeness": c.data_completeness,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows]}


@router.get("/consultations/{cid}")
def get_consultation(cid: int, db: DbDep, user: CurrentUser):
    c = db.get(models.Consultation, cid)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会诊不存在")
    return _c_detail(c)


@router.post("/consultations/{cid}/followup")
async def followup(cid: int, body: FollowupRequest, db: DbDep, user: CurrentUser):
    c = db.get(models.Consultation, cid)
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

    from ..config import get_settings
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "报告追问需要配置真实模型（生产模式）")
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


def _read_doc_content(d: models.Document) -> str:
    from pathlib import Path
    from ..config import get_settings

    base = Path(get_settings().database_url.replace("sqlite:///", "")).parent
    p = base / "documents" / d.storage_name
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _c_detail(c: models.Consultation) -> dict:
    events = [{"role": e.role, "name": e.name, "emoji": e.emoji,
               "round": e.round, "text": e.text} for e in c.events]
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
        "evidence": _evidence_list(c.id),
        "tool_calls": _tool_calls_list(c.id),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _evidence_list(cid: int):
    from ..db import SessionLocal
    from sqlalchemy import select
    db = SessionLocal()
    try:
        rows = db.scalars(select(models.EvidenceItem)
                          .where(models.EvidenceItem.consultation_id == cid)
                          .order_by(models.EvidenceItem.id)).all()
        return [{"id": e.id, "claim": e.claim, "basis_type": e.basis_type,
                 "source": e.source, "confidence": e.confidence,
                 "limitation": e.limitation} for e in rows]
    finally:
        db.close()


def _tool_calls_list(cid: int):
    from ..db import SessionLocal
    from sqlalchemy import select
    db = SessionLocal()
    try:
        rows = db.scalars(select(models.ToolCallLog)
                          .where(models.ToolCallLog.consultation_id == cid)
                          .order_by(models.ToolCallLog.id)).all()
        return [{"id": t.id, "tool_name": t.tool_name,
                 "input": json.loads(t.input_json or "{}"),
                 "output": json.loads(t.output_json or "{}"),
                 "confidence": t.confidence, "note": t.note} for t in rows]
    finally:
        db.close()
