"""相似度工具：中文二元组重叠加权。"""
import re

_STOP = {"患者", "临床", "建议", "治疗", "检查", "报告", "会诊", "医院", "本次", "进行"}


def bigrams(t: str) -> set[str]:
    out: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", (t or "").lower()):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
        out.add(run)
    return {b for b in out if b not in _STOP}


def bigram_overlap(a: str, b: str) -> int:
    ba = bigrams(a)
    if not ba:
        return 0
    return len(ba & bigrams(b))
