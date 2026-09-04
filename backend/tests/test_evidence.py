"""循证检索模块单元测试：证据分级 + 外部源优先/内部降级。"""
import pytest

from app import evidence as ev_mod
from app.evidence.providers import classify_level


def test_level_classification():
    assert classify_level("2024 ESC Guideline for AF", "") == "A"
    assert classify_level("Systematic Review and Meta-analysis", "") == "A"
    assert classify_level("Randomized controlled trial of X", "") == "B"
    assert classify_level("Cohort study of outcomes", "prospective cohort") == "C"
    assert classify_level("Case report on rare tumor", "") == "D"


def test_search_evidence_falls_back_internal_when_no_provider(monkeypatch):
    """未配置外部 provider → 内部资料库兜底。"""
    monkeypatch.setenv("EVIDENCE_PROVIDER", "")
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        res = asyncio_run(ev_mod.search_evidence("胸痛"))
        assert res["provider"] == "internal"
        assert res["degraded"] is True
        assert isinstance(res["items"], list)
    finally:
        get_settings.cache_clear()


def test_search_evidence_pubmed_uses_external(monkeypatch):
    monkeypatch.setenv("EVIDENCE_PROVIDER", "pubmed")

    async def fake_pubmed(query, n, api_key):
        return [{"title": "A meta-analysis of chest pain management",
                 "source": "Annals of Medicine", "date": "2026-01-01",
                 "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                 "snippet": "abstract", "level": "A", "first_author": "Zhang 等",
                 "doi": "doi:10.1000/xyz"}]

    import app.evidence.providers as prov
    monkeypatch.setattr(prov, "search_pubmed", fake_pubmed)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        res = asyncio_run(ev_mod.search_evidence("胸痛 meta 分析"))
        assert res["provider"] == "pubmed"
        assert res["degraded"] is False
        assert res["count"] == 1
        assert res["items"][0]["level"] == "A"
    finally:
        get_settings.cache_clear()


def test_search_evidence_pubmed_failure_falls_back(monkeypatch):
    """外部源抛异常 → 自动降级内部，不中断。"""
    monkeypatch.setenv("EVIDENCE_PROVIDER", "pubmed")

    async def boom(query, n, api_key):
        raise RuntimeError("network down")

    import app.evidence.providers as prov
    monkeypatch.setattr(prov, "search_pubmed", boom)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        res = asyncio_run(ev_mod.search_evidence("流感"))
        assert res["provider"] == "internal"
        assert res["degraded"] is True
    finally:
        get_settings.cache_clear()


def asyncio_run(coro):
    import anyio
    return anyio.run(lambda: coro)