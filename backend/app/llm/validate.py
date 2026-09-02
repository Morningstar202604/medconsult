"""结构化输出校验：MDT 报告必须通过 Pydantic 校验，失败即显式报错，不静默降级。"""
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class ReportSchema(BaseModel):
    final_diagnosis: str = Field(min_length=1, max_length=300)
    confidence: Literal["高", "中", "低"] = "中"
    recommended_dept: str = Field(default="", max_length=100)
    key_findings: list[str] = Field(default_factory=list, max_length=10)
    plan: list[str] = Field(default_factory=list, max_length=12)
    red_flags: list[str] = Field(default_factory=list, max_length=10)
    disagreements: str = Field(default="", max_length=500)
    warnings: str = Field(default="", max_length=500)

    @field_validator("key_findings", "plan", "red_flags")
    @classmethod
    def _clean_str_list(cls, v):
        return [str(x).strip() for x in v if str(x).strip()][:10]


def extract_json(text: str) -> dict | None:
    """从模型输出中稳健提取单个 JSON 对象（处理代码块/多余文字）。"""
    if not text:
        return None
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    # 尝试整段解析；失败则贪婪取第一个 { 到最后一个 }
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def validate_report(data: dict) -> ReportSchema | None:
    try:
        return ReportSchema.model_validate(data)
    except Exception:
        return None


async def report_with_retry(gen_fn, max_retries: int = 2) -> ReportSchema:
    """gen_fn() 返回模型原始文本；解析失败自动带错误反馈重试一次。"""
    last_raw = ""
    for attempt in range(max_retries):
        raw = await gen_fn(error_feedback=last_raw if attempt > 0 else "")
        last_raw = raw
        data = extract_json(raw)
        if data is not None:
            validated = validate_report(data)
            if validated is not None:
                return validated
    raise RuntimeError("主持人报告未通过结构校验，本次会诊报告生成失败（不静默降级）。")
