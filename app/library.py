"""我的文档库：本地硬盘持久化的真实文档（txt/md/pdf/docx 等）。

文档以原始文件形式保存在 library/documents/ 下，列表即扫描目录，
因此增删立即生效、无需重启；会诊时可引用文档内容作为依据。
"""
import hashlib
import os
import re

from . import rag

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_DIR = os.path.join(_BASE, "library", "documents")

TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".log", ".htm", ".html", ".xml"}

MAX_DOC_CHARS = 60000  # 单篇入库上限（超出截断保存）


def _ensure_dir():
    os.makedirs(DOC_DIR, exist_ok=True)


def safe_name(name):
    name = os.path.basename(name or "未命名.txt")
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return name or "未命名.txt"


def doc_id(name):
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _extract_text(path, ext):
    if ext in TEXT_EXTS:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:  # noqa: BLE001
            return "[PDF 解析失败：{}]".format(e)
    if ext == ".docx":
        try:
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs if p.text.strip())
        except Exception as e:  # noqa: BLE001
            return "[DOCX 解析失败：{}]".format(e)
    # 未知扩展名：尝试按文本读
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return "[暂不支持该格式的文本提取，已保存原文件：{}]".format(ext)


def meta(name):
    for d in list_docs():
        if d["name"] == name:
            return d
    return {"id": doc_id(safe_name(name)), "name": safe_name(name), "size": 0, "mtime": 0, "preview": ""}


def save_bytes(name, data: bytes):
    _ensure_dir()
    name = safe_name(name)
    ext = os.path.splitext(name)[1].lower()
    path = os.path.join(DOC_DIR, name)
    with open(path, "wb") as f:
        f.write(data)
    text = _extract_text(path, ext)
    with open(path + ".txt", "w", encoding="utf-8") as f:
        f.write(text[:MAX_DOC_CHARS])
    rag.index_doc(name, text)  # 检索工具：入库即建分块索引
    return meta(name)


def save_text(name, content: str):
    return save_bytes(name, (content or "").encode("utf-8"))


def delete(name):
    name = safe_name(name)
    path = os.path.join(DOC_DIR, name)
    removed = False
    for p in (path, path + ".txt"):
        if os.path.exists(p):
            os.remove(p)
            removed = True
    if removed:
        rag.remove_doc(name)
    return removed


def list_docs():
    _ensure_dir()
    out = []
    for fn in sorted(os.listdir(DOC_DIR)):
        if fn.endswith(".txt") and os.path.exists(os.path.join(DOC_DIR, fn[:-4])):
            continue  # 提取文本附属文件不单列
        if fn.endswith((".pdf", ".docx")) and not os.path.exists(os.path.join(DOC_DIR, fn + ".txt")):
            continue  # 原始文件尚未完成解析的跳过（极少见）
        path = os.path.join(DOC_DIR, fn)
        if not os.path.isfile(path):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        preview = ""
        text_path = path + ".txt"
        src = text_path if os.path.exists(text_path) else path
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                preview = f.read(140).replace("\n", " ")
        except OSError:
            pass
        out.append({
            "id": doc_id(fn),
            "name": fn,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "preview": preview,
        })
    return out


def get_text(name):
    name = safe_name(name)
    text_path = os.path.join(DOC_DIR, name + ".txt")
    path = os.path.join(DOC_DIR, name)
    src = text_path if os.path.exists(text_path) else path
    if not os.path.exists(src):
        return ""
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def get_texts_by_ids(ids, each_cap=2500, total_cap=10000):
    """按前端传来的 doc_id 列表取内容（每篇截断，总量封顶）。"""
    if not ids:
        return []
    by_id = {doc_id(d["name"]): d["name"] for d in list_docs()}
    out, used = [], 0
    for i in ids:
        name = by_id.get(str(i))
        if not name:
            continue
        text = get_text(name)[:each_cap]
        if not text.strip():
            continue
        used += len(text)
        if used > total_cap:
            text = text[:max(0, each_cap - (used - total_cap))]
            if not text.strip():
                break
            out.append({"name": name, "content": text, "truncated": True})
            break
        out.append({"name": name, "content": text})
    return out


def reindex_all():
    """启动迁移：为尚未建立检索索引的历史文档补建分块索引。"""
    _ensure_dir()
    idx_path = os.path.join(_BASE, "library", "chunks.json")
    have = set()
    try:
        with open(idx_path, "r", encoding="utf-8") as f:
            have = {c["doc"] for c in json.load(f)}
    except Exception:
        pass
    for fn in os.listdir(DOC_DIR):
        if fn.endswith(".txt") and os.path.exists(os.path.join(DOC_DIR, fn[:-4])):
            continue  # 提取文本附属文件不重复索引
        if fn in have:
            continue
        text = get_text(fn)
        if text.strip():
            rag.index_doc(fn, text)
