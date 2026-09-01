"""多模态媒体路由：上传图片/音频 → OCR/ASR 识别 → 落库 + 审计。

无多模态模型时走本地工具兜底（rapidocr / faster-whisper / edge-tts），
有配置时走用户自填的 API provider。识别结果可一键填入会诊描述或问诊回答。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..deps import CurrentUser, DbDep, client_ip, write_audit
from ..services import toolbox

router = APIRouter(tags=["media"])

_ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".webm", ".mp4"}
_MAX_SIZE = 50 * 1024 * 1024  # 50MB


def _storage_dir() -> Path:
    settings = get_settings()
    p = Path(settings.media_storage_dir)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_upload(file: UploadFile, kind: str) -> tuple[Path, int]:
    ext = Path(file.filename or "").suffix.lower()
    allowed = _ALLOWED_IMAGE if kind == "image" else _ALLOWED_AUDIO
    if ext and ext not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"不支持的文件类型 {ext}；允许：{','.join(sorted(allowed))}")
    data = file.file.read()
    if len(data) > _MAX_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件超过 50MB 限制")
    stored = _storage_dir() / f"{uuid.uuid4().hex}{ext or ''}"
    stored.write_bytes(data)
    return stored, len(data)


def _asset_to_dict(a: models.MediaAsset) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "filename": a.filename,
        "size_bytes": a.size_bytes,
        "mime_type": a.mime_type,
        "engine": a.engine,
        "confidence": a.confidence,
        "error_msg": a.error_msg,
        "text": a.ocr_text or a.asr_text,
        "consultation_id": a.consultation_id,
        "intake_session_id": a.intake_session_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/media/ocr")
def ocr_upload(
    file: UploadFile = File(...),
    consultation_id: int | None = Form(None),
    intake_session_id: int | None = Form(None),
    db: Session = Depends(DbDep),
    user: models.User = Depends(CurrentUser),
):
    """上传图片 → OCR 识别文字（检查报告/处方/化验单）。"""
    stored, size = _save_upload(file, "image")
    try:
        result = toolbox.run_ocr(db, consultation_id, str(stored), file.filename or "")
    finally:
        pass  # 原文件保留，供下载
    asset = models.MediaAsset(
        user_id=user.id, kind="image", filename=file.filename or "",
        stored_path=str(stored), size_bytes=size, mime_type=file.content_type or "",
        ocr_text=result.get("text", ""), engine=result.get("engine", ""),
        confidence=result.get("confidence", "中"), error_msg=result.get("error", ""),
        consultation_id=consultation_id, intake_session_id=intake_session_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    write_audit(db, user, "media.ocr", "media_asset", str(asset.id),
                f"file={asset.filename} engine={asset.engine} chars={len(asset.ocr_text)}",
                client_ip(request))
    return {**_asset_to_dict(asset), "lines": result.get("lines", [])}


@router.post("/media/asr")
def asr_upload(
    request: Request,
    file: UploadFile = File(...),
    consultation_id: int | None = Form(None),
    intake_session_id: int | None = Form(None),
    db: Session = Depends(DbDep),
    user: models.User = Depends(CurrentUser),
):
    """上传音频 → ASR 转写文字（口述问诊/录音会诊）。"""
    stored, size = _save_upload(file, "audio")
    result = toolbox.run_asr(db, consultation_id, str(stored), file.filename or "")
    asset = models.MediaAsset(
        user_id=user.id, kind="audio", filename=file.filename or "",
        stored_path=str(stored), size_bytes=size, mime_type=file.content_type or "",
        asr_text=result.get("text", ""), engine=result.get("engine", ""),
        confidence=result.get("confidence", "中"), error_msg=result.get("error", ""),
        consultation_id=consultation_id, intake_session_id=intake_session_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    write_audit(db, user, "media.asr", "media_asset", str(asset.id),
                f"file={asset.filename} engine={asset.engine} chars={len(asset.asr_text)}",
                client_ip(request))
    return {**_asset_to_dict(asset), "segments": result.get("segments", []),
            "duration": result.get("duration", 0.0)}


@router.get("/media")
def list_media(db: Session = Depends(DbDep), user: models.User = Depends(CurrentUser),
               kind: str | None = None, limit: int = 50, offset: int = 0):
    q = db.query(models.MediaAsset).filter(models.MediaAsset.user_id == user.id)
    if kind:
        q = q.filter(models.MediaAsset.kind == kind)
    total = q.count()
    items = q.order_by(models.MediaAsset.id.desc()).offset(offset).limit(min(limit, 100)).all()
    return {"total": total, "items": [_asset_to_dict(a) for a in items]}


@router.get("/media/{asset_id}")
def get_media(asset_id: int, db: Session = Depends(DbDep),
              user: models.User = Depends(CurrentUser)):
    a = db.get(models.MediaAsset, asset_id)
    if a is None or (a.user_id != user.id and user.role != models.Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "媒体资源不存在")
    return _asset_to_dict(a)


@router.get("/media/{asset_id}/download")
def download_media(asset_id: int, db: Session = Depends(DbDep),
                   user: models.User = Depends(CurrentUser)):
    a = db.get(models.MediaAsset, asset_id)
    if a is None or (a.user_id != user.id and user.role != models.Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "媒体资源不存在")
    if not a.stored_path or not os.path.exists(a.stored_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原文件已丢失")
    return FileResponse(a.stored_path, filename=a.filename or f"media_{a.id}",
                        media_type=a.mime_type or "application/octet-stream")
