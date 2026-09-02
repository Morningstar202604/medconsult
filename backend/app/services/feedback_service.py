"""反馈四段审核流：recorded → pending_review → approved / rejected。

核心修复：
- 反馈必须先经主任审核通过，才可注入后续会诊；
- 注入内容强制携带来源、提交人、审核人、时间；
- 支持过期（expires_at）与自动失效。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..deps import write_audit


def submit_feedback(
    db: Session,
    consultation_id: int | None,
    title: str,
    diagnosis: str,
    helpful: bool,
    note: str,
    submitted_by: int,
) -> models.Feedback:
    """医生提交反馈 → 状态为 pending_review（待主任审核）。"""
    entry = models.Feedback(
        consultation_id=consultation_id,
        title=(title or "")[:120],
        diagnosis=(diagnosis or "")[:200],
        helpful=helpful,
        note=(note or "")[:2000],
        status=models.FeedbackStatus.PENDING_REVIEW,
        submitted_by=submitted_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    write_audit(db, db.get(models.User, submitted_by), "feedback.submit",
                "feedback", str(entry.id), f"title={entry.title}")
    return entry


def review_feedback(
    db: Session,
    feedback_id: int,
    approve: bool,
    reviewer_id: int,
    reviewer_role: models.Role,
) -> models.Feedback | None:
    """主任审核：通过 → approved（带过期时间）；驳回 → rejected。"""
    if reviewer_role != models.Role.CHIEF and reviewer_role != models.Role.ADMIN:
        raise PermissionError("仅主任/管理员可审核反馈")
    fb = db.get(models.Feedback, feedback_id)
    if fb is None:
        return None
    now = datetime.now(timezone.utc)
    if approve:
        fb.status = models.FeedbackStatus.APPROVED
        fb.reviewed_by = reviewer_id
        fb.reviewed_at = now
        fb.expires_at = now + timedelta(days=get_settings().retention_days)
    else:
        fb.status = models.FeedbackStatus.REJECTED
        fb.reviewed_by = reviewer_id
        fb.reviewed_at = now
        fb.expires_at = None
    db.commit()
    db.refresh(fb)
    write_audit(db, db.get(models.User, reviewer_id), "feedback.review",
                "feedback", str(feedback_id), f"approve={approve}")
    return fb


def injectable_feedback(db: Session, query_text: str, k: int = 2) -> list[dict]:
    """仅注入：approved 且未过期 的反馈，按中英混合 token 重叠取前 k 条。
    返回内容含来源与审核信息。反馈经人工审核，相关性门槛比 RAG 更宽（≥1 token
    重叠），以兼容 CAP/CRP/PCT 等英文缩写为主的经验。
    """
    from ..rag.index import _tokens

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(models.Feedback).where(
            models.Feedback.status == models.FeedbackStatus.APPROVED,
            (models.Feedback.expires_at.is_(None)) | (models.Feedback.expires_at > now),
        )
    ).scalars().all()
    qt = _tokens(query_text)
    if not qt:
        return []
    scored = []
    for fb in rows:
        blob = " ".join([fb.diagnosis, fb.title, fb.note])
        score = len(qt & _tokens(blob))
        if score >= 1:
            submitted_by = db.get(models.User, fb.submitted_by)
            reviewed_by = db.get(models.User, fb.reviewed_by) if fb.reviewed_by else None
            scored.append((score, {
                "diagnosis": fb.diagnosis,
                "note": fb.note,
                "helpful": fb.helpful,
                "submitted_by": submitted_by.full_name if submitted_by else "?",
                "reviewed_by": reviewed_by.full_name if reviewed_by else "?",
                "approved_at": fb.reviewed_at.strftime("%Y-%m-%d") if fb.reviewed_at else "",
            }))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:k]]
