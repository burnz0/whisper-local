# Whisper Local

Local Flask app for audio transcription with Whisper.

## Features

- Upload audio and transcribe it locally
- Dark UI based on `ui.png`
- Persistent history in `data/library.json`
- Saved audio files in `data/uploads/`
- Saved text downloads in `data/transcripts/`
- Segment-based transcript view with timestamps
- Local audio playback, search, rename, copy, download

## Repo layout

```text
whisper-local/
  app.py
  requirements.txt
  templates/
  static/
  data/
```

## Run

```bash
make run
```

The local target is Python 3.11 or 3.12. Create a repo-local environment and install the core app plus local ML extras:

```bash
PYTHON=python3.12 make install
```

Then run:

```bash
make run
```

This starts the app on `http://127.0.0.1:8765`.

You can override the local environment or port:

```bash
VENV=/path/to/venv PORT=8766 make run
```

Or run the app directly:

```bash
.venv/bin/python /Users/burnz0/workspace/pocs/whisper-local/app.py
```

Or:

```bash
cd /Users/burnz0/workspace/pocs/whisper-local
.venv/bin/flask --app app run --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

## Notes

- `requirements-core.txt` contains the web app dependency; `requirements-ml.txt` contains local transcription and analysis dependencies.
- Local transcript history and settings live in `data/library.json` and `data/settings.json`; these files are ignored by git.
- If old local records need metadata backfilled, run `make migrate`.
- To check local runtime dependencies, run `make deps`.
- To benchmark the baseline backend on a representative file, run `make benchmark AUDIO=/path/to/audio.ogg MODEL=small LANGUAGE=de`.
- Persistence intentionally stays JSON-backed while the app is single-user and local-first; SQLite can wait until JSON becomes a real limitation.
- Default language is German.
- New transcripts save quickly with an extractive placeholder summary; Qwen only runs when a summary/title job is requested.
- Default manual summary provider is the quality local Qwen model (`Qwen/Qwen3-1.7B`).
- Background auto-title generation uses the faster Qwen model (`Qwen/Qwen3-0.6B`).
- Override models with `QUALITY_INSTRUCTION_MODEL_NAME=...` or `FAST_INSTRUCTION_MODEL_NAME=...`.
- Queued transcription jobs can be canceled before they start; active OpenAI Whisper jobs cannot be interrupted safely.
- Active transcription backend: OpenAI Whisper. Supported models are discovered from the installed backend and include `turbo` when the installed package supports it.
- Supported file types: `.ogg`, `.mp3`, `.m4a`, `.wav`, `.mp4`, `.mpeg`, `.webm`, `.aac`, `.flac`.
