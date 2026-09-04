"""临床工具路由：CURB-65、药物相互作用、完备度评分等独立工具。

这些是确定性临床规则工具，不依赖LLM，直接返回结构化结果。
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..clinical.calculators import _calc_curb65, CalcResult
from ..clinical.completeness import assess as completeness_assess
from ..clinical.drug_interactions import check_interactions, summary_text
from ..services import toolbox as tb_service
from ..deps import DbDep, CurrentUser

router = APIRouter(tags=["clinical-tools"])


# ---------------------------------------------------------------- 请求模型
class Curb65Request(BaseModel):
    confusion: bool = False
    urea_mmol: float = 0.0
    resp_rate: int = 0
    sys_bp: int = 0
    dia_bp: int = 0
    age: int = 0


class DrugInteractionRequest(BaseModel):
    drugs: list[str] = Field(..., min_length=1)
    context: str = ""


class CompletenessRequest(BaseModel):
    chief_complaint: str = ""
    history: str = ""
    meds: str = ""
    exams: str = ""
    vitals: str = ""
    allergies: str = ""


class CalculatorRequest(BaseModel):
    """统一计算器请求：从自由文本提取数值计算。"""
    text: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------- CURB-65
@router.post("/tools/curb65")
def calc_curb65(body: Curb65Request, db: DbDep, user: CurrentUser):
    """CURB-65 肺炎严重度评分。"""
    text_parts = []
    if body.confusion:
        text_parts.append("意识模糊")
    if body.urea_mmol > 7:
        text_parts.append(f"尿素氮 {body.urea_mmol} mmol/L")
    if body.resp_rate >= 30:
        text_parts.append(f"呼吸 {body.resp_rate} 次/分")
    if body.sys_bp < 90:
        text_parts.append(f"收缩压 {body.sys_bp}")
    if body.dia_bp <= 60:
        text_parts.append(f"舒张压 {body.dia_bp}")
    if body.age >= 65:
        text_parts.append(f"{body.age} 岁")

    fake_text = "社区获得性肺炎 " + " ".join(text_parts)
    results = _calc_curb65(fake_text)
    if not results:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法计算CURB-65评分")

    r = results[0]
    score_str = r.result  # "X 分（建议...）"
    score = int(score_str.split(" ")[0]) if score_str else 0

    advice_map = {
        0: "倾向门诊/密切随访",
        1: "倾向门诊/密切随访",
        2: "住院或密切随访",
        3: "建议住院",
        4: "建议住院/ICU评估",
        5: "建议住院/ICU评估",
    }
    return {
        "score": score,
        "risk_level": "低危" if score <= 1 else "中危" if score == 2 else "高危",
        "advice": advice_map.get(score, "建议住院"),
        "items": r.expr.split("；") if r.expr else [],
        "unverified": True,
        "note": "从输入参数自动计算，未经检验科核实",
    }


# ---------------------------------------------------------------- 药物相互作用
@router.post("/tools/drug-interaction")
def check_drug_interaction(body: DrugInteractionRequest, db: DbDep, user: CurrentUser):
    """药物相互作用检查。"""
    drugs_text = " ".join(body.drugs)
    if body.context:
        drugs_text += f" {body.context}"

    hits = check_interactions(drugs_text)
    result = {
        "count": len(hits),
        "summary": summary_text(hits),
        "items": hits,
        "unverified": True,
        "note": "内置常见相互作用规则库；全面评估需接权威药品库",
    }
    return result


# ---------------------------------------------------------------- 完备度评分
@router.post("/tools/completeness")
def calc_completeness(body: CompletenessRequest, db: DbDep, user: CurrentUser):
    """病历完备度评分。"""
    # 合并所有文本供完备度分析
    combined = f"主诉：{body.chief_complaint}。现病史：{body.history}。用药：{body.meds}。检查：{body.exams}。生命体征：{body.vitals}。过敏史：{body.allergies}。"
    result = completeness_assess(combined)
    return {
        "score": result["score"],
        "total": result["total"],
        "missing": result.get("missing", []),
        "unverified": True,
        "note": "基于确定性规则评估，不替代临床判断",
    }


# ---------------------------------------------------------------- 通用计算器
@router.post("/tools/calculator")
def run_calculator(body: CalculatorRequest, db: DbDep, user: CurrentUser):
    """从自由文本提取并执行所有可用的医学计算器。"""
    calcs = tb_service.run_calculator(db, None, body.text)
    return {
        "count": calcs["count"],
        "items": calcs["items"],
        "unverified": True,
        "note": "单位感知计算；结果未经人工复核",
    }


# ---------------------------------------------------------------- 红旗分诊
@router.post("/tools/triage")
def run_triage(body: CalculatorRequest, db: DbDep, user: CurrentUser):
    """危急征象红旗扫描。"""
    res = tb_service.run_triage(db, None, body.text)
    return {
        "count": res["count"],
        "worst": res["worst"],
        "banner": res["banner"],
        "items": res["items"],
        "unverified": True,
        "note": "确定性规则库，按危急程度分级",
    }


# ---------------------------------------------------------------- 检查合理性
@router.post("/tools/exam-appropriateness")
def run_exam_check(body: CalculatorRequest, db: DbDep, user: CurrentUser):
    """检查合理性建议。"""
    res = tb_service.run_exam_check(db, None, body.text)
    return {
        "count": res["count"],
        "summary": res["summary"],
        "items": res["items"],
        "unverified": True,
        "note": "确定性规则，参考通用诊疗指南；不适用情形已标注",
    }
