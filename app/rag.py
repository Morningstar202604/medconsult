"""文档检索工具（RAG-lite）：入库时分块索引，按关键词评分检索。

中文按二元组（bigram）+ 英文单词切词，规模在几千块以内足够快、可解释。
索引持久化在 library/chunks.json，随文档增删动态更新。
"""
import json
import os
import re
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(_BASE, "library", "chunks.json")

_lock = threading.Lock()
_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60


def _load():
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(idx):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)


def _tokens(text):
    text = (text or "").lower()
    out = set(re.findall(r"[a-z0-9]{2,}", text))
    for m in re.finditer(r"[\u4e00-\u9fff]+", text):
        seg = m.group(0)
        out.update(seg[i:i + 2] for i in range(len(seg) - 1))
        out.add(seg)
    return out


def _split(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + _CHUNK_SIZE])
        if i + _CHUNK_SIZE >= len(text):
            break
        i += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def index_doc(name, text):
    with _lock:
        idx = [c for c in _load() if c["doc"] != name]
        for j, chunk in enumerate(_split(text)):
            idx.append({"doc": name, "cid": j, "text": chunk})
        _save(idx)


def remove_doc(name):
    with _lock:
        idx = [c for c in _load() if c["doc"] != name]
        _save(idx)


def search(query, doc_names=None, k=5):
    """返回 [{doc, text, score}]，按与查询的词重叠度排序。"""
    with _lock:
        idx = _load()
    if doc_names:
        allow = set(doc_names)
        idx = [c for c in idx if c["doc"] in allow]
    if not idx:
        return []
    qt = _tokens(query)
    scored = []
    for c in idx:
        ct = c.get("_tokens")
        if ct is None:
            ct = _tokens(c["text"])
        score = len(qt & ct)
        if score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"doc": c["doc"], "text": c["text"], "score": s} for s, c in scored[:k]]
