"""红旗危急征象扫描（确定性规则）。

相对原版改进：
1. 分级：emergent（需立即急诊）/ urgent（需紧急评估）/ review（需关注），
   报告与横幅按级别区分措辞，避免"胸痛+限定词"才触发的漏报。
2. 关键词召回更全：纯"新发胸痛/胸闷"也进入 urgent 而非静默。
3. 每条规则带可读依据（命中原文片段），可审计。
"""
import re
from dataclasses import dataclass

# 否定语境剥离：患者说"无放射/没有出汗/不压榨"时，这些危险词是"否认"而非"存在"，
# 直接剥除，避免把否定当阳性红旗误报。
_NEG_PATTERN = re.compile(
    r"(?:无|没有|没|不|未|否认|否认有|从未|从不)"
    r"(?:放射到?左(?:肩|臂)|向左(?:肩|臂)放射|放射|出汗|冷汗|大汗|压榨|濒死感|濒死|"
    r"胸痛|胸闷|心前区|头痛|头晕|晕厥|黑矇|呼吸困难|气促|咯血|呕血|便血|黑便|"
    r"恶心|呕吐|腹痛|发热|高热|昏迷|抽搐|麻木|无力|言语不清|口角歪斜)"
)


def _strip_negations(text: str) -> str:
    return _NEG_PATTERN.sub("", text or "")


# (pattern, severity, message)
_RULES: list[tuple[str, str, str]] = [
    # ---- emergent：时间敏感，需立即急诊 ----
    (r"(胸|心前区)[痛闷压][^。；]{0,16}(冷汗|大汗|濒死|压榨|放射|向左臂|向左肩)", "emergent", "疑似急性冠脉综合征（胸痛伴冷汗/放射/压榨感）"),
    (r"意识(模糊|障碍|不清|丧失)|昏迷|呼之不应", "emergent", "意识障碍——需紧急评估（脑血管事件/代谢危象等）"),
    (r"突发.{0,8}剧烈头痛|炸裂样|撕裂样.{0,6}痛|刀割样.{0,6}痛", "emergent", "剧烈头痛——警惕蛛网膜下腔出血/主动脉夹层"),
    (r"呼吸困难|气促.{0,8}加重|不能平卧|端坐呼吸|喘息.{0,4}加重", "emergent", "呼吸困难/端坐呼吸——警惕心衰、肺栓塞、气道急症"),
    (r"咯血|呕血|大量便血|柏油样便", "emergent", "出血表现——需紧急处理"),
    (r"一侧.{0,8}(无力|麻木|瘫痪)|言语不清|口角歪斜|面瘫.{0,4}突发", "emergent", "卒中征象（FAST）——时间窗内需紧急评估溶栓"),
    (r"血压.{0,8}测不出|无脉|苍白.{0,6}湿冷|休克", "emergent", "休克/循环衰竭征象"),
    (r"呼吸.{0,8}(>|＞|大于)?\s?[3-9]\d\s*次|呼吸.{0,4}(30|35|40|45|50)\s*次", "emergent", "呼吸急促（≥30次/分）——警惕呼吸衰竭"),
    # ---- urgent：需尽快就医评估 ----
    # 独立危险词（不依赖"胸痛"前缀）：问诊逐轮回答常为片段，患者说"放射到左肩/出冷汗"
    # 即使本句没有"胸痛"二字也需立刻拦截，避免漏检。
    (r"(放射到?左(肩|臂)|向左(肩|臂)放射|压榨样|刀割样|撕裂样.{0,4}痛)", "urgent", "高度提示心源性/主动脉性疼痛——需立即评估急性冠脉综合征或主动脉夹层"),
    (r"(冷汗|大汗淋漓|出冷汗|濒死感)", "urgent", "冷汗/濒死感——常提示心源性或休克早期征象，需尽快评估"),
    (r"胸[痛闷]|心前区[痛闷]", "urgent", "新发胸痛/胸闷——需尽快行心电图与心肌损伤标志物评估"),
    (r"晕厥|黑矇|跌倒发作|一过性意识", "urgent", "晕厥/黑矇——警惕心源性与栓塞事件"),
    (r"剧烈腹痛|板状腹|腹肌紧张|压痛.{0,6}反跳痛", "urgent", "急腹症征象——需外科紧急评估"),
    (r"高热(不退|持续)?|体温\s*3[9-9](\.\d)?", "urgent", "高热——警惕感染/脓毒症"),
    (r"单侧肢体肿痛|下肢.{0,4}肿胀.{0,6}疼痛|腓肠肌.{0,4}痛", "urgent", "下肢单侧肿痛——警惕深静脉血栓"),
    (r"血[压]?糖.{0,6}(测不出|极低|2\.8|3\.9)|\b低血糖\b|大汗.{0,6}手抖.{0,6}心慌", "urgent", "低血糖危象可能——立即进食并监测血糖"),
    # ---- review：需关注 ----
    (r"血压\s*[1-9]\d{2,}\s*[/／]\s*1[1-9]\d|血压.{0,6}(180|200|220)\s*[/／]", "review", "血压明显升高——需评估高血压急症风险"),
    (r"发热.{0,10}皮疹|皮疹.{0,10}发热", "review", "发热伴皮疹——需警惕感染性疾病"),
]


@dataclass
class RedFlag:
    severity: str
    message: str
    matched: str


_SEVERITY_LABEL = {
    "emergent": "立即急诊",
    "urgent": "尽快就医",
    "review": "需要关注",
}
_ORDER = {"emergent": 0, "urgent": 1, "review": 2}


def scan(text: str) -> list[RedFlag]:
    """返回命中的红旗列表，按严重度降序，含匹配原文依据。"""
    t = _strip_negations(text or "")
    hits: list[RedFlag] = []
    seen: set[str] = set()
    for pattern, severity, message in _RULES:
        m = re.search(pattern, t)
        if m and message not in seen:
            seen.add(message)
            matched = m.group(0)[:40]
            hits.append(RedFlag(severity=severity, message=message, matched=matched))
    hits.sort(key=lambda r: _ORDER[r.severity])
    return hits


def worst_severity(hits: list[RedFlag]) -> str | None:
    if not hits:
        return None
    return min(hits, key=lambda r: _ORDER[r.severity]).severity


def banner_text(hits: list[RedFlag]) -> str:
    """供前端横幅展示的文本。"""
    if not hits:
        return ""
    top = hits[0].severity
    label = _SEVERITY_LABEL[top]
    parts = [f"{label}：{h.message}（依据：…{h.matched}）" for h in hits]
    return "\n".join(parts)
