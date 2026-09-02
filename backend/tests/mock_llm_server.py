"""本地 OpenAI 兼容 mock 服务：用于验证生产模式多智能体链路真实调用。

行为：
- 根据 system prompt 识别角色（摘要/专科/主持人）；
- 主持人返回合法 ReportSchema JSON；专科/摘要返回文本；
- 记录每次调用（role, model）供断言，验证"多智能体"是真实并发调用而非单模型换皮。
"""
import json

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
CALLS: list[dict] = []


class Msg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    model: str = ""
    messages: list[Msg] = []
    temperature: float = 0.2
    max_tokens: int = 1000
    timeout: float = 30.0
    response_format: dict | None = None


@app.post("/v1/chat/completions")
async def chat(req: ChatReq):
    system = next((m.content for m in req.messages if m.role == "system"), "")
    user = next((m.content for m in req.messages if m.role == "user"), "")
    CALLS.append({"model": req.model, "system": system, "user": user})

    # 主持人 → 合法 JSON 报告
    if "会诊主持人，负责汇总共识报告" in system or "会诊共识报告" in user:
        content = json.dumps({
            "final_diagnosis": "社区获得性肺炎（CAP）",
            "confidence": "中",
            "recommended_dept": "呼吸内科",
            "key_findings": ["发热咳嗽 3 天", "影像学提示肺部感染灶"],
            "plan": ["完善血常规/CRP", "按指南经验性抗感染并评估疗效"],
            "red_flags": [],
            "disagreements": "专科意见一致，无明显分歧",
            "warnings": "由链路验证用测试模型生成，非真实临床判断",
        }, ensure_ascii=False)
    # 摘要（精确匹配 SUMMARIZER_SYSTEM 特征，避免与 SAFETY_LAYER 中的"病历摘要"混淆）
    elif "会诊主持人助理" in system:
        content = "男，45 岁，发热咳嗽 3 天，既往体健；生命体征与辅助检查待补充。"
    # 专科
    else:
        # 提取专科名（形如"你是会诊中的{spec}"）
        spec = "专科"
        marker = "你是会诊中的"
        if marker in system:
            spec = system.split(marker)[1].split("，")[0].strip("{} ")
        content = (
            f"（{spec}）考虑社区获得性肺炎可能性大；建议完善血常规、CRP 与胸部影像，"
            "评估氧合；当前资料不足以完全排除其他病原体，需动态复查。"
        )
    return {
        "id": "mock", "object": "chat.completion", "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
    }
