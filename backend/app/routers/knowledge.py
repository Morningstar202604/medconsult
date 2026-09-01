"""技能包与检验参考值路由。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from .. import models
from ..deps import DbDep
from ..deps import CurrentUser
from fastapi import Depends as _Depends
from ..deps import require_roles
from typing import Annotated
AdminUser = Annotated[models.User, _Depends(require_roles(models.Role.ADMIN))]
from ..schemas import ReferenceCreate, ReferenceDelete, SkillCreate

router = APIRouter(tags=["knowledge"])

SEED_SKILLS = [
    {"name": "抗凝管理", "desc": "房颤/VTE 抗凝决策与出血评估", "prompt":
     "涉及抗凝决策时：先完成血栓风险（CHA₂DS₂-VASc）与出血风险（HAS-BLED 要素）双评估；"
     "药物选择给出优先级；明确启动时机、肾功能剂量调整、桥接指征；提示需监测项与患者教育要点。"},
    {"name": "胸痛鉴别", "desc": "致命性胸痛红旗与时间敏感决策", "prompt":
     "涉及胸痛时：优先排除五类致命病因——ACS、主动脉夹层、肺栓塞、张力性气胸、心包填塞；"
     "按时间敏感顺序安排心电图/高敏肌钙蛋白/D-二聚体/CTA；不可在排除致命病因前给出良性结论。"},
    {"name": "儿童用药", "desc": "儿科体重剂量与禁忌核查", "prompt":
     "涉及儿科患者时：所有推荐剂量必须按体重(kg)或体表面积给出并附计算式；"
     "标注儿童禁用/慎用药物；成人剂型不可直接折算。"},
    {"name": "感染会诊", "desc": "脓毒症筛查与抗菌药物原则", "prompt":
     "涉及感染时：先做脓毒症筛查（qSOFA/SOFA 要素、乳酸）；经验性抗菌方案需覆盖感染部位"
     "+本地耐药风险，说明降阶梯与停药指征；48-72h 复评治疗反应。"},
]

SEED_REFERENCE = [
    {"item": "白细胞", "en": "WBC", "unit": "×10⁹/L", "range": "3.5-9.5", "note": "升高：感染、应激；降低：放化疗、血液病"},
    {"item": "血红蛋白", "en": "Hb", "unit": "g/L", "range": "男130-175 女115-150", "note": "降低：贫血；升高：脱水"},
    {"item": "血小板", "en": "PLT", "unit": "×10⁹/L", "range": "125-350", "note": "降低：血液病、脾亢、DIC"},
    {"item": "C反应蛋白", "en": "CRP", "unit": "mg/L", "range": "<10", "note": "升高：感染、炎症、组织损伤"},
    {"item": "降钙素原", "en": "PCT", "unit": "ng/mL", "range": "<0.05", "note": ">0.5 提示严重细菌感染/脓毒症"},
    {"item": "血肌酐", "en": "Cr", "unit": "μmol/L", "range": "男57-111 女41-81", "note": "升高：肾功能不全；用药剂量调整依据"},
    {"item": "尿素氮", "en": "BUN", "unit": "mmol/L", "range": "2.6-7.5", "note": "升高：肾功不全、高分解、脱水"},
    {"item": "血钾", "en": "K", "unit": "mmol/L", "range": "3.5-5.3", "note": "<3.5 低钾；>5.3 高钾风险"},
    {"item": "空腹血糖", "en": "FPG", "unit": "mmol/L", "range": "3.9-6.1", "note": "≥7.0 提示糖尿病（需复核）"},
    {"item": "糖化血红蛋白", "en": "HbA1c", "unit": "%", "range": "<6.5", "note": "≥6.5 支持糖尿病"},
    {"item": "肌钙蛋白I", "en": "cTnI", "unit": "ng/mL", "range": "<0.04", "note": "升高：心肌损伤，ACS 诊断核心"},
    {"item": "B型钠尿肽", "en": "BNP", "unit": "pg/mL", "range": "<100", "note": "升高：心衰可能"},
    {"item": "D-二聚体", "en": "D-Dimer", "unit": "μg/L", "range": "<500", "note": "阴性结合 Wells 低分可排除 VTE；升高非特异"},
    {"item": "国际标准化比值", "en": "INR", "unit": "-", "range": "0.8-1.2（华法林目标2.0-3.0）", "note": "抗凝监测核心指标"},
    {"item": "促甲状腺激素", "en": "TSH", "unit": "mIU/L", "range": "0.27-4.2", "note": "甲亢/甲减筛查首选"},
    {"item": "血气-氧分压", "en": "PaO2", "unit": "mmHg", "range": "80-100", "note": "<60 呼吸衰竭 I 型标准"},
    {"item": "血气-二氧化碳分压", "en": "PaCO2", "unit": "mmHg", "range": "35-45", "note": ">50 伴低氧为 II 型呼衰"},
    {"item": "尿酸", "en": "UA", "unit": "μmol/L", "range": "男208-428 女155-357", "note": "升高：痛风、代谢综合征"},
]


def seed_if_empty(db) -> None:
    if db.scalar(select(models.Skill).limit(1)) is None:
        for s in SEED_SKILLS:
            db.add(models.Skill(name=s["name"], desc=s["desc"], prompt=s["prompt"]))
    if db.scalar(select(models.ReferenceItem).limit(1)) is None:
        for r in SEED_REFERENCE:
            db.add(models.ReferenceItem(**r))
    db.commit()


# ---- skills ----
@router.get("/skills")
def list_skills(db: DbDep, user: CurrentUser):
    rows = db.scalars(select(models.Skill).order_by(models.Skill.id)).all()
    return {"items": [{"id": s.id, "name": s.name, "desc": s.desc,
                       "prompt": s.prompt, "active": s.active} for s in rows]}


@router.post("/skills")
def create_skill(body: SkillCreate, db: DbDep, user: AdminUser):
    s = models.Skill(name=body.name, desc=body.desc, prompt=body.prompt)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name}


@router.delete("/skills/{sid}")
def delete_skill(sid: int, db: DbDep, user: AdminUser):
    s = db.get(models.Skill, sid)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "技能不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---- reference ----
@router.get("/reference")
def list_reference(db: DbDep, user: CurrentUser, q: str = ""):
    q = (q or "").strip().lower()
    rows = db.scalars(select(models.ReferenceItem).order_by(models.ReferenceItem.id)).all()
    if q:
        rows = [r for r in rows if q in r.item.lower() or q in r.en.lower()]
    return {"items": [{"item": r.item, "en": r.en, "unit": r.unit,
                       "range": r.range, "note": r.note} for r in rows]}


@router.post("/reference")
def create_reference(body: ReferenceCreate, db: DbDep, user: AdminUser):
    r = models.ReferenceItem(**body.model_dump())
    db.add(r)
    db.commit()
    return {"ok": True}


@router.delete("/reference")
def delete_reference(body: ReferenceDelete, db: DbDep, user: AdminUser):
    r = db.scalar(select(models.ReferenceItem).where(models.ReferenceItem.item == body.item))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}
