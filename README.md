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

This uses `/Users/burnz0/.transcribe-venv` by default and starts the app on `http://127.0.0.1:8765`.

You can override the local environment or port:

```bash
VENV=/path/to/venv PORT=8766 make run
```

Or run the app directly:

```bash
/Users/burnz0/.transcribe-venv/bin/python /Users/burnz0/workspace/pocs/whisper-local/app.py
```

Or:

```bash
cd /Users/burnz0/workspace/pocs/whisper-local
/Users/burnz0/.transcribe-venv/bin/flask --app app run --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

## Notes

- Uses the existing local Whisper environment at `/Users/burnz0/.transcribe-venv`.
- Local transcript history and settings live in `data/library.json` and `data/settings.json`; these files are ignored by git.
- If old local records need metadata backfilled, run `make migrate`.
- Default language is German.
- Supported models: `tiny`, `base`, `small`.
- Supported file types: `.ogg`, `.mp3`, `.m4a`, `.wav`, `.mp4`, `.mpeg`, `.webm`, `.aac`, `.flac`.
