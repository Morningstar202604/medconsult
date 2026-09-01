"""临床工具统一协议（垂直临床 agent 工具层差异化核心）。

所有临床工具调用都走这里：输入校验 → 执行 → 结构化输出（含置信度/限制）→ 审计落库。
让"AI 用了什么工具、输入输出是什么、可信度如何"全程可查——这是临床合规的命根子，
也是与"用完即弃的通用插件"的本质区别。

接入约定：
- run_* 系列返回 (result_dict, confidence, limitation)。
- log_tool 把每次调用写入 tool_call_logs。
"""
from __future__ import annotations
import json
import os
from sqlalchemy.orm import Session
from .. import models


def log_tool(db: Session, consultation_id: int | None, tool_name: str,
             input_: dict, output: dict, confidence: str = "中",
             note: str = "") -> None:
    db.add(models.ToolCallLog(
        consultation_id=consultation_id,
        tool_name=tool_name,
        input_json=json.dumps(input_, ensure_ascii=False)[:4000],
        output_json=json.dumps(output, ensure_ascii=False)[:4000],
        confidence=confidence,
        note=note[:1000],
    ))


def _sanitize(text: str, max_len: int = 4000) -> str:
    return (text or "")[:max_len]


# ---------------------------------------------------------------- 红旗
def run_triage(db: Session, consultation_id: int | None, text: str) -> dict:
    from ..clinical.triage import scan, banner_text, worst_severity
    hits = scan(text)
    result = {
        "count": len(hits),
        "worst": worst_severity(hits),
        "banner": banner_text(hits),
        "items": [{"severity": h.severity, "message": h.message, "matched": h.matched}
                  for h in hits],
    }
    log_tool(db, consultation_id, "triage", {"text": _sanitize(text, 1000)},
             result, confidence="高", note="确定性规则库，按危急程度分级")
    return result


# ---------------------------------------------------------------- 计算器
def run_calculator(db: Session, consultation_id: int | None, text: str) -> dict:
    from ..clinical import detect_and_run
    calcs = detect_and_run(text)
    result = {
        "count": len(calcs),
        "items": [{"name": c.name, "expr": c.expr, "result": c.result, "note": c.note}
                  for c in calcs],
    }
    log_tool(db, consultation_id, "calculator", {"text": _sanitize(text, 1000)},
             result, confidence="中", note="单位感知计算；结果未经人工复核")
    return result


# ---------------------------------------------------------------- RAG 循证检索
def run_evidence_search(db: Session, consultation_id: int | None, query: str,
                        k: int = 5) -> dict:
    """循证检索：优先走内部 RAG（指南/资料库）；真实外部循证源接 provider 接口。"""
    from ..rag import search as rag_search
    from ..config import get_settings
    settings = get_settings()
    source = "内部资料库(RAG)"
    chunks: list[dict] = []
    try:
        chunks = rag_search(query, k=k)
    except Exception as e:
        chunks = []
    result = {
        "provider": settings.evidence_provider or "internal_rag",
        "source": source,
        "count": len(chunks),
        "items": [{"doc": c["doc"], "text": c["text"], "score": c.get("score", 0)}
                  for c in chunks],
    }
    log_tool(db, consultation_id, "evidence_search", {"query": _sanitize(query, 500)},
             result, confidence="中",
             note=f"内部RAG检索，阈值过滤；外部源({settings.evidence_provider or '未配置'})待接入")
    return result


# ---------------------------------------------------------------- 检查合理性
def run_exam_check(db: Session, consultation_id: int | None, text: str) -> dict:
    from ..clinical.exam_appropriateness import suggest_exams, summary_text
    suggestions = suggest_exams(text)
    result = {
        "count": len(suggestions),
        "summary": summary_text(suggestions),
        "items": suggestions,
    }
    log_tool(db, consultation_id, "exam_appropriateness", {"text": _sanitize(text, 1000)},
             result, confidence="中", note="确定性规则，参考通用诊疗指南；不适用情形已标注")
    return result


# ---------------------------------------------------------------- 药物相互作用
def run_drug_check(db: Session, consultation_id: int | None, meds_text: str) -> dict:
    from ..clinical.drug_interactions import check_interactions, summary_text
    hits = check_interactions(meds_text)
    result = {
        "count": len(hits),
        "summary": summary_text(hits),
        "items": hits,
    }
    log_tool(db, consultation_id, "drug_interaction", {"meds": _sanitize(meds_text, 1000)},
             result, confidence="中",
             note="内置常见相互作用规则库；全面评估需接权威药品库")
    return result


# ---------------------------------------------------------------- OCR（图片文字识别）
def run_ocr(db: Session, consultation_id: int | None, image_path: str,
            filename: str = "") -> dict:
    """OCR 识别检查报告/处方/化验单图片文字。结果走工具审计，可注入证据链。"""
    from .media import ocr_image
    result = ocr_image(image_path, filename)
    log_tool(db, consultation_id, "ocr",
             {"image": filename or os.path.basename(image_path),
              "size": _safe_size(image_path)},
             result, confidence=result.get("confidence", "中"),
             note=f"引擎={result.get('engine')}；OCR 结果需人工核对数值与单位")
    return result


# ---------------------------------------------------------------- ASR（语音转文字）
def run_asr(db: Session, consultation_id: int | None, audio_path: str,
            filename: str = "") -> dict:
    """ASR 转写口述问诊/录音会诊。结果走工具审计，可作为问诊回答或会诊输入。"""
    from .media import asr_audio
    result = asr_audio(audio_path, filename)
    log_tool(db, consultation_id, "asr",
             {"audio": filename or os.path.basename(audio_path),
              "duration": result.get("duration", 0)},
             result, confidence=result.get("confidence", "中"),
             note=f"引擎={result.get('engine')}；转写结果需人工核对医学术语")
    return result


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0
