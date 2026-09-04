"""患者与就诊（PHI）。敏感字段经 security.phi_* 加密落库。"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser, client_ip, data_scope, scope_filter, write_audit
from ..schemas import EncounterCreate, PatientCreate

router = APIRouter(tags=["patients"])


@router.get("/patients")
def list_patients(db: DbDep, user: CurrentUser, q: str = "", limit: int = 100):
    scope = data_scope(db, user)
    cond = scope_filter(scope, models.Patient.created_by)
    q = (q or "").strip()
    if q:
        rows = db.scalars(select(models.Patient)
                          .where(models.Patient.hospital_no.contains(q),
                                 *([cond] if cond is not None else []))
                          .order_by(models.Patient.id.desc()).limit(limit)).all()
    else:
        rows = db.scalars(select(models.Patient)
                          .where(*([cond] if cond is not None else []))
                          .order_by(models.Patient.id.desc()).limit(limit)).all()
    return {"items": [_p_public(p, user) for p in rows]}


@router.post("/patients")
def create_patient(body: PatientCreate, db: DbDep, user: CurrentUser,
                   request: Request):
    p = models.Patient(gender=body.gender, birth_date=body.birth_date,
                       hospital_no=body.hospital_no, created_by=user.id)
    p.name = body.name
    p.id_card = body.id_card
    p.phone = body.phone
    db.add(p)
    db.commit()
    db.refresh(p)
    write_audit(db, user, "patient.create", "patient", str(p.id),
                "name=" + (body.name or ""), client_ip(request))
    return _p_public(p, user)


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int, db: DbDep, user: CurrentUser):
    p = _p_visible(db, patient_id, user)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "患者不存在")
    return _p_public(p, user)


@router.get("/patients/{patient_id}/encounters")
def list_encounters(patient_id: int, db: DbDep, user: CurrentUser):
    p = _p_visible(db, patient_id, user)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "患者不存在")
    rows = db.scalars(select(models.Encounter)
                      .where(models.Encounter.patient_id == patient_id)
                      .order_by(models.Encounter.id.desc())).all()
    return {"items": [_e_public(e) for e in rows]}


@router.post("/patients/{patient_id}/encounters")
def create_encounter(patient_id: int, body: EncounterCreate, db: DbDep, user: CurrentUser):
    p = _p_visible(db, patient_id, user)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "患者不存在")
    e = models.Encounter(patient_id=patient_id, visit_no=body.visit_no,
                         created_by=user.id)
    e.chief_complaint_enc = _enc(body.chief_complaint)
    e.history_enc = _enc(body.history)
    e.meds_enc = _enc(body.meds)
    e.exams_enc = _enc(body.exams)
    e.vitals_enc = _enc(body.vitals)
    db.add(e)
    db.commit()
    db.refresh(e)
    write_audit(db, user, "encounter.create", "encounter", str(e.id),
                "patient=" + str(patient_id))
    return _e_public(e)


def _enc(v: str):
    from ..security import phi_encrypt
    return phi_encrypt(v) if v else None


def _p_visible(db: DbDep, patient_id: int, user) -> models.Patient | None:
    """按可见性范围取患者；越权返回 None（与 404 同义，避免泄露存在性）。"""
    p = db.get(models.Patient, patient_id)
    if p is None:
        return None
    scope = data_scope(db, user)
    if scope is not None and p.created_by not in scope:
        return None
    return p


def _mask_id_card(v: str) -> str:
    """身份证/证件号脱敏：保留前3后4，中间打码。"""
    if not v:
        return ""
    if len(v) <= 8:
        return v[0] + "***" + v[-1]
    return v[:3] + "**********" + v[-4:]


def _mask_phone(v: str) -> str:
    """手机号脱敏：保留前3后4，中间打码。"""
    if not v:
        return ""
    if len(v) < 7:
        return v
    return v[:3] + "****" + v[-4:]


def _p_public(p: models.Patient, user: models.User | None = None) -> dict:
    """患者摘要。隐私最小化：普通医生只返回脱敏证件号/手机号，
    管理员与主任可见完整 PHI（用于打印报告、医保对接等业务）。"""
    full = user is not None and user.role in (models.Role.ADMIN, models.Role.CHIEF)
    return {"id": p.id, "name": p.name, "gender": p.gender,
            "birth_date": p.birth_date,
            "id_card": p.id_card if full else _mask_id_card(p.id_card),
            "phone": p.phone if full else _mask_phone(p.phone),
            "hospital_no": p.hospital_no,
            "created_at": p.created_at.isoformat() if p.created_at else None}


def _e_public(e: models.Encounter) -> dict:
    plain = e.to_plain()
    return {"id": e.id, "patient_id": e.patient_id, "visit_no": e.visit_no,
            **plain, "created_at": e.created_at.isoformat() if e.created_at else None}
