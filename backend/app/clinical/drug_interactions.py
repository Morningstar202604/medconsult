"""药物相互作用检查（垂直临床 agent 工具层差异化）。

通用 agent 对"这个药和那个药能不能一起吃"只会泛泛而谈；
这里给出一份可审计的常见相互作用规则库：命中即给出
- 药物对 / 临床后果 / 严重度 / 处理建议 / 依据（通用用药学共识，非具体文献页码）。

规则仅覆盖临床上最常见、后果明确的相互作用（"知道就救命、不知道就出事"的一批），
真实全面评估需接药品库 API/权威数据库（留 provider 接口，未配置时用规则库+RAG 兜底）。
"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class Interaction:
    drug_a: str
    drug_b: str
    consequence: str
    severity: str          # major|moderate|minor
    advice: str
    basis: str


# 中文/英文/常见别名匹配。key 既可以是具体药，也可以是逻辑药物组
# （如 NSAIDs/他汀类），规则引用这些 key（"/" 分隔表示任一组命中即可）。
_ALIASES: dict[str, list[str]] = {
    "华法林": ["华法林", "warfarin"],
    "阿司匹林": ["阿司匹林", "aspirin", "拜阿司匹林"],
    "NSAIDs": ["布洛芬", "ibuprofen", "芬必得", "萘普生", "naproxen", "塞来昔布",
               "celecoxib", "西乐葆", "双氯芬酸", "diclofenac", "扶他林",
               "消炎痛", "吲哚美辛", "nsaid", "nsaids", "非甾体"],
    "胺碘酮": ["胺碘酮", "amiodarone", "可达龙"],
    "甲硝唑": ["甲硝唑", "metronidazole"],
    "氟康唑": ["氟康唑", "fluconazole"],
    "克拉霉素": ["克拉霉素", "clarithromycin"],
    "伊曲康唑": ["伊曲康唑", "itraconazole"],
    "他汀类": ["阿托伐他汀", "atorvastatin", "立普妥", "辛伐他汀", "simvastatin",
               "舒降之", "瑞舒伐他汀", "rosuvastatin", "他汀", "statin"],
    "ACEI": ["依那普利", "培哚普利", "赖诺普利", "卡托普利", "雷米普利", "acei"],
    "ARB": ["缬沙坦", "氯沙坦", "厄贝沙坦", "替米沙坦", "坎地沙坦", "arb"],
    "螺内酯": ["螺内酯", "spironolactone", "安体舒通"],
    "氯化钾": ["氯化钾", "potassium", "补钾"],
    "二甲双胍": ["二甲双胍", "metformin", "格华止"],
    "碘造影剂": ["碘造影剂", "碘对比剂", "造影剂", "contrast"],
    "地高辛": ["地高辛", "digoxin"],
    "维拉帕米": ["维拉帕米", "verapamil"],
    "利福平": ["利福平", "rifampin", "rifampicin"],
    "口服避孕药": ["口服避孕药", "避孕药", "ocp", "oral contraceptive"],
    "MAOIs": ["司来吉兰", "苯乙肼", "异卡波肼", "maoi", "单胺氧化酶抑制剂"],
    "SSRI": ["氟西汀", "帕罗西汀", "舍曲林", "西酞普兰", "艾司西酞普兰", "氟伏沙明", "ssri"],
    "阿片类": ["吗啡", "羟考酮", "芬太尼", "曲马多", "可待因", "阿片", "opioid"],
    "苯二氮卓类": ["地西泮", "阿普唑仑", "劳拉西泮", "氯硝西泮", "艾司唑仑", "苯二氮卓", "bzd"],
    "沙丁胺醇": ["沙丁胺醇", "salbutamol"],
    "普萘洛尔": ["普萘洛尔", "propranolol"],
    "西地那非": ["西地那非", "sildenafil", "万艾可"],
    "硝酸酯类": ["硝酸甘油", "单硝酸异山梨酯", "硝酸异山梨酯", "nitrate"],
    "别嘌醇": ["别嘌醇", "allopurinol"],
    "硫唑嘌呤": ["硫唑嘌呤", "azathioprine"],
    "氟喹诺酮": ["左氧氟沙星", "莫西沙星", "环丙沙星", "氧氟沙星", "quinolone"],
}

_RULES: list[Interaction] = [
    Interaction("华法林", "阿司匹林/NSAIDs", "显著增加消化道及颅内出血风险", "major",
                "尽量避免联用；必须联用时监测 INR 与出血症状，必要时 PPI 保护",
                "抗栓与抗血小板叠加的出血风险（通用抗凝共识）"),
    Interaction("华法林", "胺碘酮", "INR 明显升高，出血风险增加", "major",
                "联用减量并 1 周内复查 INR", "胺碘酮抑制华法林代谢（CYP2C9/2C19）"),
    Interaction("华法林", "甲硝唑/氟康唑", "INR 升高，出血风险增加", "major",
                "联用时加强 INR 监测（2-3 天）", "CYP2C9 抑制使华法林血药浓度升高"),
    Interaction("他汀类", "克拉霉素/伊曲康唑", "肌病/横纹肌溶解风险显著增加", "major",
                "避免联用；确需联用暂停他汀或换用代谢途径不同的他汀",
                "CYP3A4 强抑制剂使他汀浓度升高"),
    Interaction("ACEI/ARB", "螺内酯/氯化钾", "高钾血症风险", "major",
                "联用时定期查血钾与肾功能", "保钾机制叠加"),
    Interaction("二甲双胍", "碘造影剂", "乳酸性酸中毒风险（肾功能不全时）", "major",
                "eGFR<30 时造影前停用二甲双胍并造影后 48h 评估再恢复",
                "造影剂肾损害+二甲双胍乳酸堆积（通用用药共识）"),
    Interaction("地高辛", "胺碘酮/维拉帕米", "地高辛中毒（恶心/心律失常）风险", "major",
                "联用地高辛减量并监测血药浓度", "肾清除与 P-gp 抑制"),
    Interaction("利福平", "华法林/口服避孕药", "药效显著下降", "major",
                "联用时相应增加剂量或换用方案并监测", "强效 CYP 诱导剂"),
    Interaction("MAOIs", "SSRI/含酪胺食物", "5-羟色胺综合征或高血压危象", "major",
                "两药间隔至少 14 天；出现高热/肌阵挛/意识改变立即急诊",
                "单胺氧化酶抑制叠加"),
    Interaction("阿片类", "苯二氮卓类", "中枢抑制、呼吸抑制、死亡风险增加", "major",
                "尽量避免联用；确需联用最低剂量并观察呼吸状态",
                "CNS 抑制叠加（FDA 黑框警告类）"),
    Interaction("硝酸酯类", "西地那非", "严重低血压/晕厥", "major",
                "24 小时内禁止联用（西地那非）", "NO 通路协同扩血管"),
    Interaction("阿司匹林", "布洛芬/NSAIDs", "阿司匹林抗血小板作用被削弱（心血管保护打折）", "moderate",
                "如需 NSAID 可考虑对乙酰氨基酚或联用前服用阿司匹林并间隔 2h",
                "NSAID 竞争 COX-1 位点"),
    Interaction("阿司匹林", "ACEI/ARB", "ACEI 降压与器官保护作用减弱", "moderate",
                "监测血压；高剂量阿司匹林时更明显", "前列腺素抑制"),
    Interaction("甲硝唑", "酒精", "双硫仑样反应（面红/心悸/呕吐）", "moderate",
                "用药期间及停药后 3 天内禁酒", "抑制乙醛脱氢酶"),
    Interaction("氟喹诺酮", "含金属离子抗酸剂/钙铁锌", "抗菌药吸收下降", "moderate",
                "间隔 2-4 小时服用", "螯合作用"),
    Interaction("别嘌醇", "硫唑嘌呤", "骨髓抑制风险显著增加", "major",
                "避免联用；确需联用硫唑嘌呤减量 75% 并监测血常规",
                "黄嘌呤氧化酶抑制使硫唑嘌呤蓄积"),
    Interaction("普萘洛尔", "沙丁胺醇", "β受体拮抗降低支气管扩张效果", "moderate",
                "哮喘/COPD 患者慎用非选择性 β 阻滞剂", "β2 受体拮抗"),
]


def _match_meds(text: str) -> set[str]:
    """从用药文本中识别命中的药物组。"""
    t = (text or "").lower()
    found: set[str] = set()
    for drug, aliases in _ALIASES.items():
        if any(a.lower() in t for a in aliases):
            found.add(drug)
    return found


def check_interactions(meds_text: str) -> list[dict]:
    """检查用药文本中的相互作用。返回命中列表（含严重度/处理建议/依据）。"""
    found = _match_meds(meds_text)
    out: list[dict] = []
    for r in _RULES:
        a_group = [a for a in r.drug_a.split("/") if a]
        b_group = [b for b in r.drug_b.split("/") if b]
        fa = [g for g in a_group if g in found]
        fb = [g for g in b_group if g in found]
        if fa and fb:
            out.append({
                "drugs": f"{' / '.join(fa)} × {' / '.join(fb)}",
                "consequence": r.consequence,
                "severity": r.severity,
                "advice": r.advice,
                "basis": r.basis,
            })
    order = {"major": 0, "moderate": 1, "minor": 2}
    out.sort(key=lambda x: order[x["severity"]])
    return out


def summary_text(hits: list[dict]) -> str:
    if not hits:
        return "未检出已知药物相互作用（规则库范围内）"
    parts = []
    for h in hits:
        tag = {"major": "高危", "moderate": "中危", "minor": "低危"}[h["severity"]]
        parts.append(f"[{tag}] {h['drugs']}：{h['consequence']}→{h['advice']}")
    return "；".join(parts)
