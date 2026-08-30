# Changelog

All notable changes to MedConsult are documented here.

## [0.5.0] - 2026-08-30

Hospital-workspace restructure + clinical support libraries + closed-loop learning.

### Added
- **检验参考值对照库（支持库）** — 32 seeded lab items (ranges/units/clinical meaning,
  `library/reference.json`); sidebar search panel; hospitals can add/delete entries;
  consultations auto-inject reference blocks for labs mentioned in the case text
  (CJK-safe abbreviation matching, subtype aliases like 肌钙蛋白→肌钙蛋白I).
- **临床要素引擎（确定性）** — 资料完备度 6 要素评分（缺项提示，写入报告置信度）+
  红旗危急征象扫描（ACS/卒中/夹层/出血/脓毒症/急腹症/低血糖），危急征象在专家发言
  前以横幅警示并合入报告 red_flags。
- **本院经验库（长期学习闭环）** — report card gains 👍有帮助 / 👎需修正（可填修正意见）；
  feedback persists to `library/feedback.json` and similar-case consultations auto-inject
  past experience (bigram-overlap retrieval, stopworded) as reference-only context.
- **会诊记录搜索** — sidebar filter by title/visit identifier.
- **技能包管理界面** — add/delete skills from ⚙️ settings (previously API-only).

### Changed
- **Workspaces merged 3→2**: 演示观摩台 folded into 问诊训练台 as a one-click
  「🤖 AI演示」 button (same case/dialogue/verdict pipeline); splash now two cards.
- 「跳过追问」now actually skips the pre-consultation round (previously it silently
  re-ran clarify — latent since v0.1.0).

## [0.4.0] - 2026-08-30

Agent-architecture pass: prompt layering, context engineering, skills, report follow-up.

### Added
- **Prompt layering** (提示词分层) for every MDT agent —
  `安全基线（AI不得虚构检查/病史、仅供参考、医师决策） → 医院规范（config.json hospital_policy，可写本院用药目录/检查路径） → 会诊技能（勾选的技能包） → 角色任务`。
  Trainer/demo modes keep the upstream AgentClinic protocol prompts for research fidelity.
- **Consultation skills (技能包)** — reusable specialist instruction packs stored in
  `library/skills/*.json`; four seeded skills: 抗凝管理 / 胸痛鉴别 / 儿童用药 / 感染会诊.
  Selectable per consultation in ⚙️ settings; injected into all specialists + moderator.
  CRUD via `/api/skills` (GET) and `/api/skills/save|delete` (POST) — hospitals can grow
  their own skill library.
- **Report follow-up (报告追问)** — after a report is generated, the composer stays live:
  doctors question the moderator agent about the report, with the report + recent
  discussion injected as context (`/api/mdt/followup`). The most natural doctor–AI
  interaction in real chart review.
- `hospital_policy` / `report_footer` config knobs (config.json).

### Fixed
- **Round-2 specialists discussed without the case**: the second-round prompt contained
  peers' opinions but NOT the medical summary — experts were cross-commenting blind.
  The summary is now included in every round.
- Frontend `runMdt` was called but never defined (latent ReferenceError on the MDT
  send path); the MDT composer now routes properly: 会诊/追问 by conversation stage.

## [0.3.0] - 2026-08-30

Hospital-readiness pass: clinical scoring tools, report printing/archive, patient identifiers.

### Added
- **Medical score calculators** (deterministic, conservative triggers — require disease context):
  CHA₂DS₂-VASc (atrial fibrillation stroke risk), CURB-65 (pneumonia severity),
  Wells score (DVT/PE likelihood), joining MAP/BMI/CrCl. Verified against textbook cases.
- **Report printing & export**: every MDT report card gets 🖨 打印 (hidden-iframe print)
  and ⬇ 导出 (standalone HTML archive) — hospital letterhead (configurable
  `hospital_name` in config.json), generation timestamp, and a physician
  signature/date block for paper archives.
- **Patient identifier** (就诊号/患者标识) in the structured intake form; flows into the
  consultation summary and archive title so records can be matched to the HIS.
- Upload whitelist: only txt/md/pdf/docx/json/csv/log/htm/html/xml accepted; anything
  else (e.g. .exe) is rejected with a clear 400 message. Document writes are serialized
  with a lock (concurrent uploads no longer interleave).

### Fixed
- `me_engine`: pending request files are now deleted when their answer is consumed
  (previously they accumulated and could be mistaken for live requests).

## [0.2.0] - 2026-08-30

Engineering audit & optimization round (bug fixes, robustness, performance, security).

### Fixed
- Trainer auto/demo loop: a doctor model that never emits the `DIAGNOSIS READY`
  protocol keyword after the turn budget made the consultation spin forever
  (observed with small local models); the platform now closes the dialogue for the
  moderator to score instead.
- `/api/mdt/clarify`: models that wrap each question in an object
  (`{"问题": "..."}`) were shown as raw dict reprs; values are now extracted.
- `server.py`: `ThreadingHTTPServer.allow_reuse_address` is disabled on Windows —
  its `SO_REUSEADDR` semantics allowed two server instances to bind 127.0.0.1:8765
  simultaneously with requests silently split between old and new code.
- `llm.py`: base_url no longer blindly appends `/v1` — endpoints with their own version
  path (e.g. GLM `https://open.bigmodel.cn/api/paas/v4`) were rewritten to `.../v4/v1`
  and every request failed; bare-host URLs still get `/v1` automatically. Migrated the
  bridge from the EOL `openai==0.28` global-state API to the maintained `openai>=1` SDK.
  Empty model replies now raise a clear error instead of returning "(模型返回为空)".
- `library.py`: missing `import json` made `reindex_all()` swallow a `NameError` and
  rebuild the whole RAG index on every startup.
- `web/app.js`: replaying an archived consultation rendered an empty report card
  (report was stored as a JSON string but used as an object); replay no longer
  re-archives the session; archive title was read from the already-cleared input box.
- `server.py` `/api/test_llm`: "Test connection" now falls back to the server-side
  `config.json` key like real consultations do (previously it failed whenever the
  browser box was left blank even with a working server default).
- Silent LLM→mock degradation: selecting "real model" without a usable key now shows
  an explicit fallback notice in the conversation instead of quietly scripting it.
- `requirements.txt`: `regex==2023.12.25` does not build on Python 3.13 (no wheel,
  source build fails); research-only deps (`transformers`, `datasets`, `anthropic`,
  `replicate`, stdlib `argparse`) split into `requirements-research.txt`; added the
  actually-used-but-unlisted `pypdf` / `python-docx` so PDF/DOCX upload works as
  documented; `server.py` docstring port corrected (8765).

### Changed
- Default LLM profile is GLM (Zhipu Bigmodel): `config.json` template now ships with
  the official OpenAI-compatible endpoint (`https://open.bigmodel.cn/api/paas/v4`) and
  `glm-4.5-air` preset; `/api/defaults` returns the endpoint/model suggestions even
  before a key exists, and the settings dialog prefills them — the user only pastes
  their API key (in ⚙️ Settings or `config.json`). The bundled local Ollama setup used
  during development was removed again.
- MDT pipeline: first-round opinions and second-round cross discussion now run the
  specialists **concurrently** (~3-4x faster consultations); a single specialist
  failure falls back to the scripted line instead of aborting the consultation.
- `rag.py`: token sets are precomputed at ingest and stored in `chunks.json`; the
  index is cached in memory by mtime — retrieval no longer re-reads and re-tokenizes
  the whole corpus per request.
- `config.py`: `config.json` cached by mtime; `MEDCONSULT_API_KEY` / `MEDCONSULT_BASE_URL`
  / `MEDCONSULT_MODEL` env vars override for container deployments.
- Numeric settings (temperature / max_tokens / timeout / rounds) parsed defensively —
  bad or NaN values fall back to defaults instead of raising 500s.

### Security
- Static file handler hardens the path check with a separator suffix (a sibling
  directory named `web*` could previously pass the prefix check).
- Request/upload body capped at 64 MB.

### Added
- **ZCode temporary engine bridge (`me_engine/`)** — a local OpenAI-compatible shim
  (stdlib only, port 8790): the platform posts chat requests to a file queue, the ZCode
  agent answers them live and the shim streams the reply back. Lets the assistant act
  as the platform's LLM directly, with no external API. Unanswered requests degrade
  gracefully after a wait window instead of hanging. Configure via `config.json`
  (`base_url: http://127.0.0.1:8790/v1`); live only while the ZCode session runs.
- `MEDCONSULT_HOST` / `MEDCONSULT_PORT` env vars to move the listener without editing code.
- `tests/smoke_optim.py` — 14-assertion backend smoke suite for the above.
- `start_web.bat` now auto-creates the venv on first run instead of failing silently.

### Fixed (round 2, found during live engine testing)
- **重置 button was born disabled and never re-enabled** — after a consultation ended
  the UI offered no way to reset (only mode-switching side effect); now enabled when a
  consultation starts and re-disabled on reset.
- `/api/defaults` now returns endpoint/model suggestions even without a key, and the
  settings dialog prefills them — the user only pastes the API key.

## [0.1.0] - 2026-08-29

First public release. Built on AgentClinic (MIT) as the upstream research baseline.

### Added
- Three workspaces: Consultation Workbench (MDT), Consultation Trainer, Demo Stage
- Local-first architecture: stdlib HTTP server, dependency-free frontend, data never leaves the machine
- Local document library (txt / md / pdf / docx) with persistent disk storage
- RAG retrieval tool: chunk index on ingest, relevance retrieval during consultations
- Medical calculator tools: MAP, BMI, Cockcroft-Gault creatinine clearance
- Consultation memory: auto-archive, replay, delete, clear (local storage)
- Prompt pool: editable per-role system prompts with named presets
- Configurable sandbox: tool whitelist, request timeout, local data boundary
- Streaming OpenAI-compatible LLM bridge (works with relays that require `stream=true`)
- Pre-consultation clarification round and structured intake form
- Per-role model assignment, 13 cognitive-bias injection, connection test
- Headless-browser end-to-end test (`tests/e2e_cdp.py`)
- English / Chinese / Japanese documentation
