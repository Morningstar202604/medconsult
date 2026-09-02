"""采集式问诊路由：主诉→定向问诊→结构化病历。

对话层差异化：从这里开始，交互不再是自由聊天，而是采集协议。
会话持久化到 intake_sessions，问诊轮次写入 answers_json，全程可审计、可回放。
"""
import json
from fastapi import APIRouter, HTTPException, Request, status
from .. import models
from ..deps import DbDep, CurrentUser, client_ip, write_audit
from ..clinical import intake
from ..schemas import IntakeStartRequest, IntakeAnswerRequest, IntakeCompleteRequest

router = APIRouter(tags=["intake"])


def _load_state(sess: models.IntakeSession) -> intake.IntakeState:
    return intake.state_from_json(
        sess.chief_complaint, sess.category,
        json.loads(sess.fields_json or "{}"),
        json.loads(sess.answers_json or "[]"),
        json.loads(sess.pending_json or "[]"),
        sess.status,
        json.loads(sess.red_flags_json or "[]"),
        sess.flags_urgent)


def _save_state(db: DbDep, sess: models.IntakeSession, st: intake.IntakeState) -> None:
    sess.fields_json = json.dumps(st.fields, ensure_ascii=False)
    sess.answers_json = json.dumps(st.answers, ensure_ascii=False)
    sess.pending_json = json.dumps(st.protocol, ensure_ascii=False)
    sess.red_flags_json = json.dumps(st.red_flags, ensure_ascii=False)
    sess.flags_urgent = st.flags_urgent
    sess.status = st.status
    db.add(sess)


@router.post("/intake")
def start_intake(body: IntakeStartRequest, db: DbDep, user: CurrentUser, request: Request):
    st = intake.init_state(body.chief_complaint)
    first = intake.first_question(st)
    sess = models.IntakeSession(
        user_id=user.id,
        chief_complaint=st.chief_complaint,
        category=st.category,
        status=st.status,
        fields_json=json.dumps(st.fields, ensure_ascii=False),
        answers_json=json.dumps(st.answers, ensure_ascii=False),
        pending_json=json.dumps(st.protocol, ensure_ascii=False),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    write_audit(db, user, "intake.start", "intake_session", str(sess.id),
                f"chief={st.chief_complaint[:50]} cat={st.category}", client_ip(request))
    return {
        "id": sess.id,
        "category": st.category,
        "category_label": intake.CATEGORY_LABEL.get(st.category, "其他"),
        "next_question": first,
        "initial_flags": st.initial_flags,
        "progress": {"answered": 0, "total": len(st.protocol)},
    }


@router.post("/intake/{sid}/answer")
def answer_intake(sid: int, body: IntakeAnswerRequest, db: DbDep, user: CurrentUser):
    sess = db.get(models.IntakeSession, sid)
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "问诊会话不存在")
    if sess.user_id != user.id and user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该问诊")
    if sess.status in ("redflag", "complete"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "该问诊已终止或完成，请新建会话")
    st = _load_state(sess)
    result = intake.apply_answer(st, body.answer)
    _save_state(db, sess, st)
    db.commit()
    return {
        "reply": result["reply"],
        "interrupt": result["interrupt"],
        "red_flags": st.red_flags,
        "done": result["done"],
        "next_question": result["next_question"],
        "progress": {"answered": len(st.answers), "total": len(st.protocol)},
        "status": st.status,
    }


@router.post("/intake/{sid}/complete")
def complete_intake(sid: int, body: IntakeCompleteRequest, db: DbDep, user: CurrentUser, request: Request):
    sess = db.get(models.IntakeSession, sid)
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "问诊会话不存在")
    if sess.user_id != user.id and user.role != models.Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作该问诊")
    st = _load_state(sess)
    built = intake.build_record(st)
    encounter_id = None
    if body.create_encounter and body.patient_id:
        from ..security import phi_encrypt
        enc = models.Encounter(
            patient_id=body.patient_id,
            visit_no=body.visit_no or "",
            chief_complaint_enc=phi_encrypt(built["encounter_fields"]["chief_complaint"]),
            history_enc=phi_encrypt(built["encounter_fields"]["history"]),
            meds_enc=phi_encrypt(built["encounter_fields"]["meds"]),
            exams_enc=phi_encrypt(built["encounter_fields"]["exams"]),
            vitals_enc=phi_encrypt(built["encounter_fields"]["vitals"]),
            created_by=user.id,
        )
        db.add(enc)
        db.flush()
        encounter_id = enc.id
        sess.encounter_id = encounter_id
    _save_state(db, sess, st)
    db.commit()
    write_audit(db, user, "intake.complete", "intake_session", str(sid),
                f"encounter={encounter_id}", client_ip(request))
    return {"record": built["record"], "encounter_id": encounter_id,
            "category": st.category, "red_flags": st.red_flags}
