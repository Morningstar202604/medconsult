## Working rules for this repository

* Dependency updates: search the whole repository for every occurrence of a dependency (build files, lockfiles, CI workflows, docs) before bumping. A partial bump — declaration updated but lockfile or a pinned action left behind — is the most common cause of "works locally, CI fails". Keep lockfiles in the same commit as the declaration. Move version-coupled toolchain upgrades together in one commit.
* Refactoring: pull latest main first, work on a fresh branch, keep commits atomic with messages that state the why, and always run the full check suite before pushing (for this repo: `cd backend && pytest`). A branch left behind main cannot be merged under the repository's branch protection.
* Merge conflicts: resolve conflicts in the working tree against the latest main; never force-push shared branches; never resolve a conflict by blindly taking either side — re-read both sides and keep both changes when they are both valid.
* Versioning: releases follow X.Y.Z starting at 0.0.0. Last digit = fixes, middle digit = feature work, first digit stays 0 until a stable release is declared. Bump the version in code, CHANGELOG.md and the tag in the same change.

---

# Contributing to MedConsult

Thanks for your interest in improving MedConsult! 🎉

## How to help

- **Bug reports** — open an issue with steps to reproduce, expected vs actual behavior, and your environment (OS / Python / model provider).
- **Feature proposals** — open an issue first so we can align on the design (especially for clinical-safety-related features).
- **Pull requests** — fork, create a feature branch, keep changes focused, and make sure `python -m compileall app server.py` passes.

## Development setup

```bash
git clone https://github.com/Morningstar202604/medconsult.git
cd medconsult
python -m venv .venv
.venv/Scripts/python -m venv .venv      # Windows
.venv/bin/python -m venv .venv          # Linux/macOS (use the line above on Windows)
pip install -r requirements.txt
python server.py                        # http://127.0.0.1:8765
```

## Ground rules

1. **Clinical safety first** — the platform outputs reference information only.
   Never add features that present AI output as a definitive diagnosis or
   prescription. Keep disclaimers intact.
2. **Data stays local** — no telemetry, no cloud calls except the LLM provider
   you configure. Any new feature must keep patient data on the user's machine.
3. **No secrets in the repo** — API keys live in `config.json` (gitignored) or
   browser localStorage only.
4. Python standard library first — avoid adding web frameworks or heavy
   dependencies unless there is a strong reason.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License that covers this repository.
