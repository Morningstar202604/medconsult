# Security Policy

## Scope

MedConsult is a local-first research platform: it stores everything on your machine and only talks to the LLM provider you configure. Please read `docs/ARCHITECTURE.md` for the data-flow overview.

## Reporting a vulnerability

If you find a security issue (for example, a secret leaking into the repository or the HTTP server), please open a GitHub issue or contact the maintainers privately. We aim to respond within one week.

## Safe defaults

- API keys live in `config.json` (gitignored) or your browser's localStorage — never in the repository.
- The HTTP server binds to `127.0.0.1` only. Do not expose it publicly without authentication.
- Uploaded patient documents are stored unencrypted in `library/`. If you handle real patient data, use disk encryption and follow your local data-protection laws.
