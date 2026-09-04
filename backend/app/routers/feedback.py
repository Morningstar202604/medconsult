"""反馈路由：提交（医生）→ 审核（主任/管理员）→ 列表。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser
from ..schemas import FeedbackReview, FeedbackSubmit
from ..services import feedback_service

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def submit(body: FeedbackSubmit, db: DbDep, user: CurrentUser):
    entry = feedback_service.submit_feedback(
        db, body.consultation_id, body.title, body.diagnosis,
        body.helpful, body.note, user.id)
    return {"id": entry.id, "status": entry.status.value}


@router.get("/feedback")
def list_feedback(db: DbDep, user: CurrentUser, status_filter: str = ""):
    if user.role == models.Role.DOCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅主任/管理员可查看反馈")
    q = select(models.Feedback).order_by(models.Feedback.id.desc()).limit(200)
    if status_filter:
        try:
            q = q.where(models.Feedback.status == models.FeedbackStatus(status_filter))
        except ValueError:
            pass
    rows = db.scalars(q).all()
    return {"items": [_fb_view(db, f) for f in rows]}


@router.get("/feedback/{fid}")
def get_feedback(fid: int, db: DbDep, user: CurrentUser):
    """获取单条反馈详情（仅主任/管理员；与列表权限一致）。"""
    if user.role == models.Role.DOCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅主任/管理员可查看反馈")
    fb = db.get(models.Feedback, fid)
    if fb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "反馈不存在")
    return _fb_view(db, fb)


@router.post("/feedback/{fid}/review")
def review(fid: int, body: FeedbackReview, db: DbDep, user: CurrentUser):
    if user.role not in (models.Role.CHIEF, models.Role.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅主任/管理员可审核反馈")
    try:
        entry = feedback_service.review_feedback(db, fid, body.approve, user.id, user.role)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "反馈不存在")
    return {"id": entry.id, "status": entry.status.value}


def _fb_view(db: DbDep, f: models.Feedback) -> dict:
    submitter = db.get(models.User, f.submitted_by)
    reviewer = db.get(models.User, f.reviewed_by) if f.reviewed_by else None
    return {
        "id": f.id, "title": f.title, "diagnosis": f.diagnosis,
        "helpful": f.helpful, "note": f.note, "status": f.status.value,
        "consultation_id": f.consultation_id,
        "submitted_by": submitter.full_name or submitter.username if submitter else "?",
        "reviewed_by": reviewer.full_name or reviewer.username if reviewer else None,
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "expires_at": f.expires_at.isoformat() if f.expires_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
