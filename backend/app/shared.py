"""汇诊共享常量：跨前后端/模块统一的数据源。

此模块是以下内容的单一真实来源（Single Source of Truth）：
- 专科列表（SPECIALTIES）：后端 mdt.py 和前端 Consultations.tsx 共用
- Ollama 默认端口常量：用于 is_ollama 检测
- 运行时数据目录（storage_dir）：媒体/文档统一落址推导

新增专科时只需在此文件修改，前端可通过 API 同步获取最新列表。
"""
from pathlib import Path


def storage_dir(sub: str) -> Path:
    """运行时数据目录统一解析（媒体/文档/索引共用）。

    规则：
    - SQLite：与数据库文件同目录（如 backend/data/documents、backend/data/media），
      既能被 .gitignore 一并忽略，也让测试（临时库）天然隔离。
    - PostgreSQL/自定义：落在 ./data/<sub>（Docker 中 WORKDIR=/app，落在挂载卷内）。
    - 传入绝对路径时原样返回。
    目录不存在时自动创建。
    """
    from .config import get_settings

    s = get_settings()
    if sub and Path(sub).is_absolute():
        d = Path(sub)
    elif s.database_url.startswith("sqlite"):
        p = Path(s.database_url.split("sqlite:///", 1)[-1])
        base = p if p.is_absolute() else Path(".") / p
        d = base.parent / sub
    else:
        d = Path("./data") / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- 专科定义
SPECIALTIES = {
    "internal":   {"name": "内科专家", "emoji": "🫀", "label": "内科"},
    "surgery":    {"name": "外科专家", "emoji": "🦴", "label": "外科"},
    "pharmacy":   {"name": "药学专家", "emoji": "💊", "label": "药学"},
    "labimaging": {"name": "影像与检验专家", "emoji": "🩻", "label": "影像检验"},
    "neurology":  {"name": "神经内科专家", "emoji": "🧠", "label": "神经内科"},
    "cardio":     {"name": "心内科专家", "emoji": "❤️", "label": "心内科"},
    "pediatrics": {"name": "儿科专家", "emoji": "🧒", "label": "儿科"},
    "obgyn":      {"name": "妇产科专家", "emoji": "🤰", "label": "妇产科"},
}

DEFAULT_SPECIALTIES = ["internal", "surgery", "pharmacy", "labimaging"]

# ---------------------------------------------------------------- LLM 常量
# Ollama 默认监听端口，is_ollama 检测时使用
OLLAMA_DEFAULT_PORT = "11434"
