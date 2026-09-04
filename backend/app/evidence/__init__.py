"""循证检索统一入口：外部源优先、内部资料库兜底（graceful degradation）。

用法：res = await search_evidence(query)
返回 {"items": [...], "provider": "pubmed"|"internal", "count": N, "degraded": bool}
"""
from ..config import get_settings
from ..rag import search as rag_search


async def search_evidence(query: str, max_results: int | None = None) -> dict:
    """外部循证源检索；未配置/失败时自动降级到内部资料库。"""
    s = get_settings()
    n = max_results or s.evidence_max_results or 5
    provider = (s.evidence_provider or "").strip().lower()
    if provider and provider not in ("none", "off", "internal"):
        try:
            if provider == "pubmed":
                from .providers import search_pubmed
                items = await search_pubmed(query, n, s.evidence_api_key)
            else:
                raise ValueError(f"不支持的证据源 provider: {provider}")
            if items:
                return {"items": items, "provider": "pubmed",
                        "count": len(items), "degraded": False}
        except Exception:
            pass  # 外部源失败 → 内部兜底
    return search_internal(query, n)


def search_internal(query: str, n: int = 5) -> dict:
    """内部资料库检索兜底。"""
    try:
        chunks = rag_search(query, k=n)
    except Exception:
        chunks = []
    items = [{"title": c["doc"], "source": "内部资料库", "date": "",
              "url": "", "snippet": c["text"][:400],
              "level": "D", "first_author": ""} for c in chunks]
    return {"items": items, "provider": "internal",
            "count": len(items), "degraded": True}