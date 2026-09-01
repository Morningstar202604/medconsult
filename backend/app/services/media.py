"""多模态工具层：OCR（图片文字识别）/ ASR（语音转文字）/ TTS（语音合成）。

设计原则（与用户约定一致）：
1. 多模态模型让用户自己填 provider（OCR_API_URL / ASR_API_URL / TTS_API_URL，OpenAI 兼容）；
2. 没有多模态模型时，用本地工具兜底识别（rapidocr / faster-whisper / edge-tts）；
3. 所有识别结果结构化返回（text/engine/confidence/error），上层走 toolbox 审计 + 证据链。

依赖均为可选：未安装本地库且未配置 API 时，返回明确 error，不崩溃。
"""
from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

import httpx

from ..config import get_settings


# ---------------------------------------------------------------- OCR
def ocr_image(image_path: str, filename: str = "") -> dict:
    """识别图片中的文字（检查报告/处方/化验单）。

    优先级：配置的 OCR_API（OpenAI 兼容 vision）> 本地 rapidocr > 报错。
    返回 {text, lines, engine, confidence, error}。
    """
    settings = get_settings()
    # ---- 1. API 模式（OpenAI 兼容 vision）----
    if settings.ocr_api_url:
        try:
            return _ocr_via_api(image_path, filename, settings)
        except Exception as e:
            return {"text": "", "lines": [], "engine": "ocr_api",
                    "confidence": "低", "error": f"OCR API 调用失败：{e}"}
    # ---- 2. 本地 rapidocr 兜底 ----
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {"text": "", "lines": [], "engine": "none",
                "confidence": "低",
                "error": "未配置 OCR_API 且未安装本地 OCR（pip install rapidocr-onnxruntime）"}
    try:
        engine = RapidOCR()
        result, _ = engine(image_path)
        lines = []
        if result:
            for item in result:
                # rapidocr 返回 [box, text, score]
                if len(item) >= 2:
                    lines.append({"text": str(item[1]),
                                  "score": float(item[2]) if len(item) >= 3 else 0.0})
        text = "\n".join(l["text"] for l in lines)
        avg = sum(l["score"] for l in lines) / len(lines) if lines else 0.0
        confidence = "高" if avg >= 0.85 else ("中" if avg >= 0.6 else "低")
        return {"text": text, "lines": lines, "engine": "rapidocr_local",
                "confidence": confidence, "error": ""}
    except Exception as e:
        return {"text": "", "lines": [], "engine": "rapidocr_local",
                "confidence": "低", "error": f"本地 OCR 识别失败：{e}"}


def _ocr_via_api(image_path: str, filename: str, settings) -> dict:
    """通过 OpenAI 兼容 vision 接口识别图片文字。"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = "image/png"
    ext = Path(filename or image_path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    url = settings.ocr_api_url
    # 若用户给的是 base_url（不含 /chat/completions），补全
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.ocr_api_model or settings.llm_default_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "请逐行识别这张医疗图片中的全部文字（检查报告/处方/化验单），"
                                          "保留原始排版与数值，不要解释、不要翻译、不要遗漏。"},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "temperature": 0.0,
        "max_tokens": 2000,
    }
    headers = {"Content-Type": "application/json"}
    if settings.ocr_api_key:
        headers["Authorization"] = f"Bearer {settings.ocr_api_key}"
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    text = (data["choices"][0]["message"]["content"] or "").strip()
    lines = [{"text": ln, "score": 0.0} for ln in text.splitlines() if ln.strip()]
    return {"text": text, "lines": lines, "engine": "ocr_api_vision",
            "confidence": "中", "error": ""}


# ---------------------------------------------------------------- ASR
def asr_audio(audio_path: str, filename: str = "") -> dict:
    """语音转文字（口述问诊/录音会诊）。

    优先级：配置的 ASR_API（OpenAI 兼容 /audio/transcriptions）> 本地 faster-whisper > 报错。
    返回 {text, segments, engine, confidence, duration, error}。
    """
    settings = get_settings()
    if settings.asr_api_url:
        try:
            return _asr_via_api(audio_path, filename, settings)
        except Exception as e:
            return {"text": "", "segments": [], "engine": "asr_api",
                    "confidence": "低", "duration": 0.0, "error": f"ASR API 调用失败：{e}"}
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"text": "", "segments": [], "engine": "none",
                "confidence": "低", "duration": 0.0,
                "error": "未配置 ASR_API 且未安装本地 ASR（pip install faster-whisper）"}
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language="zh", beam_size=1)
        segs = []
        for seg in segments:
            segs.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                         "text": seg.text.strip(), "avg_logprob": getattr(seg, "avg_logprob", 0.0)})
        text = "".join(s["text"] for s in segs)
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        return {"text": text, "segments": segs, "engine": "faster_whisper_local",
                "confidence": "中", "duration": duration, "error": ""}
    except Exception as e:
        return {"text": "", "segments": [], "engine": "faster_whisper_local",
                "confidence": "低", "duration": 0.0, "error": f"本地 ASR 识别失败：{e}"}


def _asr_via_api(audio_path: str, filename: str, settings) -> dict:
    """通过 OpenAI 兼容 /audio/transcriptions 转写音频。"""
    url = settings.asr_api_url
    if not url.endswith("/audio/transcriptions"):
        url = url.rstrip("/") + "/audio/transcriptions"
    headers = {}
    if settings.asr_api_key:
        headers["Authorization"] = f"Bearer {settings.asr_api_key}"
    with open(audio_path, "rb") as f:
        files = {"file": (filename or os.path.basename(audio_path), f,
                           "application/octet-stream")}
        data = {"model": settings.asr_api_model, "language": "zh",
                "response_format": "json"}
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
    text = (result.get("text") or "").strip()
    return {"text": text, "segments": [], "engine": "asr_api",
            "confidence": "中", "duration": 0.0, "error": ""}


# ---------------------------------------------------------------- TTS
def tts_speak(text: str, out_path: str) -> dict:
    """文本转语音（报告朗读）。优先级：TTS_API > edge-tts > 报错。"""
    settings = get_settings()
    if settings.tts_api_url:
        try:
            return _tts_via_api(text, out_path, settings)
        except Exception as e:
            return {"path": "", "engine": "tts_api", "error": f"TTS API 调用失败：{e}"}
    try:
        import edge_tts
    except ImportError:
        return {"path": "", "engine": "none",
                "error": "未配置 TTS_API 且未安装 edge-tts（pip install edge-tts）"}
    try:
        asyncio.run(_edge_tts_save(text, out_path, settings.tts_voice))
        return {"path": out_path, "engine": "edge_tts", "error": ""}
    except Exception as e:
        return {"path": "", "engine": "edge_tts", "error": f"edge-tts 合成失败：{e}"}


async def _edge_tts_save(text: str, out_path: str, voice: str) -> None:
    communicate = __import__("edge_tts").Communicate(text, voice)
    await communicate.save(out_path)


def _tts_via_api(text: str, out_path: str, settings) -> dict:
    url = settings.tts_api_url
    if not url.endswith("/audio/speech"):
        url = url.rstrip("/") + "/audio/speech"
    headers = {"Content-Type": "application/json"}
    if settings.tts_api_key:
        headers["Authorization"] = f"Bearer {settings.tts_api_key}"
    payload = {"model": "tts-1", "input": text, "voice": settings.tts_voice,
               "response_format": "mp3"}
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
    return {"path": out_path, "engine": "tts_api", "error": ""}
