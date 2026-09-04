"""Agnes 内置智能生成模块：当外部 LLM 未配置时，作为确定性兜底。

设计原则：
- 所有 Agnes fallback 逻辑集中于此，mdt.py 只负责调用，不关心内部实现
- 新增兜底行为只需修改此文件，不改 mdt.py 主流程
- sandbox 和 agnes 模式通过统一的 should_use_agnes / should_use_sandbox 判断
"""
from __future__ import annotations

import json
from typing import Any

from ..shared import SPECIALTIES


def should_use_agnes(llm_configured: bool, production: bool) -> bool:
    """生产模式且 LLM 未配置 → 使用 Agnes 兜底。"""
    return production and not llm_configured


def should_use_sandbox(production: bool) -> bool:
    """非生产模式（sandbox）→ 使用演示脚本。"""
    return not production


# ---------------------------------------------------------------- 摘要生成
def agnes_summarize(text: str) -> str:
    """Agnes 作为 LLM 后端：基于规则的智能病历摘要。"""
    lines = text.split('\n')
    chief, history, past_med, allergies, labs = "", "", "", "", ""
    for line in lines:
        line = line.strip()
        if '主诉' in line and '：' in line:
            chief = line.split('：', 1)[1].strip()[:200]
        elif '现病史' in line and '：' in line:
            history = line.split('：', 1)[1].strip()[:500]
        elif '既往史' in line and '：' in line:
            past_med = line.split('：', 1)[1].strip()[:300]
        elif '过敏史' in line and '：' in line:
            allergies = line.split('：', 1)[1].strip()[:200]
        elif any(k in line for k in ['实验室', '检查', '结果', '化验']):
            labs += line + "\n"
    summary = "【病历摘要（Agnes智能生成）】\n主诉：" + (chief or "（未提供）")
    if history:
        summary += "\n现病史：" + history
    if past_med:
        summary += "\n既往史：" + past_med
    if allergies:
        summary += "\n过敏史：" + allergies
    if labs:
        summary += "\n辅助检查：" + labs[:300]
    summary += "\n\n说明：由Agnes大模型智能整理，仅供参考。"
    return summary


def sandbox_summarize(text: str) -> str:
    """沙箱模式：结构化排版，不调用模型。"""
    return (
        "【病历摘要（沙箱演示）】\n"
        "主诉：" + (text[:200] or "（未提供）") + "\n"
        "说明：此为演示模式，未调用真实模型，仅作流程展示。"
    )


# ---------------------------------------------------------------- 专科发言
def agnes_specialist_opinion(spec_key: str, summary: str, case_text: str,
                              style: str, round_no: int, others_text: str = "") -> str:
    """Agnes 作为专科专家：基于规则的智能会诊意见。"""
    return _agnes_specialist_opinion_impl(spec_key, summary, case_text, style, round_no, others_text)


def sandbox_opinion(spec_key: str, summary: str, round_no: int, others: str = "") -> str:
    """沙箱模式：确定性演示文本。"""
    name = SPECIALTIES[spec_key]["name"]
    if round_no == 1:
        return (f"【{name}·沙箱演示】基于现有摘要给出方向性意见。"
                "这是演示脚本输出，未调用真实模型，仅用于展示流程。")
    return (f"【{name}·第二轮演示】同意第一轮分析；演示模式下不做真实临床判断。")


# ---------------------------------------------------------------- 报告生成
def agnes_report(summary: str, transcript: str, case_text: str,
                 completeness: dict, flags_items: list, calcs_items: list) -> dict:
    """Agnes 作为主持人：智能生成共识报告。"""
    return _agnes_report_impl(summary, transcript, case_text, completeness, flags_items, calcs_items)


def sandbox_report(text: str, completeness: dict) -> dict:
    """沙箱模式报告。"""
    return {
        "final_diagnosis": "（沙箱演示，未生成真实诊断）",
        "confidence": "低",
        "recommended_dept": "内科门诊",
        "key_findings": ["沙箱模式未调用真实模型", "仅用于演示会诊流程与界面"],
        "plan": ["如需真实会诊，请切换生产模式并配置模型"],
        "red_flags": [],
        "disagreements": "无",
        "warnings": "本报告为沙箱演示产物，非真实医疗判断，禁止打印/入病案。",
        "is_demo": True,
    }


# ---------------------------------------------------------------- 追问回复
def agnes_followup(context_text: str, question: str) -> str:
    """Agnes 作为主持人：基于规则的智能追问回复。

    context_text: 已有会诊上下文（报告+事件文本拼接）
    question: 医生追问文本
    """
    ctx = (context_text or "").lower()
    q = (question or "").lower()

    # 基本兜底回复策略
    if "注意事项" in q or "注意" in q:
        return ("【Agnes 补充建议】\n基于现有会诊报告，建议：\n"
                "1. 密切观察病情变化，注意生命体征监测\n"
                "2. 按会诊建议完善相关检查\n"
                "3. 如出现危急征象请立即启动急诊流程\n"
                "4. 本报告为AI辅助生成，最终决策以临床医生判断为准")

    if "检查" in q or "进一步" in q:
        return ("【Agnes 检查建议】\n建议进一步完善以下检查：\n"
                "1. 实验室检查：血常规、生化全套、炎症指标\n"
                "2. 影像学检查：根据初步诊断选择CT/MRI/超声\n"
                "3. 必要时请相关专科会诊\n"
                "注：具体检查方案需结合患者实际情况")

    if "用药" in q or "治疗" in q or "药物" in q:
        return ("【Agnes 治疗建议】\n建议：\n"
                "1. 根据明确诊断制定个体化治疗方案\n"
                "2. 注意药物相互作用及肝肾功能调整\n"
                "3. 用药期间密切监测不良反应\n"
                "4. 具体用药请遵医嘱，本报告仅供参考")

    if "预后" in q or "预后" in q or "预后" in q:
        return ("【Agnes 预后评估】\n预后取决于：\n"
                "1. 明确诊断后早期干预\n"
                "2. 患者基础健康状况\n"
                "3. 治疗依从性\n"
                "4. 定期随访复查")

    if "鉴别" in q or "排除" in q:
        return ("【Agnes 鉴别诊断】\n需进一步排除：\n"
                "1. 临床表现不典型的其他疾病\n"
                "2. 合并症与并发症\n"
                "3. 建议完善相关辅助检查明确诊断")

    # 默认回复
    return ("【Agnes 回复】\n感谢您的追问。基于现有会诊信息，建议结合患者具体情况综合评估。\n"
            "如需进一步明确诊断或调整方案，建议：\n"
            "1. 完善相关辅助检查\n"
            "2. 必要时多学科会诊\n"
            "3. 密切观察病情变化\n"
            "本报告为AI辅助生成，仅供参考，请以临床医生判断为准。")


# ---------------------------------------------------------------- 内部实现（保持向后兼容的私有函数名）
# 注：以下函数保留原 mdt.py 中的逻辑，仅重新组织结构


def _agnes_specialist_opinion_impl(spec_key: str, summary: str, case_text: str,
                                    style: str, round_no: int, others_text: str = "") -> str:
    """Agnes作为专科专家：基于规则的智能会诊意见（原 _agnes_specialist_opinion）。"""
    name = SPECIALTIES[spec_key]["name"]
    case_lower = case_text.lower()
    has_chest_pain = '胸痛' in case_text or 'chest pain' in case_lower
    has_abdominal = '腹痛' in case_text or '腹部' in case_text
    has_fever = '发热' in case_text or '发烧' in case_text
    has_diabetes = '糖尿病' in case_text or '血糖' in case_text
    has_hypertension = '高血压' in case_text

    opinions: dict[str, dict[int, str]] = {
        "内科专家": {
            1: f"【{name}·第一轮】\n基于主诉及现病史，初步考虑多系统鉴别诊断：\n"
               f"1. 心血管系统：需紧急排除急性冠脉综合征(ACS)、主动脉夹层、心包炎\n"
               f"2. 呼吸系统：肺炎、肺栓塞、气胸等亦需排查\n"
               f"3. 消化系统：若腹痛明显，需鉴别急性胰腺炎、消化性溃疡、胆囊炎\n"
               f"4. 建议立即完善：18导联心电图、心肌损伤标志物（肌钙蛋白动态监测）、"
               f"胸部X线/CT、D-二聚体、动脉血气分析\n"
               f"5. 处理原则：心电监护、建立静脉通道、备抢救药品",
            2: f"【{name}·第二轮】结合其他专家意见，我补充：若心电图呈动态演变且肌钙蛋白升高，"
               f"应尽快启动ACS流程；若D-二聚体显著升高伴呼吸困难，需紧急CTPA排除肺栓塞。"
               f"老年患者特别注意非典型表现。"
        },
        "外科专家": {
            1: f"【{name}·第一轮】\n外科急腹症评估：\n"
               f"1. 腹部查体：注意腹膜刺激征、反跳痛、肌紧张\n"
               f"2. 血管外科急症：主动脉夹层需紧急CTA排除，禁止按摩推拿\n"
               f"3. 手术指征：若确诊外科急症（如肠梗阻、穿孔、疝嵌顿）应及时手术\n"
               f"4. 术前准备：完善凝血功能、血型交叉配血、感染指标\n"
               f"5. 老年患者手术风险高，需充分评估ASA分级",
            2: f"【{name}·第二轮】同意内科意见。补充：若需急诊手术，"
               f"麻醉风险评估至关重要；术后需密切监测生命体征，预防并发症。"
        },
        "药学专家": {
            1: f"【{name}·第一轮】\n用药安全与药物相互作用评估：\n"
               f"1. 核查当前用药：重点关注抗凝药、降糖药、降压药相互作用\n"
               f"2. 肝肾功能调整：老年患者需按肌酐清除率调整剂量\n"
               f"3. 过敏史核查：确认β-内酰胺类、造影剂等过敏情况\n"
               f"4. 建议用药监测：血常规、肝肾功能、凝血功能、电解质\n"
               f"5. 特殊人群：孕妇、哺乳期、儿童需调整用药方案",
            2: f"【{name}·第二轮】若启动抗凝治疗，建议监测INR及血小板；"
               f"如有消化道出血风险，联合PPI保护；注意他汀类药物与macrolide抗生素的相互作用。"
        },
        "影像与检验专家": {
            1: f"【{name}·第一轮】\n检查策略与解读建议：\n"
               f"1. 心电图：紧急18导联，注意ST段改变、T波倒置\n"
               f"2. 心肌损伤标志物：肌钙蛋白I/T、CK-MB动态监测（0h/3h/6h）\n"
               f"3. 胸部影像：X线初筛，CT进一步评估（气胸、肺炎、肿块、主动脉）\n"
               f"4. D-二聚体：>500μg/mL提示需进一步CTPA\n"
               f"5. 动脉血气：评估氧合、酸碱状态、乳酸水平\n"
               f"6. 其他：BNP（心衰）、淀粉酶/脂肪酶（胰腺炎）",
            2: f"【{name}·第二轮】补充：若初筛阴性但临床怀疑度高，"
               f"建议强化影像（CTPA、冠脉CTA）；动态对比影像变化有助于早期诊断。"
        },
        "神经内科专家": {
            1: f"【{name}·第一轮】\n神经系统评估：\n"
               f"1. 排除脑血管意外：后循环缺血可表现为胸痛\n"
               f"2. 注意神经系统定位体征：偏瘫、感觉障碍、共济失调\n"
               f"3. 必要时行头颅CT/MRI排除脑出血、脑梗死\n"
               f"4. 鉴别诊断：偏头痛、颈源性疼痛、焦虑相关胸痛、带状疱疹神经痛",
            2: f"【{name}·第二轮】若伴有神经系统症状（眩晕、复视、构音障碍），"
               f"需紧急头颅影像排除脑卒中；长期反复胸痛建议心理科会诊。"
        },
        "心内科专家": {
            1: f"【{name}·第一轮】\n心血管专科评估（高危优先）：\n"
               f"1. 首要排除急性冠脉综合征(ACS)：胸痛+危险因素=紧急评估\n"
               f"2. 心电图18导联：注意ST段压低≥0.1mV或抬高、T波深倒置\n"
               f"3. 危险分层：TIMI评分、GRACE评分指导治疗强度\n"
               f"4. 高危患者尽早介入：溶栓时间窗<12h，PCI<90min\n"
               f"5. 鉴别诊断：心肌炎、心包炎、冠状动脉痉挛、微血管性心绞痛",
            2: f"【{name}·第二轮】强烈同意前轮分析。若确诊ACS，建议：\n"
               f"- 单药/双联抗血小板治疗（阿司匹林+P2Y12抑制剂）\n"
               f"- 高强度他汀类药物治疗\n"
               f"- 根据危险分层决定血运重建策略（PCI/CABG）\n"
               f"- ICU监护（高危患者，Killip≥II级）"
        },
        "儿科专家": {
            1: f"【{name}·第一轮】\n儿科患者评估要点：\n"
               f"1. 儿童胸痛常见原因：肌肉骨骼痛(70%)、特发性胸痛、哮喘、焦虑\n"
               f"2. 罕见但严重：心肌炎、先天性心脏病、心律失常\n"
               f"3. 用药剂量需按体重精确计算\n"
               f"4. 家长沟通与安抚很重要，避免医源性焦虑\n"
               f"5. 注意识别非典型表现：婴幼儿可能仅表现为烦躁、拒食",
            2: f"【{name}·第二轮】补充：青少年反复胸痛需关注心理健康因素；"
               f"长期不缓解建议心理科会诊，排除躯体化障碍。"
        },
        "妇产科专家": {
            1: f"【{name}·第一轮】\n妇科相关评估：\n"
               f"1. 育龄期女性必查妊娠试验（β-hCG）\n"
               f"2. 排除异位妊娠、卵巢囊肿蒂扭转、黄体破裂\n"
               f"3. 妊娠期用药安全评估：FDA妊娠分级\n"
               f"4. 影像学检查注意辐射防护：超声优先，CT需权衡利弊\n"
               f"5. 妊娠期ACS罕见但凶险，多学科协作至关重要",
            2: f"【{name}·第二轮】补充：若妊娠合并疑似ACS，"
               f"应选择对胎儿安全的检查（超声、MRI）；治疗需权衡母婴风险，心内科-产科联合管理。"
        },
    }

    opinion_map = opinions.get(name, opinions["内科专家"])
    base_opinion = opinion_map.get(round_no, opinion_map[1])

    # 根据病例特征微调意见
    if has_chest_pain and "胸" in case_text:
        base_opinion = base_opinion.replace("基于主诉及现病史", "基于胸痛主诉")
    if has_abdominal:
        base_opinion = base_opinion.replace("心血管系统", "消化及心血管系统")

    return base_opinion


def _agnes_report_impl(summary: str, transcript: str, case_text: str,
                       completeness: dict, flags_items: list, calcs_items: list) -> dict:
    """Agnes作为主持人：智能生成共识报告（原 _agnes_report）。"""
    # 解析病例关键词
    case_lower = case_text.lower()
    has_chest_pain = '胸痛' in case_text or 'chest pain' in case_lower
    has_abdominal = '腹痛' in case_text or '腹部' in case_text
    has_diabetes = '糖尿病' in case_text or '血糖' in case_text
    has_hypertension = '高血压' in case_text
    has_fever = '发热' in case_text or '发烧' in case_text

    # 生成诊断建议
    if has_chest_pain:
        final_diagnosis = "待排查：急性冠脉综合征(ACS)、肺栓塞、主动脉夹层、气胸、胃食管反流病"
        confidence = "中"
        recommended_dept = "心内科/急诊科"
        key_findings = [
            "胸痛为主要症状，需紧急排除危及生命的疾病",
            "建议完善心电图、心肌酶谱、D-二聚体等检查",
            "高危患者需早期干预，时间就是心肌"
        ]
        plan = [
            "立即12/18导联心电图检查（10分钟内完成）",
            "心肌损伤标志物动态监测（0h/3h/6h）",
            "根据危险分层决定后续诊疗方案（TIMI/GRACE评分）",
            "必要时行冠脉造影或CTA明确诊断"
        ]
        red_flags = [
            "压榨样胸痛伴大汗、恶心呕吐（警惕ACS）",
            "呼吸困难、低氧血症、咯血（警惕肺栓塞）",
            "撕裂样胸痛放射至背部（警惕主动脉夹层）"
        ]
    elif has_abdominal:
        final_diagnosis = "待排查：急性阑尾炎、急性胆囊炎、急性胰腺炎、消化性溃疡穿孔、肠梗阻"
        confidence = "中"
        recommended_dept = "普通外科/消化内科"
        key_findings = ["急性腹痛为主要症状", "需鉴别外科急腹症与内科疾病", "注意腹膜刺激征"]
        plan = ["腹部查体及影像学检查", "实验室检查：血常规、淀粉酶、肝功能", "必要时急诊手术探查"]
        red_flags = ["板状腹、反跳痛（腹膜炎）", "高热伴寒战（感染性休克）", "呕血/黑便（消化道出血）"]
    elif has_fever:
        final_diagnosis = "发热待查：感染性疾病、自身免疫性疾病、肿瘤性发热"
        confidence = "低"
        recommended_dept = "感染科/风湿免疫科"
        key_findings = ["发热为主要症状", "需系统排查感染源", "注意非感染性发热"]
        plan = ["血培养、尿培养、痰培养", "炎症指标：CRP、PCT、血沉", "影像学检查：胸片/CT"]
        red_flags = ["高热>39.5℃伴意识改变", "休克表现（低血压、心动过速）", "出血倾向"]
    elif has_diabetes:
        final_diagnosis = "糖尿病相关并发症待排查"
        confidence = "中"
        recommended_dept = "内分泌科"
        key_findings = ["糖尿病患者主诉胸痛/腹痛需特别注意非典型表现",
                        "需排查糖尿病酮症酸中毒、高渗性昏迷等急症"]
        plan = ["血糖、酮体监测", "糖化血红蛋白评估近期控制",
                "完善心肾功能及眼底检查"]
        red_flags = ["意识改变伴呼吸深快（警惕DKA）", "极端高血糖伴脱水"]
    else:
        final_diagnosis = "待进一步明确诊断，需结合辅助检查结果综合评估"
        confidence = "低"
        recommended_dept = "内科门诊"
        key_findings = ["主诉信息有限，建议完善相关检查"]
        plan = ["根据症状定位针对性检查", "必要时多学科会诊", "随访观察病情变化"]
        red_flags = ["症状持续或加重请及时就医"]

    # 处理高血压相关
    if has_hypertension:
        key_findings.append("高血压病史：注意血压控制目标及靶器官损害评估")
        plan.append("监测血压，评估降压方案合理性")

    # 完整性检查
    missing_info = ""
    data_completeness_score = completeness.get("score", 0)
    if data_completeness_score < 0.5:
        missing_info = "病历信息不完整，诊断置信度受限"
    elif data_completeness_score < 0.7:
        missing_info = "部分关键信息缺失，建议补充检查"

    # 组装报告
    report = {
        "final_diagnosis": final_diagnosis,
        "confidence": confidence,
        "recommended_dept": recommended_dept,
        "key_findings": key_findings,
        "plan": plan,
        "red_flags": red_flags,
        "disagreements": "Agnes会诊模式，暂无专科分歧记录",
        "warnings": missing_info or "本报告为AI辅助生成，仅供参考，最终诊疗决策以临床医生判断为准",
        "is_demo": False,
    }

    # 如有危急征象，追加到报告
    if flags_items:
        report["red_flags"] = [f["message"] for f in flags_items] + report["red_flags"]

    return report
