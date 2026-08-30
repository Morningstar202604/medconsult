"""OpenAI 兼容 LLM 桥（openai>=1.x SDK）。

支持 OpenAI、DeepSeek、GLM、Qwen、Ollama 等任何 OpenAI 兼容端点。
base_url 按端点原样使用：只有裸域名（无路径）时才补 /v1，
避免把 https://open.bigmodel.cn/api/paas/v4 这类自带版本路径的
端点错误改写成 .../v4/v1（旧版本的缺陷）。
API key 仅在单次请求内存中出现，不写日志。
"""
import re
import threading

import openai

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_url_lock = threading.Lock()  # openai<1.x 全局态兜底（安装了 0.x 时）
_CLIENTS = {}


def _normalize_base(base_url):
    """裸域名补 /v1；已带路径（如 .../v1、.../api/paas/v4）原样保留。"""
    u = (base_url or "").strip().rstrip("/")
    if not u:
        return None
    if "://" not in u:
        u = "https://" + u
    from urllib.parse import urlparse
    path = urlparse(u).path.strip("/")
    return u if path else u + "/v1"


def _client(api_key, base_url):
    key = (api_key or "").strip() or "EMPTY"  # Ollama 等本地端点不校验 key
    url = _normalize_base(base_url)
    ck = (key, url)
    with _url_lock:
        cli = _CLIENTS.get(ck)
        if cli is None:
            cli = openai.OpenAI(api_key=key, base_url=url,
                                timeout=120, max_retries=1)
            _CLIENTS[ck] = cli
        return cli


def chat(model, system_prompt, user_prompt, api_key, base_url=None,
         timeout=120, max_tokens=400, temperature=0.05):
    """单轮对话（内部流式）。返回模型文本。"""
    cli = _client(api_key, base_url)
    stream = cli.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        timeout=timeout,
    )
    pieces = []
    for chunk in stream:
        choices = chunk.choices or []
        if not choices:
            continue
        piece = choices[0].delta and choices[0].delta.content
        if piece:
            pieces.append(piece)
    text = "".join(pieces)
    # 思考型模型（Qwen3/GLM-Z/DeepSeek-R1 等）把推理放在 <think> 段，剥离
    text = _THINK_RE.sub("", text)
    if "</think>" in text:
        text = text.split("</think>")[-1]
    text = (text or "").strip()
    if not text:
        raise RuntimeError("模型返回为空（可能是 max_tokens 太小或端点不兼容）")
    return text
