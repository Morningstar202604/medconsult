"""Consultation platform web server (Python stdlib only, no extra deps).

Run:  .venv/Scripts/python server.py  ->  http://127.0.0.1:8765
可用环境变量覆盖监听地址：MEDCONSULT_HOST / MEDCONSULT_PORT。
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
HOST = os.environ.get("MEDCONSULT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MEDCONSULT_PORT", "8765"))
MAX_BODY = 64 * 1024 * 1024  # 上传/请求体上限 64MB，防御误传超大文件

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
        if n > MAX_BODY:
            raise ValueError("请求体过大（>64MB）")
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
            c = app_config.load()
            # 未配 Key 时也回传 base_url/model 作为预填建议（用户只需粘贴 Key）
            return self._json({
                "has_key": bool(d),
                "base_url": d.get("base_url") or c.get("base_url") or "",
                "model": d.get("model") or c.get("model") or "",
                "hospital": app_config.hospital_name(),
            })
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
        if path == "/api/skills":  # 会诊技能包
            from app import skills as skills_mod
            return self._json({"skills": skills_mod.list_skills()})
        if path == "/api/reference":  # 检验参考值对照库
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            from app import reference as ref_mod
            return self._json({"items": ref_mod.search(unquote(qs.get("q", [""])[0]))})
        if path == "/api/feedback":  # 本院经验库（医生反馈）
            from app import feedback as fb_mod
            return self._json({"items": fb_mod.list_()})
        return self._static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/library/upload":  # 原始字节上传：必须在解析 JSON body 之前处理
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            name = unquote(qs.get("name", ["未命名.txt"])[0])
            ext = os.path.splitext(name)[1].lower()
            if ext not in library.ALLOWED_EXTS:
                return self._json({"error": "不支持的文件类型 {}（允许：txt/md/pdf/docx/json/csv/log/htm/html/xml）".format(ext or "(无扩展名)")}, 400)
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
                d = app_config.llm_defaults()
                key = (s.get("api_key") or "").strip() or d.get("api_key")
                if not key:
                    return self._json({"ok": False, "error": "未配置 API Key（可在设置中填写，或服务端 config.json 提供）"})
                model = ((s.get("doctor_model") or s.get("model") or "").strip()
                         or d.get("model") or "gpt-4o-mini")
                base = (s.get("base_url") or "").strip() or d.get("base_url")
                try:
                    reply = engine.llm.chat(
                        model, "You are a connectivity test.", "Reply with exactly: OK",
                        key, base or None,
                        max_tokens=10, temperature=0)
                    return self._json({"ok": True, "reply": reply, "model": model})
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
            if path == "/api/mdt/followup":  # 报告追问：医生就报告向主持人 Agent 追问
                result = mdt.followup(body.get("text"), body.get("report"),
                                      body.get("tail"), body.get("settings"))
                return self._json(result)
            if path == "/api/skills/save":
                from app import skills as skills_mod
                sk = skills_mod.save(body.get("name"), body.get("desc"),
                                     body.get("prompt"), body.get("id"))
                return self._json({"ok": bool(sk), "id": sk["id"] if sk else None})
            if path == "/api/skills/delete":
                from app import skills as skills_mod
                return self._json({"ok": skills_mod.delete(body.get("id"))})
            if path == "/api/feedback/save":  # 医生反馈 → 本院经验库（长期学习）
                from app import feedback as fb_mod
                e = fb_mod.save(body.get("title"), body.get("diagnosis"),
                                body.get("helpful"), body.get("note"), body.get("visit"))
                return self._json({"ok": bool(e)})
            if path == "/api/reference/save":
                from app import reference as ref_mod
                e = ref_mod.save_entry(body)
                return self._json({"ok": bool(e)})
            if path == "/api/reference/delete":
                from app import reference as ref_mod
                return self._json({"ok": ref_mod.delete_entry(body.get("item"))})
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
        # 防目录穿越：必须在 web/ 目录内（补分隔符，避免误匹配 web-xyz 同级目录）
        if not (full == WEB or full.startswith(WEB + os.sep)) or not os.path.isfile(full):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):  # quiet
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 的 SO_REUSEADDR 允许双绑定同一端口：两个实例静默并存、请求随机分流。
    # 在 Windows 上禁用，保证端口互斥、重启必然可见。
    allow_reuse_address = os.name != "nt"


def main():
    library.reindex_all()  # 启动迁移：历史文档补建检索索引
    from app import skills as skills_mod
    skills_mod.seed_if_empty()  # 首次运行播种会诊技能包
    server = Server((HOST, PORT), Handler)
    url = "http://{}:{}".format(HOST, PORT)
    print("Consultation platform running at", url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
