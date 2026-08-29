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
