<div align="center">

# 🏥 MedConsult · 汇诊

**A local-first, hospital-oriented multi-agent MDT consultation platform**

*Multi-specialist AI consultation · Clinical scoring tools · Lab reference library · Prompt layering & Skills · Closed-loop learning · Report printing & archiving*

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

`MIT License` `Python 3.10+` `Zero web framework` `Data stays on your machine`

**MDT** · **Clinical Decision Support** · **Multi-Agent** · **RAG** · **EMR/HIS-friendly** · **DeepSeek / GLM / Qwen / OpenAI / Ollama**

[🚀 Quick Start](#-quick-start) · [✨ Features](#-features) · [🧠 Agent Architecture](#-agent-architecture) · [🖼 Screenshots](#-screenshots) · [⚙️ Configuration](#%EF%B8%8F-configuration)

</div>

---

## ⚠️ Disclaimer

> MedConsult is a **research and demonstration platform**. It is **NOT a medical device**; outputs are references for licensed physicians only, never medical advice or prescriptions. You are responsible for compliance with local healthcare regulations.

## ✨ Features

**🏥 Built for real hospital workflows**

- 🚨 **Red-flag triage before anything else** — deterministic critical-sign scanning (ACS / stroke / dissection / hemorrhage / sepsis / acute abdomen…) warns in a banner *before* specialists speak, and flows into the report's emergency section.
- 📊 **Data-completeness scoring** — 6 structured elements (age/sex, duration, history, medication, exams, vitals) with explicit "missing" hints; shown next to the report confidence so it is *explainable*, not vibes.
- 🧮 **Deterministic medical calculators & scores** — MAP, BMI, Cockcroft-Gault CrCl, **CHA₂DS₂-VASc**, **Wells (DVT/PE)**, **CURB-65** — auto-detected from the case text, computed locally, auditable in the transcript.
- 🧾 **Lab reference library (支持库)** — 32+ seeded lab items with ranges & clinical meaning; searchable in the sidebar, editable by the hospital, and **auto-injected into consultations** when the case mentions them.
- 🖨 **Report printing & archiving** — every report prints with configurable hospital letterhead, timestamp and physician signature/date block; one-click export to standalone HTML for the medical record room.
- 🔄 **Report follow-up (报告追问)** — after the report, the composer stays live: physicians question the moderator agent with the report + discussion as context. The most natural chart-review interaction.
- 🧑‍🏫 **Consultation trainer** — practice interviewing an AI patient (`REQUEST TEST` / `DIAGNOSIS READY` protocol), moderator scoring; one-click **AI demo mode** for teaching & product demos.

**🧠 Real agent engineering**

- 🥞 **Layered prompt engineering** — `AI safety baseline → hospital policy (config) → consultation skills → role task`, applied to every MDT agent. Hospitals write their own drug-formulary / pathway rules in plain text.
- 🧩 **Skills (技能包)** — reusable specialist instruction packs (seeded: 抗凝管理 / 胸痛鉴别 / 儿童用药 / 感染会诊). Select per consultation, grow your department library, manage in ⚙️ settings.
- 📚 **Context engineering** — case summary + retrieved document chunks + lab references + past feedback are assembled per agent with budgets; round-2 debaters always see the case (yes, this was a real bug we fixed).
- 🌱 **Closed-loop learning** — physicians mark reports 👍 helpful / 👎 needs-correction (with corrections); feedback persists locally and similar future consultations auto-inject "本院既往经验" as reference-only context.
- 🤖 **True multi-agent MDT** — triage assistant → per-specialist independent opinions (concurrent) → cross-discussion → moderator consensus report; any OpenAI-compatible model per role.

**🔒 Local-first & safe**

- Everything (documents, sessions, prompts, feedback, config) stays on your machine. Only the LLM provider you configure is called.
- Zero web framework: server is Python stdlib; frontend is dependency-free vanilla JS. `pip install -r requirements.txt` and go.
- Upload whitelist, path-traversal hardening, body-size caps, port double-bind protection.

## 🖼 Screenshots

![MDT with triage banner & injected references](docs/images/mdt_triage_banner.png)
*Consultation workbench: red-flag banner → summary with injected lab references & past hospital experience → specialist opinion → calculator → structured report (completeness 6/6, signature block, 👍/👎 feedback)*

| | |
|---|---|
| ![Report details](docs/images/mdt_triage_report.png) | ![Workspace launcher](docs/images/splash.png) |
| *Report card: confidence + data completeness, calculations, red flags, print/export* | *Launcher: 会诊工作台 / 问诊训练台* |
| ![Settings](docs/images/settings.png) |
| *⚙️ Settings: model per role, prompt pool, skills, hospital policy, biases, sandbox* |

## 🚀 Quick Start

```bash
git clone https://github.com/Morningstar202604/medconsult.git
cd medconsult

python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python server.py
# Linux / macOS
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Open **http://127.0.0.1:8765** — or double-click `start_web.bat` on Windows.
Without any API key the platform runs in **scripted demo mode**; the built-in English research case library (MedQA / NEJM, 456 cases) works as training material.

### Configure an LLM (30 seconds)

Option A — server-wide defaults in `config.json` (see `config.json.example`, gitignored):

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "hospital_name": "XX医院",
  "hospital_policy": "本院规范：抗凝药物仅限目录内品种；出院带药不超过14天。"
}
```

Works with **OpenAI / DeepSeek / GLM (open.bigmodel.cn/api/paas/v4) / Qwen / Ollama** — any OpenAI-compatible endpoint, including local models.
Option B — in-app: **⚙️ Settings → 真实大模型**, paste your key, 🔌 Test Connection. Keys live in your browser's localStorage; they never leave the machine.

## 🧠 Agent Architecture

```
┌────────────────────────────────────────────────────────┐
│ Prompt layering (every MDT agent)                      │
│  1. AI safety baseline   — no fabrication, physician-  │
│     in-command, reference-only output                  │
│  2. Hospital policy      — your formulary / pathway    │
│  3. Consultation skills  — anticoag / chest-pain /     │
│     peds-dosing / infection (editable library)         │
│  4. Role task            — specialist / moderator      │
├────────────────────────────────────────────────────────┤
│ Context assembly per agent:                            │
│  case summary · RAG chunks · lab references ·          │
│  past feedback (similar cases) · calculator results    │
├────────────────────────────────────────────────────────┤
│ Pipeline: triage → summary → specialist opinions ×N    │
│  (concurrent) → cross discussion → consensus report →  │
│  physician follow-up Q&A → feedback → experience base  │
└────────────────────────────────────────────────────────┘
```

## ⚙️ Configuration

| Key | Purpose |
|---|---|
| `api_key` / `base_url` / `model` | LLM endpoint (OpenAI-compatible, incl. Ollama) |
| `hospital_name` | Letterhead on printed reports |
| `hospital_policy` | Hospital-specific rules injected into every agent |
| `report_footer` | Footer note on printed reports |

Env overrides: `MEDCONSULT_API_KEY` / `MEDCONSULT_BASE_URL` / `MEDCONSULT_MODEL` / `MEDCONSULT_HOST` / `MEDCONSULT_PORT`.

## 📚 Documentation

- [简体中文说明](README.zh-CN.md) · [CHANGELOG](CHANGELOG.md) · [CONTRIBUTING](CONTRIBUTING.md) · [SECURITY](SECURITY.md)
- Upstream research baseline: [AgentClinic](https://github.com/SamuelSchmidgall/AgentClinic) (MIT) — the trainer/verdict protocol mirrors its benchmark.

## License

MIT © MedConsult Contributors. Medical disclaimer above applies.
