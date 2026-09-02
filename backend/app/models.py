"""ORM 模型。敏感字段以 *_enc 存储（Fernet 加密），通过属性访问解密。"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .security import phi_decrypt, phi_encrypt


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "admin"      # 系统管理员：用户管理、配置
    CHIEF = "chief"      # 主任：反馈审核、审批报告
    DOCTOR = "doctor"    # 医生：会诊、反馈


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.DOCTOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str] = mapped_column(String(8), default="未知")
    birth_date: Mapped[str] = mapped_column(String(20), default="")
    id_card_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    hospital_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    encounters: Mapped[list["Encounter"]] = relationship(back_populates="patient")

    @property
    def name(self) -> str:
        return phi_decrypt(self.name_enc) or ""

    @name.setter
    def name(self, v: str) -> None:
        self.name_enc = phi_encrypt(v)

    @property
    def id_card(self) -> str:
        return phi_decrypt(self.id_card_enc) or ""

    @id_card.setter
    def id_card(self, v: str) -> None:
        self.id_card_enc = phi_encrypt(v)

    @property
    def phone(self) -> str:
        return phi_decrypt(self.phone_enc) or ""

    @phone.setter
    def phone(self, v: str) -> None:
        self.phone_enc = phi_encrypt(v)


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    visit_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    chief_complaint_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    meds_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    exams_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    vitals_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    patient: Mapped["Patient"] = relationship(back_populates="encounters")
    consultations: Mapped[list["Consultation"]] = relationship(back_populates="encounter")

    def to_plain(self) -> dict:
        """解密后的明文（仅用于构建会诊上下文，绝不落日志）。"""
        return {
            "visit_no": self.visit_no,
            "chief_complaint": phi_decrypt(self.chief_complaint_enc) or "",
            "history": phi_decrypt(self.history_enc) or "",
            "meds": phi_decrypt(self.meds_enc) or "",
            "exams": phi_decrypt(self.exams_enc) or "",
            "vitals": phi_decrypt(self.vitals_enc) or "",
        }


class ConsultationMode(str, enum.Enum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    mode: Mapped[ConsultationMode] = mapped_column(Enum(ConsultationMode), default=ConsultationMode.PRODUCTION)
    title: Mapped[str] = mapped_column(String(120), default="未命名会诊")
    status: Mapped[str] = mapped_column(String(24), default="running")  # running|completed|failed
    specialties_json: Mapped[str] = mapped_column(Text, default="[]")
    report_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 非敏感报告字段（明文 JSON）
    data_completeness: Mapped[str] = mapped_column(String(8), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)   # 沙箱生成的报告必须 is_demo=True
    error_msg: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    encounter: Mapped["Encounter | None"] = relationship(back_populates="consultations")
    events: Mapped[list["ConsultationEvent"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan", order_by="ConsultationEvent.id")

    def set_report(self, report: dict) -> None:
        import json

        # 沙箱报告强制打标，前端据此拒绝打印/签名
        if self.mode == ConsultationMode.SANDBOX:
            report["is_demo"] = True
        self.report_json = json.dumps(report, ensure_ascii=False)
        # 报告含敏感结论，落盘加密
        self.report_enc = phi_encrypt(json.dumps(report, ensure_ascii=False))

    def get_report(self) -> dict | None:
        import json

        if self.report_enc:
            try:
                return json.loads(phi_decrypt(self.report_enc) or "{}")
            except Exception:
                return None
        return None


class ConsultationEvent(Base):
    __tablename__ = "consultation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"), index=True)
    role: Mapped[str] = mapped_column(String(24))     # triage|summary|specialist|moderator|tool|report
    name: Mapped[str] = mapped_column(String(64), default="")
    emoji: Mapped[str] = mapped_column(String(8), default="")
    round: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")

    consultation: Mapped["Consultation"] = relationship(back_populates="events")


class FeedbackStatus(str, enum.Enum):
    RECORDED = "recorded"            # 医生提交
    PENDING_REVIEW = "pending_review"  # 待主任审核
    APPROVED = "approved"            # 主任审核通过，可注入
    REJECTED = "rejected"            # 主任驳回


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int | None] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    diagnosis: Mapped[str] = mapped_column(String(200), default="")
    helpful: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[FeedbackStatus] = mapped_column(Enum(FeedbackStatus), default=FeedbackStatus.RECORDED)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(32), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(48), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ext: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    storage_name: Mapped[str] = mapped_column(String(64), default="")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    desc: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReferenceItem(Base):
    __tablename__ = "reference_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item: Mapped[str] = mapped_column(String(64), unique=True)
    en: Mapped[str] = mapped_column(String(64), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    range: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")

class IntakeSession(Base):
    """采集式问诊会话：主诉驱动的结构化病史采集。
    采集结果 fields_json 为 SOAP 结构化字段；对话记录存 consultation_events(role=intake)。
    """
    __tablename__ = "intake_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    chief_complaint: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(32), default="other")
    status: Mapped[str] = mapped_column(String(24), default="collecting")  # collecting|redflag|complete
    fields_json: Mapped[str] = mapped_column(Text, default="{}")   # SOAP 结构化字段
    answers_json: Mapped[str] = mapped_column(Text, default="[]")   # 对话轮次 [{q,a,reason,field}]
    pending_json: Mapped[str] = mapped_column(Text, default="[]")   # 待追问问题
    red_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    flags_urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
class EvidenceItem(Base):
    """证据链：会诊中每个诊断/建议的「依据 + 来源 + 置信度 + 限制」。
    basis_type: guideline|rag|calculator|specialist|moderator|feedback|rule|exam|drug
    """
    __tablename__ = "evidence_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"), index=True)
    claim: Mapped[str] = mapped_column(Text)
    basis_type: Mapped[str] = mapped_column(String(24), default="rule")
    source: Mapped[str] = mapped_column(String(300), default="")
    confidence: Mapped[str] = mapped_column(String(12), default="中")
    limitation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
class ToolCallLog(Base):
    """临床工具调用审计：每个工具调用（计算器/红旗/检查合理性/药物互作/循证检索）
    的输入、输出、置信度与审计备注全部留痕。
    """
    __tablename__ = "tool_call_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int | None] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(48), index=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[str] = mapped_column(String(12), default="中")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MediaAsset(Base):
    """多模态资产：用户上传的图片（检查报告/处方/化验单）或音频（口述问诊/录音会诊）。
    OCR/ASR 结果直接存字段，便于检索与证据链引用；原文件存 media_storage_dir。
    """
    __tablename__ = "media_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)          # image | audio
    filename: Mapped[str] = mapped_column(String(255), default="")
    stored_path: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    # 识别结果
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    asr_text: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(48), default="")         # rapidocr_local / ocr_api_vision / faster_whisper_local / asr_api
    confidence: Mapped[str] = mapped_column(String(12), default="中")
    error_msg: Mapped[str] = mapped_column(Text, default="")
    # 关联（可选）
    consultation_id: Mapped[int | None] = mapped_column(ForeignKey("consultations.id"), nullable=True, index=True)
    intake_session_id: Mapped[int | None] = mapped_column(ForeignKey("intake_sessions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
