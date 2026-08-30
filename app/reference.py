"""检验参考值对照库（医院支持库）。

内置常见检验项目的参考范围与临床意义，存储于 library/reference.json（首启播种，
医院可增删改）。用途：
  1. 侧栏「检验参考值」随时查询（/api/reference）；
  2. 会诊时自动检测病情文本中的检验项目，将参考范围注入会诊上下文（支持库增强）。
"""
import json
import os
import re
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_BASE, "library", "reference.json")

_lock = threading.Lock()

# item/英文名/单位/参考范围/低值/高值(数值型用于比对)/临床意义
SEED = [
    {"item": "白细胞", "en": "WBC", "unit": "×10⁹/L", "range": "3.5-9.5", "note": "升高：感染、应激；降低：放化疗、血液病"},
    {"item": "血红蛋白", "en": "Hb", "unit": "g/L", "range": "男130-175 女115-150", "note": "降低：贫血；升高：脱水、真性红细胞增多"},
    {"item": "血小板", "en": "PLT", "unit": "×10⁹/L", "range": "125-350", "note": "降低：血液病、脾亢、DIC；升高：反应性/骨髓增殖"},
    {"item": "C反应蛋白", "en": "CRP", "unit": "mg/L", "range": "<10", "note": "升高：感染、炎症、组织损伤"},
    {"item": "血沉", "en": "ESR", "unit": "mm/h", "range": "男<15 女<20", "note": "非特异，升高见于炎症、肿瘤、自身免疫病"},
    {"item": "降钙素原", "en": "PCT", "unit": "ng/mL", "range": "<0.05", "note": ">0.5 提示严重细菌感染/脓毒症"},
    {"item": "谷丙转氨酶", "en": "ALT", "unit": "U/L", "range": "9-50", "note": "升高：肝细胞损伤、药物性肝损"},
    {"item": "谷草转氨酶", "en": "AST", "unit": "U/L", "range": "15-40", "note": "升高：肝损、心肌/骨骼肌损伤"},
    {"item": "总胆红素", "en": "TBIL", "unit": "μmol/L", "range": "3.4-20.5", "note": "升高：黄疸（溶血/肝细胞性/梗阻性）"},
    {"item": "白蛋白", "en": "ALB", "unit": "g/L", "range": "40-55", "note": "降低：营养不良、肝病、肾病、消耗"},
    {"item": "血肌酐", "en": "Cr/SCr", "unit": "μmol/L", "range": "男57-111 女41-81", "note": "升高：肾功能不全；用药剂量调整依据"},
    {"item": "尿素氮", "en": "BUN", "unit": "mmol/L", "range": "2.6-7.5", "note": "升高：肾功不全、高分解、脱水（CURB-65 要素）"},
    {"item": "血钾", "en": "K", "unit": "mmol/L", "range": "3.5-5.3", "note": "<3.5 低钾（肌无力、心律失常）；>5.3 高钾（心动过缓/停搏风险）"},
    {"item": "血钠", "en": "Na", "unit": "mmol/L", "range": "137-147", "note": "降低：SIADH、利尿剂；意识改变"},
    {"item": "空腹血糖", "en": "FPG", "unit": "mmol/L", "range": "3.9-6.1", "note": "≥7.0 提示糖尿病（需复核）"},
    {"item": "糖化血红蛋白", "en": "HbA1c", "unit": "%", "range": "<6.5", "note": "反映近8-12周平均血糖；≥6.5 支持糖尿病"},
    {"item": "总胆固醇", "en": "TC", "unit": "mmol/L", "range": "<5.2", "note": "升高：血脂异常、动脉粥样硬化风险"},
    {"item": "低密度脂蛋白", "en": "LDL-C", "unit": "mmol/L", "range": "<3.4（ ASCVD 按危险分层更严）", "note": "动脉粥样硬化核心致病指标"},
    {"item": "高密度脂蛋白", "en": "HDL-C", "unit": "mmol/L", "range": ">1.0", "note": "降低增加心血管风险"},
    {"item": "甘油三酯", "en": "TG", "unit": "mmol/L", "range": "<1.7", "note": "升高：代谢综合征；>5.6 警惕胰腺炎"},
    {"item": "肌钙蛋白I", "en": "cTnI", "unit": "ng/mL", "range": "<0.04", "note": "升高：心肌损伤，ACS 诊断核心（动态复查）"},
    {"item": "B型钠尿肽", "en": "BNP", "unit": "pg/mL", "range": "<100", "note": "升高：心衰可能；NT-proBNP 按年龄分层"},
    {"item": "D-二聚体", "en": "D-Dimer", "unit": "μg/L", "range": "<500", "note": "阴性结合 Wells 低分可排除 VTE；升高非特异"},
    {"item": "凝血酶原时间", "en": "PT", "unit": "s", "range": "11-14.5", "note": "延长：凝血因子缺乏、抗凝药、肝病"},
    {"item": "国际标准化比值", "en": "INR", "unit": "-", "range": "0.8-1.2（华法林目标2.0-3.0）", "note": "抗凝监测核心指标"},
    {"item": "活化部分凝血活酶时间", "en": "APTT", "unit": "s", "range": "25-37", "note": "延长：肝素治疗、血友病等"},
    {"item": "促甲状腺激素", "en": "TSH", "unit": "mIU/L", "range": "0.27-4.2", "note": "甲亢/甲减筛查首选"},
    {"item": "血气-pH", "en": "pH", "unit": "-", "range": "7.35-7.45", "note": "酸碱失衡核心指标"},
    {"item": "血气-氧分压", "en": "PaO2", "unit": "mmHg", "range": "80-100", "note": "<60 呼吸衰竭 I 型标准"},
    {"item": "血气-二氧化碳分压", "en": "PaCO2", "unit": "mmHg", "range": "35-45", "note": ">50 伴低氧为 II 型呼衰"},
    {"item": "尿酸", "en": "UA", "unit": "μmol/L", "range": "男208-428 女155-357", "note": "升高：痛风、代谢综合征"},
    {"item": "淀粉酶", "en": "AMY", "unit": "U/L", "range": "<110", "note": "升高3倍以上支持急性胰腺炎"},
]


def _ensure():
    os.makedirs(os.path.dirname(PATH), exist_ok=True)


def _load_all():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_all(items):
    _ensure()
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)


def seed_if_empty():
    with _lock:
        if _load_all():
            return
        _save_all(SEED)


def list_items():
    seed_if_empty()
    return _load_all()


def search(q="", limit=40):
    q = (q or "").strip().lower()
    items = list_items()
    if not q:
        return items[:limit]
    out = [r for r in items if q in r.get("item", "").lower() or q in r.get("en", "").lower()]
    return out[:limit]


def save_entry(entry):
    item = (entry or {}).get("item", "").strip()
    if not item:
        return None
    with _lock:
        items = _load_all()
        items = [r for r in items if r.get("item") != item]
        items.append({"item": item, "en": entry.get("en", ""), "unit": entry.get("unit", ""),
                      "range": entry.get("range", ""), "note": entry.get("note", "")})
        _save_all(items)
    return entry


def delete_entry(item):
    with _lock:
        items = _load_all()
        remain = [r for r in items if r.get("item") != item]
        _save_all(remain)
        return len(remain) < len(items)


# 用于会诊上下文注入：英文缩写边界（不能用 \b——\w 含中文，中文相邻处无边界）
def _en_regex(en):
    first = en.split("/")[0].strip()
    try:
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(first) + r"(?![A-Za-z0-9])", re.I)
    except re.error:
        return None


_EN_PAT = [(r["item"], _en_regex(r.get("en", ""))) for r in SEED]


def inject_references(text, max_items=6):
    """检测病情文本涉及的检验项目，返回供会诊上下文使用的参考值块（无命中返回空串）。"""
    if not text:
        return ""
    t = text
    hits, seen = [], set()

    def _hit(row):
        it = row["item"]
        if it in t:
            return True
        # 别名匹配：肌钙蛋白I → 肌钙蛋白（去掉末尾亚型字母后仍保持≥2字）
        short = it.rstrip("IiVXab0-9")
        if len(short) >= 2 and short in t:
            return True
        for item, pat in _EN_PAT:
            if item == it and pat and pat.search(t):
                return True
        return False

    for r in list_items():
        if r["item"] not in seen and _hit(r):
            seen.add(r["item"])
            hits.append("{}：参考范围 {} {}（{}）".format(r["item"], r["range"], r["unit"], r["note"]))
        if len(hits) >= max_items:
            break
    if not hits:
        return ""
    return "【检验参考值（支持库）】\n" + "\n".join(hits)
