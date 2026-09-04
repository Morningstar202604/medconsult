"""实时循证检索：外部循证源（PubMed 等） + 内部资料库双通道。

企业交付对标项：医生要的不仅是答案，而是「依据从哪来、证据多强、是否过时」。
本模块产出带 来源/日期/链接/证据分级 的结构化结果；未配置外部源或网络不可用时
自动降级到内部资料库检索，保证功能不中断（graceful degradation）。
"""
import re
from datetime import date

# 证据分级（对照 循证医学五级体系）
LEVEL_LABEL = {
    "A": "指南/系统综述/Meta分析",
    "B": "随机对照试验(RCT)",
    "C": "队列/病例对照研究",
    "D": "病例报告/专家意见",
}


def classify_level(title: str, snippet: str) -> str:
    """基于标题/摘要关键词的启发式证据分级（非权威判定，仅作快速标签）。"""
    t = f"{title} {snippet}".lower()
    if re.search(r"(guideline|consensus|指南|共识|meta-?analysis|systematic review|cochrane)", t):
        return "A"
    if re.search(r"(randomized|randomised|rct|double-?blind|双盲|随机对照)", t):
        return "B"
    if re.search(r"(cohort|case-control|prospective|队列|病例对照|回顾性)", t):
        return "C"
    return "D"


def _clean_pubmed_snippet(abstract: str, maxlen: int = 500) -> str:
    if not abstract:
        return "（无摘要）"
    return re.sub(r"\s+", " ", abstract).strip()[:maxlen]


async def search_pubmed(query: str, max_results: int = 5,
                        api_key: str = "", base: str = "https://eutils.ncbi.nlm.nih.gov") -> list[dict]:
    """PubMed E-utilities 检索：esearch 取 PMID → esummary 取元数据。

    使用 httpx；网络不可用或超时向上抛异常，由 search_evidence 统一降级。
    """
    import httpx

    params = {"db": "pubmed", "term": query, "retmax": max_results,
              "retmode": "json", "sort": "relevance"}
    if api_key:
        params["api_key"] = api_key
    with httpx.Client(timeout=12, follow_redirects=True) as client:
        r = client.get(f"{base}/entrez/eutils/esearch.fcgi", params=params)
        r.raise_for_status()
        pmids = r.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return []
        ids = ",".join(pmids)
        s = client.get(f"{base}/entrez/eutils/esummary.fcgi",
                       params={"db": "pubmed", "id": ids, "retmode": "json"})
        s.raise_for_status()
        docs = s.json().get("result", {})

    today = date.today().isoformat()
    hits = []
    for pid in pmids:
        d = docs.get(pid, {})
        title = d.get("title", "（无标题）")
        title = re.sub(r"</?[^>]+>", "", title)  # 去 HTML 实体扰动
        journal = d.get("fulljournalname") or d.get("source") or ""
        pubdate = (d.get("pubdate") or d.get("epubdate") or "")[:10]
        authors = d.get("authors", [])
        first_author = (authors[0]["name"] if authors else "") + " 等" if authors else ""
        hits.append({
            "title": title.strip(),
            "source": journal,
            "date": pubdate or today,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
            "snippet": _clean_pubmed_snippet(d.get("abstract", "")),
            "level": classify_level(title, d.get("abstract", "")),
            "first_author": first_author,
            "doi": d.get("elocationid", "") if d.get("elocationid", "").startswith("doi") else "",
        })
    return hits