"""文档检索工具（RAG-lite）：入库时分块索引，按关键词评分检索。

中文按二元组（bigram）+ 英文单词切词，规模在几千块以内足够快、可解释。
分词在入库时预计算存入索引（chunks.json），检索只做交集评分；
索引文件带 mtime 缓存在进程内，避免每次请求重复读盘解析。
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

_cache = {"sig": None, "idx": []}


def _load():
    """读取索引（带 mtime 缓存）。"""
    try:
        st = os.stat(INDEX_PATH)
        sig = (st.st_mtime, st.st_size)
    except OSError:
        return []
    if _cache["sig"] == sig:
        return _cache["idx"]
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = []
    _cache["sig"] = sig
    _cache["idx"] = idx
    return idx


def _save(idx):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    try:
        st = os.stat(INDEX_PATH)
        _cache["sig"] = (st.st_mtime, st.st_size)
    except OSError:
        _cache["sig"] = None
    _cache["idx"] = idx


def _tokens(text):
    text = (text or "").lower()
    out = set(re.findall(r"[a-z0-9]{2,}", text))
    for m in re.finditer(r"[\u4e00-\u9fff]+", text):
        seg = m.group(0)
        out.update(seg[i:i + 2] for i in range(len(seg) - 1))
        out.add(seg)
    return out


def _chunk_tokens(c):
    t = c.get("_tokens")
    if t is None:
        t = _tokens(c["text"])
    return set(t)


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
            idx.append({"doc": name, "cid": j, "text": chunk,
                        "_tokens": sorted(_tokens(chunk))})  # 预存分词，检索免现算
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
        score = len(qt & _chunk_tokens(c))
        if score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"doc": c["doc"], "text": c["text"], "score": s} for s, c in scored[:k]]
