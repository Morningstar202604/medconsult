"""提示词池：按角色保存/载入/删除命名提示词预设（library/prompts.json）。"""
import json
import os
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_BASE, "library", "prompts.json")

_lock = threading.Lock()


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def list_pool():
    return {role: list(names.keys()) for role, names in _load().items()}


def dump():
    return _load()


def get(role, name):
    return _load().get(role, {}).get(name)


def save(role, name, text):
    if not role or not name or not (text or "").strip():
        return False
    with _lock:
        data = _load()
        data.setdefault(role, {})[name] = text
        _save(data)
    return True


def delete(role, name):
    with _lock:
        data = _load()
        if role in data and name in data[role]:
            del data[role][name]
            _save(data)
            return True
    return False
