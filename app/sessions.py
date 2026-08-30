"""会诊记录（记忆）：每场会诊自动持久化到 library/sessions.json。"""
import json
import os
import threading
import time
import uuid

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_BASE, "library", "sessions.json")
MAX_SESSIONS = 100

_lock = threading.Lock()


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def save(mode, title, items, report=None):
    with _lock:
        data = _load()
        entry = {
            # 时间戳 + 随机后缀：避免同一毫秒内连存两条时 ID 撞车、删除误伤
            "id": "{}-{}".format(int(time.time() * 1000), uuid.uuid4().hex[:6]),
            "ts": time.strftime("%Y-%m-%d %H:%M"),
            "mode": mode,
            "title": (title or "未命名会诊")[:60],
            "items": items or [],
            "report": report,
        }
        data.insert(0, entry)
        _save(data[:MAX_SESSIONS])
        return entry["id"]


def list_(limit=30):
    return [{"id": s["id"], "ts": s["ts"], "mode": s["mode"], "title": s["title"]}
            for s in _load()[:limit]]


def get(sid):
    for s in _load():
        if s["id"] == sid:
            return s
    return None


def delete(sid):
    with _lock:
        data = _load()
        data = [s for s in data if s["id"] != sid]
        _save(data)


def clear():
    with _lock:
        _save([])
