"""多模态工具层测试：OCR/ASR 上传、识别结果落库、审计、鉴权。
依赖本地 OCR/ASR 库或 API，测试中用 monkeypatch 模拟识别结果，验证路由与落库链路。
"""
import io
from tests.conftest import auth


def _png_bytes() -> bytes:
    # 1x1 最小 PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )


def _wav_bytes() -> bytes:
    # 最小 WAV 头
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + \
        (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little") + \
        (8000).to_bytes(4, "little") + (1).to_bytes(2, "little") + (8).to_bytes(2, "little") + \
        b"data" + (0).to_bytes(4, "little")


def test_ocr_upload_mocked(client, admin_token, monkeypatch):
    from app.services import media
    monkeypatch.setattr(media, "ocr_image", lambda path, filename="": {
        "text": "白细胞 12.5×10^9/L\n血红蛋白 130g/L",
        "lines": [{"text": "白细胞 12.5×10^9/L", "score": 0.95}],
        "engine": "rapidocr_local", "confidence": "高", "error": "",
    })
    r = client.post("/api/media/ocr", headers=auth(admin_token),
                    files={"file": ("report.png", io.BytesIO(_png_bytes()), "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "image"
    assert "白细胞" in d["text"]
    assert d["engine"] == "rapidocr_local"
    assert d["confidence"] == "高"
    assert d["id"] > 0


def test_asr_upload_mocked(client, admin_token, monkeypatch):
    from app.services import media
    monkeypatch.setattr(media, "asr_audio", lambda path, filename="": {
        "text": "患者胸痛两小时，伴出冷汗",
        "segments": [{"start": 0.0, "end": 2.5, "text": "患者胸痛两小时，伴出冷汗"}],
        "engine": "faster_whisper_local", "confidence": "中", "duration": 2.5, "error": "",
    })
    r = client.post("/api/media/asr", headers=auth(admin_token),
                    files={"file": ("voice.wav", io.BytesIO(_wav_bytes()), "audio/wav")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "audio"
    assert "胸痛" in d["text"]
    assert d["duration"] == 2.5


def test_ocr_unsupported_type(client, admin_token):
    r = client.post("/api/media/ocr", headers=auth(admin_token),
                    files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")})
    assert r.status_code == 400


def test_media_requires_auth(client):
    r = client.post("/api/media/ocr", files={"file": ("x.png", io.BytesIO(_png_bytes()), "image/png")})
    assert r.status_code == 401
    r = client.get("/api/media")
    assert r.status_code == 401


def test_media_list_and_detail(client, admin_token, monkeypatch):
    from app.services import media
    monkeypatch.setattr(media, "ocr_image", lambda path, filename="": {
        "text": "测试报告", "lines": [], "engine": "rapidocr_local",
        "confidence": "中", "error": "",
    })
    up = client.post("/api/media/ocr", headers=auth(admin_token),
                     files={"file": ("r.png", io.BytesIO(_png_bytes()), "image/png")})
    aid = up.json()["id"]
    lst = client.get("/api/media", headers=auth(admin_token))
    assert lst.status_code == 200
    assert lst.json()["total"] >= 1
    det = client.get(f"/api/media/{aid}", headers=auth(admin_token))
    assert det.status_code == 200
    assert det.json()["text"] == "测试报告"
