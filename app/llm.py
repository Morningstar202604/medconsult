"""OpenAI-compatible LLM bridge (openai 0.28 style) with custom base_url.

Lets the platform talk to OpenAI, DeepSeek, GLM, Qwen, Ollama or any
OpenAI-compatible endpoint. Uses streaming internally: some relays (new-api
渠道) hang on non-streamed completions, and streaming works everywhere.
The API key lives only for the duration of one request and is never logged.
"""
import re
import threading

_lock = threading.Lock()

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def chat(model, system_prompt, user_prompt, api_key, base_url=None,
         timeout=120, max_tokens=400, temperature=0.05):
    """Single-turn chat completion, streamed internally. Returns the text."""
    import openai  # 0.28.x

    with _lock:  # 0.28 config is module-global; serialize calls
        old_key, old_base = openai.api_key, getattr(openai, "api_base", None)
        try:
            openai.api_key = api_key
            if base_url:
                openai.api_base = base_url if base_url.endswith("/v1") or "/v1" in base_url else base_url + "/v1"
            stream = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                request_timeout=timeout,
            )
            pieces = []
            for chunk in stream:
                choices = chunk.get("choices") or [{}]
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    pieces.append(piece)
            text = "".join(pieces)
            # 思考型模型（Qwen3/DeepSeek-R1 等）会把推理过程放在 <think> 段，剥离
            text = _THINK_RE.sub("", text)
            # 兜底：若有 </think> 但没剥干净，只保留其后内容
            if "</think>" in text:
                text = text.split("</think>")[-1]
            return (text or "(模型返回为空)").strip()
        finally:
            openai.api_key = old_key
            openai.api_base = old_base
