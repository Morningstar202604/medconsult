"""本院经验库（长期学习）：医生对会诊报告的反馈沉淀，反哺后续会诊。

闭环：会诊 → 医生标记「有帮助/需修正」(+修正意见) → 存入经验库 →
后续相似病情的会诊自动检索注入「本院既往经验」，供专家参考（注明来源与局限）。
"""
import json
import os
import re
import threading
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_BASE, "library", "feedback.json")
MAX_ENTRIES = 300

_lock = threading.Lock()


def _load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)


def save(title, diagnosis, helpful, note="", visit=""):
    """记录一条医生反馈；diagnosis 取报告倾向判断，note 为修正意见/理由。"""
    title = (title or "")[:60]
    diagnosis = (diagnosis or "")[:80]
    note = (note or "")[:500]
    if not title and not diagnosis and not note:
        return None
    with _lock:
        items = _load()
        entry = {"id": str(int(time.time() * 1000)),
                 "ts": time.strftime("%Y-%m-%d %H:%M"),
                 "title": title, "visit": (visit or "")[:40],
                 "diagnosis": diagnosis, "helpful": bool(helpful), "note": note}
        items.insert(0, entry)
        _save(items[:MAX_ENTRIES])
        return entry


def list_(limit=50):
    return _load()[:limit]


_STOP = {"患者", "临床", "建议", "治疗", "检查", "报告", "会诊", "医院", "本次", "进行"}


def _bigrams(t):
    out = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", (t or "").lower()):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
        out.add(run)
    return {b for b in out if b not in _STOP}


def similar(text, k=2):
    """检索与当前病情最相关的既往反馈（中文双字重叠加词级匹配），供会诊注入。"""
    q_big = _bigrams(text)
    if not q_big:
        return []
    scored = []
    for e in _load():
        e_big = _bigrams(" ".join([e.get("diagnosis", ""), e.get("title", ""), e.get("note", "")]))
        ov = q_big & e_big
        if ov:
            scored.append((len(ov), e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:k]]
