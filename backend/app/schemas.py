"""API 请求/响应模型（Pydantic）。"""
from pydantic import BaseModel, Field


# ---- auth ----
class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = ""
    role: str = "doctor"  # admin|chief|doctor


class UserUpdate(BaseModel):
    is_active: bool | None = None
    full_name: str | None = None


# ---- patient / encounter ----
class PatientCreate(BaseModel):
    name: str = ""
    gender: str = "未知"
    birth_date: str = ""
    id_card: str = ""
    phone: str = ""
    hospital_no: str = ""


class EncounterCreate(BaseModel):
    visit_no: str = ""
    chief_complaint: str = ""
    history: str = ""
    meds: str = ""
    exams: str = ""
    vitals: str = ""


# ---- consultation ----
class ConsultRequest(BaseModel):
    mode: str = "production"            # production | sandbox
    encounter_id: int | None = None
    text: str = Field(default="", max_length=6000)
    specialties: list[str] = Field(default_factory=list)
    skills: list[int] = Field(default_factory=list)
    doc_ids: list[int] = Field(default_factory=list)
    style: str = "brief"                # brief|detailed|evidence
    rounds: int = Field(default=2, ge=1, le=4)


class FollowupRequest(BaseModel):
    consultation_id: int
    text: str = Field(min_length=1, max_length=2000)


# ---- feedback ----
class FeedbackSubmit(BaseModel):
    consultation_id: int | None = None
    title: str = ""
    diagnosis: str = ""
    helpful: bool = True
    note: str = Field(default="", max_length=2000)


class FeedbackReview(BaseModel):
    approve: bool


# ---- library ----
class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    desc: str = ""
    prompt: str = Field(min_length=1)


class ReferenceCreate(BaseModel):
    item: str = Field(min_length=1, max_length=64)
    en: str = ""
    unit: str = ""
    range: str = ""
    note: str = ""


class ReferenceDelete(BaseModel):
    item: str
# ---- intake（采集式问诊） ----
class IntakeStartRequest(BaseModel):
    chief_complaint: str = Field(min_length=1, max_length=300)
    patient_id: int | None = None
class IntakeAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
class IntakeCompleteRequest(BaseModel):
    create_encounter: bool = True
    patient_id: int | None = None
    visit_no: str = ""
