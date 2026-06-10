# Contributing to meeting-scribe

Thanks for your interest in improving meeting-scribe. Contributions of all
sizes are welcome — bug reports, docs, and code.

## Ground rules

- **Never commit private data.** No real recordings, transcripts, summaries,
  API keys, or personal/voice data. The `.gitignore` already excludes `.env`,
  `meetings/`, `voice_samples/`, `output/`, and the real `config/*.yaml`. Only
  the `*.example` templates are tracked — keep it that way.
- Be respectful in issues and pull requests.

## Getting set up

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg

cp .env.example .env                                  # add OPENAI_API_KEY, HF_TOKEN
cp config/config.example.yaml   config/config.yaml
cp config/meetings.example.yaml config/meetings.yaml
cp config/partners.example.yaml config/partners.yaml
```

See the [README](README.md) for full setup and usage.

## Reporting bugs

Open an issue with:
- what you ran (command, OS, Python version),
- what you expected vs. what happened,
- relevant logs (with any names, keys, or transcript content removed).

## Pull requests

1. Fork and create a branch off `main`: `git checkout -b fix/short-description`.
2. Keep changes focused — one logical change per PR.
3. Match the style of the surrounding code; keep functions small and readable.
4. If you change behavior, update the README.
5. Confirm no secrets or private data are staged before pushing:
   ```bash
   git diff --cached --name-only
   ```
6. Open the PR against `main` with a clear description of what and why.

## Third-party model terms

This project is Apache-2.0, but it depends on models with their own licenses —
notably the gated pyannote diarization models on Hugging Face. Contributions
must not bundle those models or assume rights their terms do not grant. See
[NOTICE](NOTICE).

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
