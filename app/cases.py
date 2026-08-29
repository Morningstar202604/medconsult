"""Case loading for the consultation platform.

Wraps the AgentClinic JSONL datasets. Client-facing serialization never
includes the correct diagnosis or the test-result table -- those are server
secrets until a diagnosis is submitted for scoring.
"""
import json
import os
import re

DATA_FILES = {
    "MedQA": "agentclinic_medqa.jsonl",
    "MedQA_Ext": "agentclinic_medqa_extended.jsonl",
    "NEJM": "agentclinic_nejm.jsonl",
    "NEJM_Ext": "agentclinic_nejm_extended.jsonl",
}

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_raw(dataset):
    fname = DATA_FILES.get(dataset)
    if not fname:
        raise KeyError("unknown dataset: %s" % dataset)
    path = os.path.join(_BASE, fname)
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Case:
    def __init__(self, dataset, idx, raw):
        self.dataset = dataset
        self.id = idx
        osce = raw.get("OSCE_Examination", raw)  # NEJM files are flat
        self.raw_osce = osce
        self.patient_info = osce.get("Patient_Actor") or osce.get("patient_info") or {}
        self.examiner_info = osce.get("Objective_for_Doctor") or osce.get("question") or ""
        self.physical_exams = osce.get("Physical_Examination_Findings") or osce.get("physical_exams") or {}
        self.tests = osce.get("Test_Results") or {}
        if not self.tests and dataset.startswith("NEJM"):
            answers = osce.get("answers") or []
            self.diagnosis = next((a["text"] for a in answers if a.get("correct")), "")
        else:
            self.diagnosis = osce.get("Correct_Diagnosis") or ""

    # -- public (client-safe) summaries ------------------------------------
    @property
    def demographics(self):
        pi = self.patient_info
        if isinstance(pi, dict):
            return pi.get("Demographics") or ""
        return ""

    @property
    def chief_summary(self):
        """One-line complaint preview for the case list."""
        pi = self.patient_info
        if isinstance(pi, dict):
            hist = pi.get("History") or ""
            m = re.search(r"reports? (a [a-z0-9\- ]+? history of [^.,]+)", hist)
            if m:
                return m.group(1)[:90]
            return hist[:90]
        return str(pi)[:90]

    def public_view(self):
        return {
            "id": self.id,
            "dataset": self.dataset,
            "demographics": zh_demographics(self.demographics),
            "summary": self.chief_summary,
            "objective": self.examiner_info if not isinstance(self.examiner_info, dict) else str(self.examiner_info),
        }

    # -- server-side helpers -------------------------------------------------
    def patient_prompt_info(self):
        """Text injected into the patient agent system prompt."""
        pi = self.patient_info
        if isinstance(pi, dict):
            return json.dumps(pi, ensure_ascii=False)
        return str(pi)

    def exam_information(self):
        info = dict(self.physical_exams) if isinstance(self.physical_exams, dict) else {}
        info["tests"] = self.tests
        return info

    def flattened_tests(self):
        """{test_name: value} flattened from nested category dicts."""
        flat = {}

        def walk(d, prefix=""):
            for k, v in d.items():
                name = (prefix + " " + k).strip() if prefix else k
                if isinstance(v, dict):
                    walk(v, name)
                else:
                    flat[name] = v

        walk(self.tests or {})
        return flat


_DATA_ZH = {
    "MedQA": "MedQA 内科",
    "MedQA_Ext": "MedQA 扩展",
    "NEJM": "NEJM 影像",
    "NEJM_Ext": "NEJM 影像扩展",
}

_DEMO_ZH = [
    (re.compile(r"(\d+)[- ]year[- ]old\s+(male|man)", re.I), r"\1岁男性"),
    (re.compile(r"(\d+)[- ]year[- ]old\s+(female|woman)", re.I), r"\1岁女性"),
    (re.compile(r"(\d+)[- ]year[- ]old\s+(boy)", re.I), r"\1岁男孩"),
    (re.compile(r"(\d+)[- ]year[- ]old\s+(girl)", re.I), r"\1岁女孩"),
    (re.compile(r"(\d+)[- ]year[- ]old\s+child", re.I), r"\1岁儿童"),
    (re.compile(r"(\d+)[- ]year[- ]old", re.I), r"\1岁"),
    (re.compile(r"\bnewborn\b", re.I), "新生儿"),
    (re.compile(r"\binfant\b", re.I), "婴儿"),
]


def zh_demographics(text):
    """Translate the common demographic patterns; leave the rest as-is."""
    out = text or ""
    for pat, rep in _DEMO_ZH:
        out = pat.sub(rep, out)
    return out


def dataset_zh(name):
    return _DATA_ZH.get(name, name)


_LOADERS = {}


def list_cases(dataset):
    if dataset not in _LOADERS:
        _LOADERS[dataset] = [Case(dataset, i, raw) for i, raw in enumerate(_load_raw(dataset))]
    return _LOADERS[dataset]


def get_case(dataset, case_id):
    cases = list_cases(dataset)
    if not isinstance(case_id, int) or not (0 <= case_id < len(cases)):
        raise IndexError("case id out of range")
    return cases[case_id]
