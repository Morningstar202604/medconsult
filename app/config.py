"""服务端默认配置（config.json，gitignore，不进仓库）。

使平台开箱即用：配置一次 api_key/base_url/model 后，前端无需每次手填。
"""
import json
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(_BASE, "config.json")


def load():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def llm_defaults():
    c = load()
    key = (c.get("api_key") or "").strip()
    if not key:
        return {}
    return {
        "api_key": key,
        "base_url": (c.get("base_url") or "").strip() or None,
        "model": (c.get("model") or "").strip() or None,
    }
