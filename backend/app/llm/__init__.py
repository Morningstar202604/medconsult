"""LLM 包：客户端 / 提示词分层 / 结构化校验。"""
from .client import LLMConfig, chat, role_config, server_defaults
from .prompts import (FOLLOWUP_SYSTEM, MODERATOR_SYSTEM, SPECIALIST_SYSTEM,
                      SUMMARIZER_SYSTEM, role_system, wrap_untrusted)
from .validate import ReportSchema, extract_json, report_with_retry, validate_report

__all__ = [
    "LLMConfig", "chat", "role_config", "server_defaults",
    "FOLLOWUP_SYSTEM", "MODERATOR_SYSTEM", "SPECIALIST_SYSTEM", "SUMMARIZER_SYSTEM",
    "role_system", "wrap_untrusted",
    "ReportSchema", "extract_json", "report_with_retry", "validate_report",
]
