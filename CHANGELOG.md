# Changelog

All notable changes to MedConsult are documented here.

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
