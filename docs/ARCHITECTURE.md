# MedConsult Architecture

## Overview

MedConsult is deliberately simple to deploy and audit: a single-process Python
standard-library HTTP server plus a dependency-free frontend. All state (documents,
sessions, prompts, settings) lives on the user's machine.

```
┌─────────────────────────────  Browser (vanilla JS)  ─────────────────────────────┐
│  Splash → Workspaces (MDT / Trainer / Demo) → Chat UI → Settings modal           │
│  localStorage: settings (model, prompts, tools) · session preferences            │
└────────────────────────────────────┬─────────────────────────────────────────────┘
                                     │ JSON over HTTP (127.0.0.1:8765)
┌────────────────────────────────────▼─────────────────────────────────────────────┐
│  server.py (stdlib http.server)                                                  │
│  ├─ /api/step, /api/ask        consultation engine (auto / human-doctor)         │
│  ├─ /api/mdt/clarify, /api/mdt MDT pipeline                                      │
│  ├─ /api/library/*             document library (upload / list / delete / read)  │
│  ├─ /api/search                RAG keyword retrieval                             │
│  ├─ /api/sessions/*            consultation memory                               │
│  ├─ /api/prompts/*             prompt pool                                       │
│  └─ static web/                                                                  │
└───────┬───────────────────┬────────────────────┬─────────────────────────────────┘
        │                   │                    │
┌───────▼──────┐   ┌────────▼────────┐   ┌───────▼──────────────────────┐
│ app/engine.py│   │ app/mdt.py      │   │ app/llm.py (streaming bridge) │
│ auto/human   │   │ summarize→      │   │ openai 0.28, any compatible   │
│ consultation │   │ retrieve→discuss│   │ endpoint; think-block strip   │
└──────────────┘   │ →report         │   └──────────────────────────────┘
                   └────────┬────────┘
        ┌───────────────────┼──────────────────────────────┐
┌───────▼───────┐  ┌────────▼───────┐  ┌─────────┐  ┌──────▼──────┐
│ app/rag.py    │  │ app/tools.py   │  │sessions │  │ prompts.py  │
│ chunk index + │  │ MAP/BMI/CrCl   │  │ memory  │  │ prompt pool │
│ retrieval     │  │ calculators    │  │ .py     │  │             │
└───────┬───────┘  └────────────────┘  └─────────┘  └─────────────┘
        │ library/documents/*  library/chunks.json  library/sessions.json
        │ library/prompts.json          ← all local, all gitignored
```

## The MDT pipeline

1. **Clarify** — pre-consultation assistant asks 2–3 focused questions (LLM or rule-based).
2. **Summarize** — intake is structured into a clinical summary.
3. **Retrieve (tool)** — chunks from the document library most relevant to the case are
   injected as "reference material"; specialists are instructed to ground every claim.
4. **Discuss** — each selected specialist gives an independent opinion (round 1), then
   responds to the others (round 2).
5. **Calculate (tool)** — deterministic medical calculations are detected and appended.
6. **Report** — the moderator synthesizes a structured JSON report (tendency / confidence /
   recommended department / findings / plan / red flags / disagreements / warnings).

## Agent capability matrix

| Capability | Module | Persisted at |
|---|---|---|
| Multi-role agents | engine / mdt / mockllm | — |
| Prompt pool | prompts.py | library/prompts.json |
| Document library + RAG | library.py + rag.py | library/documents/, chunks.json |
| Medical calculators | tools.py | — (deterministic) |
| Session memory | sessions.py | library/sessions.json |
| Sandbox controls | settings in frontend | browser localStorage |
| Server defaults | config.py | config.json (gitignored) |

## Design constraints

- **Local-first**: the only network calls go to the LLM provider you configure.
- **Streaming**: some relays hang on non-streamed completions, so `llm.py` always streams.
- **Grounding**: specialists and the report prompt carry an explicit
  "do not fabricate data not present in the reference material" instruction.
- **Non-medical-device**: every user-facing surface keeps the reference-only disclaimer.
