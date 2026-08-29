"""Consultation platform web server (Python stdlib only, no extra deps).

Run:  .venv/Scripts/python server.py  ->  http://127.0.0.1:8000
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import cases as cases_mod
from app import config as app_config
from app import engine
from app import library
from app import mdt
from app import prompts as prompts_mod
from app import rag
from app import sessions as sessions_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
HOST, PORT = "127.0.0.1", 8765

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------------- helpers ----------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---------------- API ----------------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/datasets":
            out = []
            for name in cases_mod.DATA_FILES:
                cs = cases_mod.list_cases(name)
                out.append({"name": name, "zh_name": cases_mod.dataset_zh(name),
                            "count": len(cs),
                            "cases": [c.public_view() for c in cs]})
            return self._json({"datasets": out})
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/api/defaults":  # 服务端默认 LLM 配置（不回传 key 本体）
            d = app_config.llm_defaults()
            return self._json({"has_key": bool(d), "base_url": d.get("base_url") or "", "model": d.get("model") or ""})
        if path == "/api/library":
            return self._json({"docs": library.list_docs()})
        if path.startswith("/api/library/doc"):
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            return self._json({"name": unquote(qs.get("name", [""])[0]),
                               "content": library.get_text(unquote(qs.get("name", [""])[0]))})
        if path == "/api/search":  # 文档检索工具
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            return self._json({"results": rag.search(unquote(qs.get("q", [""])[0]), None,
                                                     int(qs.get("k", ["5"])[0] or 5))})
        if path == "/api/sessions":  # 会诊记录（记忆）
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            if qs.get("id"):
                return self._json({"session": sessions_mod.get(qs["id"][0])})
            return self._json({"sessions": sessions_mod.list_()})
        if path == "/api/prompts":  # 提示词池
            return self._json({"pool": prompts_mod.dump(), "names": prompts_mod.list_pool()})
        return self._static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/library/upload":  # 原始字节上传：必须在解析 JSON body 之前处理
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            name = unquote(qs.get("name", ["未命名.txt"])[0])
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n) if n else b""
                if not data:
                    return self._json({"error": "空文件"}, 400)
                return self._json({"doc": library.save_bytes(name, data)})
            except Exception as e:  # noqa: BLE001
                return self._json({"error": "server error: %s" % e}, 500)
        body = self._body()
        try:
            if path == "/api/step":  # auto (AI doctor) mode
                result = engine.auto_step(
                    body.get("dataset"), body.get("case_id"),
                    body.get("history"), body.get("settings"))
                return self._json({"event": result})
            if path == "/api/ask":  # human doctor mode
                result = engine.ask(
                    body.get("dataset"), body.get("case_id"),
                    body.get("question"), body.get("history"), body.get("settings"))
                return self._json({"event": result})
            if path == "/api/test_llm":  # connectivity test from the settings dialog
                s = body or {}
                if s.get("mode") != "llm":
                    return self._json({"ok": True, "reply": "模拟演示模式，无需连接。"})
                model = (s.get("doctor_model") or s.get("model") or "gpt-4o-mini").strip()
                try:
                    reply = engine.llm.chat(
                        model, "You are a connectivity test.", "Reply with exactly: OK",
                        (s.get("api_key") or "").strip(),
                        (s.get("base_url") or "").strip() or None,
                        max_tokens=10, temperature=0)
                    return self._json({"ok": True, "reply": reply})
                except Exception as e:  # noqa: BLE001
                    return self._json({"ok": False, "error": str(e)})
            if path == "/api/mdt/clarify":  # 预问诊追问
                text = (body.get("text") or "").strip()
                if len(text) < 5:
                    return self._json({"error": "请先描述病情（至少 5 个字）"}, 400)
                return self._json({"questions": mdt.clarify(text, body.get("settings"))})
            if path == "/api/library/text":  # 粘贴文本入库
                if not (body.get("content") or "").strip():
                    return self._json({"error": "内容为空"}, 400)
                return self._json({"doc": library.save_text(body.get("name") or "粘贴文档.txt", body.get("content"))})
            if path == "/api/library/delete":
                names = body.get("names") or ([body.get("name")] if body.get("name") else [])
                for nm in names:
                    library.delete(nm)
                return self._json({"ok": True})
            if path == "/api/sessions/save":  # 会诊结束自动存档（记忆）
                sid = sessions_mod.save(body.get("mode"), body.get("title"),
                                        body.get("items"), body.get("report"))
                return self._json({"id": sid})
            if path == "/api/sessions/delete":
                sessions_mod.delete(body.get("id"))
                return self._json({"ok": True})
            if path == "/api/sessions/clear":
                sessions_mod.clear()
                return self._json({"ok": True})
            if path == "/api/prompts/save":  # 提示词池
                ok = prompts_mod.save(body.get("role"), body.get("name"), body.get("text"))
                return self._json({"ok": bool(ok)})
            if path == "/api/prompts/delete":
                return self._json({"ok": prompts_mod.delete(body.get("role"), body.get("name"))})
            if path == "/api/mdt":  # MDT 多学科会诊：用户提交病情 -> 多专科讨论 -> 共识报告
                text = (body.get("text") or "").strip()
                if len(text) < 5:
                    return self._json({"error": "请先描述病情（至少 5 个字）"}, 400)
                result = mdt.consult(
                    text, body.get("settings"),
                    body.get("dataset"), body.get("case_id"),
                    body.get("doc_ids"))
                return self._json(result)
            return self._json({"error": "not found"}, 404)
        except KeyError as e:
            return self._json({"error": str(e)}, 400)
        except IndexError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 - report to client, keep serving
            return self._json({"error": "server error: %s" % e}, 500)

    # ---------------- static ----------------
    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        safe = re.sub(r"^/+", "", path)
        full = os.path.normpath(os.path.join(WEB, safe))
        if not full.startswith(WEB) or not os.path.isfile(full):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):  # quiet
        pass


def main():
    library.reindex_all()  # 启动迁移：历史文档补建检索索引
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = "http://{}:{}".format(HOST, PORT)
    print("Consultation platform running at", url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
