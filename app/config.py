"""服务端默认配置（config.json，gitignore，不进仓库）。

使平台开箱即用：配置一次 api_key/base_url/model 后，前端无需每次手填。
也支持环境变量覆盖：MEDCONSULT_API_KEY / MEDCONSULT_BASE_URL / MEDCONSULT_MODEL
（优先级高于 config.json，便于容器化部署时注入密钥）。
"""
import json
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(_BASE, "config.json")

_cache = {"sig": None, "data": {}}


def load():
    try:
        st = os.stat(CFG_PATH)
        sig = (st.st_mtime, st.st_size)
    except OSError:
        _cache["sig"] = None
        _cache["data"] = {}
        return {}
    if _cache["sig"] == sig:
        return _cache["data"]
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    _cache["sig"] = sig
    _cache["data"] = data
    return data


def llm_defaults():
    c = load()
    key = (os.environ.get("MEDCONSULT_API_KEY") or c.get("api_key") or "").strip()
    if not key:
        return {}
    base = (os.environ.get("MEDCONSULT_BASE_URL") or c.get("base_url") or "").strip() or None
    model = (os.environ.get("MEDCONSULT_MODEL") or c.get("model") or "").strip() or None
    return {"api_key": key, "base_url": base, "model": model}


def hospital_name():
    """机构名称：报告抬头与打印用（config.json 的 hospital_name，缺省为通用名称）。"""
    c = load()
    return (os.environ.get("MEDCONSULT_HOSPITAL") or c.get("hospital_name") or "").strip() or "汇诊会诊中心"


def hospital_policy():
    """医院规范文本：注入每个会诊智能体的系统提示词（提示词工程的机构层）。

    医院可在此写用药目录约束、检查路径、会诊时限等本院规范；留空则不注入。
    """
    c = load()
    return (c.get("hospital_policy") or "").strip()


def report_footer():
    """打印报告页脚备注（可选）。"""
    c = load()
    return (c.get("report_footer") or "").strip()
