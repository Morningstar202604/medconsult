# -*- coding: utf-8 -*-
"""优化改动后的后端冒烟测试（不依赖外部 LLM）。"""
import sys

sys.path.insert(0, ".")

from app import cases, engine, library, mdt, rag, sessions, config as app_config
from app.llm import _normalize_base

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print("PASS", name, extra)
    else:
        fail += 1
        print("FAIL", name, extra)


# 1. base_url 规范化：GLM 的 /api/paas/v4 不得被改写
check("base_url GLM v4 原样保留",
      _normalize_base("https://open.bigmodel.cn/api/paas/v4") == "https://open.bigmodel.cn/api/paas/v4")
check("base_url 裸域名补 /v1",
      _normalize_base("https://api.deepseek.com") == "https://api.deepseek.com/v1")
check("base_url 已带 /v1 保留",
      _normalize_base("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1")
check("base_url ollama 本地",
      _normalize_base("http://127.0.0.1:11435/v1") == "http://127.0.0.1:11435/v1")

# 2. 健壮数值解析：坏值不抛异常
cfg = engine._llm_cfg({"mode": "llm", "api_key": "sk-x", "temperature": "abc", "max_tokens": None,
                       "request_timeout": float("nan")})
check("坏参数回退默认", cfg["temperature"] == 0.05 and cfg["max_tokens"] == 400 and cfg["timeout"] == 120)

# 2. 健壮数值解析：坏值不抛异常
cfg = engine._llm_cfg({"mode": "llm", "api_key": "sk-x", "temperature": "abc", "max_tokens": None,
                       "request_timeout": float("nan")})
check("坏参数回退默认", cfg["temperature"] == 0.05 and cfg["max_tokens"] == 400 and cfg["timeout"] == 120)

# 3. 无 Key 回退提示（不再静默降级）——屏蔽服务端 config.json 默认值再测
_orig_defaults = app_config.llm_defaults
app_config.llm_defaults = lambda: {}
try:
    ev = engine.auto_step("MedQA", 0, [], {"mode": "llm", "api_key": ""})
    check("无Key回退有提示", isinstance(ev, dict) and ev.get("notice"))
    res = mdt.consult("35岁女性，视物成双一个月", {"mode": "llm", "api_key": ""})
    check("MDT无Key回退有提示", bool(res.get("notice")))
finally:
    app_config.llm_defaults = _orig_defaults

# 4. mock MDT 全流程
res = mdt.consult("58岁男性，胸闷气短两周，有高血压史", {})
roles = [e["role"] for e in res["events"]]
check("MDT mock 事件流", "summary" in roles and "specialist" in roles and "report" in roles, str(roles[:6]))
check("MDT mock 报告字段", bool(res["report"].get("final_diagnosis")))

# 5. RAG：入库即检索（预存分词）
library.save_text("冒烟测试_指南.txt", "高血压患者推荐低盐饮食，每日钠摄入不超过 5 克，配合规律有氧运动。")
hits = rag.search("高血压 饮食", None, k=3)
check("RAG 命中", bool(hits) and "高血压" in hits[0]["text"], "score=%s" % (hits[0]["score"] if hits else None))

# 6. 会话存档
sid = sessions.save("mdt", "冒烟测试会诊", [{"role": "summary", "text": "x"}], {"final_diagnosis": "测试"})
got = sessions.get(sid)
check("会话存取", bool(got) and got["title"] == "冒烟测试会诊")
sessions.delete(sid)
check("会话删除", sessions.get(sid) is None)

# 7. 计算器
calcs = mdt.toolmod.detect_and_run("患者血压 150/95 mmHg，身高 170 cm，体重 80 kg")
names = [c["name"] for c in calcs]
check("计算器 MAP+BMI", "平均动脉压(MAP)" in names and "BMI" in names, str(names))

# 7b. CHA₂DS₂-VASc：72岁女性房颤+高血压+糖尿病+卒中史 = 1(女)+1(高压)+1(65-74)+1(糖)+2(卒中) = 6
sc = mdt.toolmod.detect_and_run("72岁女性，房颤病史，高血压10年，2型糖尿病，1年前脑卒中，心功能2级")
cha = next((c for c in sc if "CHA₂DS₂-VASc" in c["name"]), None)
check("CHA₂DS₂-VASc 评分=6", bool(cha) and cha["result"].startswith("6 分"), cha["result"] if cha else "未触发")

# 7c. CURB-65：80岁肺炎患者意识模糊+呼吸35次/分 = 2 + 年龄1 = 3
cu = mdt.toolmod.detect_and_run("80岁男性，社区获得性肺炎，意识模糊，呼吸 35 次/分，收缩压 110")
curb = next((c for c in cu if "CURB-65" in c["name"]), None)
check("CURB-65 评分=3", bool(curb) and curb["result"].startswith("3 分"), curb["result"] if curb else "未触发")

# 7d. Wells：DVT 患者，癌症+制动+全腿肿胀+凹陷性水肿 = 4 高度可能
we = mdt.toolmod.detect_and_run("考虑左下肢 DVT。活动期癌症患者，术后制动，全腿肿胀伴凹陷性水肿")
wells = next((c for c in we if "Wells" in c["name"]), None)
check("Wells 评分=4 高度可能", bool(wells) and wells["result"].startswith("4 分"), wells["result"] if wells else "未触发")

# 7e. 误触发防护：无房颤/肺炎/DVT 上下文时不输出评分
no_score = mdt.toolmod.detect_and_run("72岁女性，高血压10年，糖尿病")
check("无疾病上下文不误触发评分", not any("评分" in c["name"] for c in no_score), str([c["name"] for c in no_score]))

# 8. 清理冒烟文档
library.delete("冒烟测试_指南.txt")

# 9. 会诊技能包：播种 + 分层提示词注入
from app import skills as skills_mod
seeds = skills_mod.list_skills()
check("技能包播种4个", len(seeds) >= 4, str([s["id"] for s in seeds]))
sys_p = mdt.agent_system("角色X", {"skills": ["anticoag"]})
check("安全基线注入", "【AI会诊安全基线】" in sys_p)
check("技能注入", "【会诊技能:抗凝管理】" in sys_p)
check("未选技能不注入", "会诊技能" not in mdt.agent_system("角色X", {}))
tmp = skills_mod.save("冒烟技能", "测试", "测试提示词内容")
check("技能保存", bool(tmp) and skills_mod.get(tmp["id"])["name"] == "冒烟技能")
check("技能删除", skills_mod.delete(tmp["id"]) and skills_mod.get(tmp["id"]) is None)

# 10. 二轮讨论提示词必须带病历摘要（上下文工程修复）——用文本探针验证
import inspect
src = inspect.getsource(mdt._llm_opinion)
check("二轮提示词带摘要", "【病历摘要】" in src.split("else:")[1] if "else:" in src else False)

# 11. 临床要素引擎：完备度 + 红旗
from app import clinical
c = clinical.completeness("58岁男性，胸痛伴冷汗3小时，高血压病史，服氨氯地平，心电图送检，血压150/95")
check("完备度=6/6", c["score"] == 6, str(c))
rf = clinical.red_flags("突发胸痛伴大汗淋漓，向左肩放射")
check("红旗命中ACS", any("冠脉" in x for x in rf), str(rf))
check("无征象不误报", clinical.red_flags("头皮发麻") == [])

# 12. 检验参考值支持库
from app import reference as ref_mod
items = ref_mod.list_items()
check("参考库播种>=30项", len(items) >= 30, str(len(items)))
hits = ref_mod.search("肌钙蛋白")
check("参考库检索", bool(hits) and "肌钙蛋白" in hits[0]["item"])
blk = ref_mod.inject_references("患者BNP升高，血钾5.8，肌钙蛋白I待复查")
check("会诊文本注入参考值", "BNP" in blk and "血钾" in blk and "参考范围" in blk, blk[:40])
e = ref_mod.save_entry({"item": "冒烟指标", "en": "SMOKE", "range": "1-2", "unit": "x", "note": "t"})
check("参考库增补", ref_mod.search("冒烟指标")[0]["item"] == "冒烟指标")
check("参考库删除", ref_mod.delete_entry("冒烟指标") and not ref_mod.search("冒烟指标"))

# 13. 本院经验库（长期学习）
from app import feedback as fb_mod
fb_mod.save("房颤会诊", "心房颤动", True, "建议首选DOAC，查肌酐清除率")
sim = fb_mod.similar("65岁男性心悸，心电图示房颤，考虑抗凝治疗")
check("经验相似检索命中", bool(sim) and sim[0]["diagnosis"] == "心房颤动", str(sim[:1]))
check("无关病情不注入", not fb_mod.similar("膝关节皮疹"))

print("\n===== %d passed, %d failed =====" % (ok, fail))
sys.exit(1 if fail else 0)
