"""LLM 客户端：OpenAI 兼容（API 为主）+ Ollama 本地兜底。

- API：任意 OpenAI 兼容端点（DeepSeek/GLM/Qwen/OpenAI）。
- Ollama：base_url 指向本地 Ollama，api_key 可留空，走同一兼容层。
"""
import re
import uuid
from dataclasses import dataclass

from ..config import get_settings
from ..shared import OLLAMA_DEFAULT_PORT

_THINK_RE = re.compile(r"<think>.*?</think>|<reasoning>.*?</reasoning>", re.S)


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = ""
    model: str = "glm-4.5-air"
    timeout: float = 120.0
    max_tokens: int = 1200
    temperature: float = 0.2

    @property
    def is_ollama(self) -> bool:
        return OLLAMA_DEFAULT_PORT in (self.base_url or "") or "ollama" in (self.base_url or "").lower()

    @property
    def configured(self) -> bool:
        return bool(self.model) and (bool(self.api_key) or self.is_ollama)


def server_defaults() -> LLMConfig:
    s = get_settings()
    return LLMConfig(
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_default_model,
        timeout=s.llm_timeout_seconds,
        max_tokens=s.llm_max_tokens,
    )


def role_config(role: str) -> LLMConfig:
    """按角色取默认模型（summarizer / moderator / specialist）。"""
    s = get_settings()
    model = {
        "summarizer": s.summarizer_model,
        "moderator": s.moderator_model,
        "specialist": s.specialist_model,
    }.get(role, s.llm_default_model)
    return LLMConfig(
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=model,
        timeout=s.llm_timeout_seconds,
        max_tokens=s.llm_max_tokens,
    )


async def chat(
    cfg: LLMConfig,
    system: str,
    user: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    """单轮对话，返回模型文本。思考段自动剥离。"""
    import openai

    kwargs: dict = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": cfg.temperature if temperature is None else temperature,
        "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
        "timeout": cfg.timeout,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    client = openai.AsyncOpenAI(
        api_key=cfg.api_key or "EMPTY",
        base_url=cfg.base_url or None,
        timeout=cfg.timeout,
        max_retries=1,
    )
    try:
        resp = await client.chat.completions.create(**kwargs)
    finally:
        await client.close()

    text = (resp.choices[0].message.content or "") if resp.choices else ""
    text = _THINK_RE.sub("", text).strip()
    if not text:
        raise RuntimeError(f"模型返回为空（model={cfg.model}）。请检查模型配置或调大 max_tokens。")
    return text


def trace_id() -> str:
    return uuid.uuid4().hex[:12]
