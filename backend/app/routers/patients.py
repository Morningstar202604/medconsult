"""患者与就诊（PHI）。敏感字段经 security.phi_* 加密落库。"""
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser, client_ip, write_audit
from ..schemas import EncounterCreate, PatientCreate

router = APIRouter(tags=["patients"])


@router.get("/patients")
def list_patients(db: DbDep, user: CurrentUser, q: str = "", limit: int = 100):
    q = (q or "").strip()
    if q:
        rows = db.scalars(select(models.Patient)
                          .where(models.Patient.hospital_no.contains(q))
                          .order_by(models.Patient.id.desc()).limit(limit)).all()
    else:
        rows = db.scalars(select(models.Patient)
                          .order_by(models.Patient.id.desc()).limit(limit)).all()
    return {"items": [_p_public(p) for p in rows]}


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
    return _p_public(p)


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int, db: DbDep, user: CurrentUser):
    p = db.get(models.Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "患者不存在")
    return _p_public(p)


@router.get("/patients/{patient_id}/encounters")
def list_encounters(patient_id: int, db: DbDep, user: CurrentUser):
    rows = db.scalars(select(models.Encounter)
                      .where(models.Encounter.patient_id == patient_id)
                      .order_by(models.Encounter.id.desc())).all()
    return {"items": [_e_public(e) for e in rows]}


@router.post("/patients/{patient_id}/encounters")
def create_encounter(patient_id: int, body: EncounterCreate, db: DbDep, user: CurrentUser):
    if db.get(models.Patient, patient_id) is None:
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


def _p_public(p: models.Patient) -> dict:
    return {"id": p.id, "name": p.name, "gender": p.gender,
            "birth_date": p.birth_date, "id_card": p.id_card,
            "phone": p.phone, "hospital_no": p.hospital_no,
            "created_at": p.created_at.isoformat() if p.created_at else None}


def _e_public(e: models.Encounter) -> dict:
    plain = e.to_plain()
    return {"id": e.id, "patient_id": e.patient_id, "visit_no": e.visit_no,
            **plain, "created_at": e.created_at.isoformat() if e.created_at else None}
