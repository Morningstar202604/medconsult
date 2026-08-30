"""ZCode 临时引擎桥（me_engine）。

让 ZCode 会话中的大模型直接充当 MedConsult 的临时 LLM 引擎，无需任何外部 API：
平台（OpenAI 兼容客户端）把对话请求 POST 进来，本进程将其落盘为待答请求，
由 ZCode 智能体读取后把答案写回，本进程再以 OpenAI 流式格式返回给平台。

仅在 ZCode 会话活跃期间有真实回答；智能体未应答时，等待 ENGINE_WAIT_SECONDS
后返回占位回复（平台可正常降级，不会挂起）。

用法:  python me_engine/me_engine.py   # 监听 127.0.0.1:8790
"""
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(BASE, "pending")
ANSWERS = os.path.join(BASE, "answers")
HOST = os.environ.get("ME_ENGINE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ME_ENGINE_PORT", "8790"))
ENGINE_WAIT_SECONDS = float(os.environ.get("ME_ENGINE_WAIT", "45"))
OFFLINE_REPLY = "（ZCode 临时引擎暂时离线：回到 ZCode 会话说一声即可继续；正式使用请在 config.json 填入 GLM Key）"


def _setup():
    for d in (PENDING, ANSWERS):
        os.makedirs(d, exist_ok=True)
        for fn in os.listdir(d):  # 清理上次残留
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass


def _messages_text(messages):
    out = []
    for m in messages or []:
        out.append("[{}] {}".format(m.get("role"), m.get("content")))
    return "\n\n".join(out)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply_offline(self, req_id, model):
        return {"id": req_id, "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": OFFLINE_REPLY}}]}

    def _sse(self, req_id, model, content):
        """以 OpenAI 流式（SSE）格式返回。"""

        def chunk(delta, finish=None):
            return "data: " + json.dumps({
                "id": req_id, "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }, ensure_ascii=False) + "\n\n"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(chunk({"role": "assistant"}).encode("utf-8"))
        # 分几段发出，模拟流式
        step = max(1, len(content) // 3)
        for i in range(0, len(content), step):
            self.wfile.write(chunk({"content": content[i:i + step]}).encode("utf-8"))
        self.wfile.write(chunk({}, "stop").encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": True, "engine": "zcode-temp"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, UnicodeDecodeError):
            payload = {}
        req_id = "me_" + uuid.uuid4().hex[:12]
        model = payload.get("model") or "zcode"
        messages = payload.get("messages") or []

        # 落盘待答（先写临时文件再原子改名，避免读到半截）
        req = {"id": req_id, "ts": time.time(), "model": model,
               "prompt": _messages_text(messages),
               "max_tokens": payload.get("max_tokens"), "temperature": payload.get("temperature")}
        tmp = os.path.join(PENDING, req_id + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(req, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(PENDING, req_id + ".json"))

        # 等智能体作答
        answer_path = os.path.join(ANSWERS, "resp_" + req_id + ".json")
        deadline = time.time() + ENGINE_WAIT_SECONDS
        content = None
        while time.time() < deadline:
            if os.path.exists(answer_path):
                try:
                    with open(answer_path, "r", encoding="utf-8") as f:
                        content = (json.load(f).get("content") or "").strip()
                except Exception:
                    content = None
                for p in (answer_path, os.path.join(PENDING, req_id + ".json")):
                    try:  # 应答消费后同步清理待答文件，避免残留误导
                        os.remove(p)
                    except OSError:
                        pass
                break
            time.sleep(0.3)

        if content is None:  # 引擎临时离线：优雅占位，平台可降级
            body = json.dumps(self._reply_offline(req_id, model), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            self._sse(req_id, model, content)
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def log_message(self, fmt, *args):  # quiet
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"


def main():
    _setup()
    print("ZCode temp engine on http://{}:{}  (wait {}s per request)".format(
        HOST, PORT, ENGINE_WAIT_SECONDS), flush=True)
    try:
        Server((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
