# TODO

Prioritized backlog based on the current app, screenshot review, and `VISION.md`.

## P3 - Architecture And Maintainability

- [ ] Split `app.py` into focused modules.
  - `routes.py` for Flask routes.
  - `storage.py` for records, settings, and migrations.
  - `transcription.py` for Whisper model loading and transcription.
  - `summaries.py` for local model and extractive summarization.
- [ ] Add a background job path for long-running work.
  - Start with an in-process job registry.
  - Return job status to the UI while transcription runs.
- [ ] Add structured logging.
  - Log transcription start/end, summary provider fallback, and recoverable local-data errors.
- [ ] Add dependency checks at startup.
  - Verify Whisper import, ffmpeg availability, and optional Transformers support.
- [ ] Consider SQLite only when JSON becomes a real limitation.
  - Keep JSON while the app is single-user and local-first.

## P4 - Product Enhancements

- [ ] Add transcript editing.
  - Edit segment text.
  - Re-export corrected transcript.
- [ ] Add tags or lightweight collections.
  - Keep it local and file-backed at first.
- [ ] Add export formats.
  - Plain text.
  - Markdown with timestamps.
  - JSON with segments.
- [ ] Add language/model hints.
  - Explain model speed/quality tradeoffs in settings.
  - Keep defaults simple.
- [ ] Add optional transcript cleanup.
  - Remove filler words.
  - Normalize punctuation.
  - Keep the original transcript available.
