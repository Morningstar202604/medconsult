"""RAG 检索：分块 + 中文二元组/英文词 token + 相关度阈值。

相对原版改进：检索结果必须达到阈值（≥2 个重叠 token，或精确命中），
避免"任何重叠都注入"，把无关旧文档标成"会诊必须基于的真实内容"。
"""
import json
import os
import re
import threading
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
INDEX_PATH = _BASE / "data" / "rag_index.json"
_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60
_MIN_OVERLAP = 2  # 相关度阈值

_lock = threading.Lock()


def _tokens(text: str) -> set[str]:
    t = (text or "").lower()
    out = set(re.findall(r"[a-z0-9]{2,}", t))
    for m in re.finditer(r"[\u4e00-\u9fff]+", t):
        seg = m.group(0)
        out.update(seg[i:i + 2] for i in range(len(seg) - 1))
        out.add(seg)
    return out


def _split(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + _CHUNK_SIZE])
        if i + _CHUNK_SIZE >= len(text):
            break
        i += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def _load() -> list[dict]:
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(idx: list[dict]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)


def index_doc(name: str, text: str) -> None:
    with _lock:
        idx = [c for c in _load() if c["doc"] != name]
        for j, chunk in enumerate(_split(text)):
            idx.append({"doc": name, "cid": j, "text": chunk,
                        "_tokens": sorted(_tokens(chunk))})
        _save(idx)


def remove_doc(name: str) -> None:
    with _lock:
        _save([c for c in _load() if c["doc"] != name])


def search(query: str, k: int = 6) -> list[dict]:
    """返回 [{doc, text, score}]；score 低于阈值或完全无关的丢弃。"""
    with _lock:
        idx = _load()
    if not idx or not (query or "").strip():
        return []
    qt = _tokens(query)
    if not qt:
        return []
    scored = []
    for c in idx:
        overlap = len(qt & set(c.get("_tokens") or []))
        if overlap >= _MIN_OVERLAP:
            scored.append((overlap, c))
    scored.sort(key=lambda x: -x[0])
    return [{"doc": c["doc"], "text": c["text"], "score": s} for s, c in scored[:k]]


def clear() -> None:
    with _lock:
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
