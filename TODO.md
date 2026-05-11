# TODO

Prioritized backlog based on the current app, screenshot review, and `VISION.md`.

## P1 - Make Daily Use Faster

- [ ] Add a visible transcription progress state.
  - Disable the form while transcription is running.
  - Show a loading indicator and the selected file name.
  - Prevent double-submit.
- [ ] Preserve the selected sidebar panel.
  - If the user opens Settings, keep Settings active after saving.
- [ ] Add empty and loading states for summaries.
  - Show when a summary is being refreshed.
  - Show a useful fallback message when generation fails.
- [ ] Improve transcript search.
  - Show match count.
  - Highlight matched text inside segments.
  - Keep active audio segment visible while filtering is off.
- [ ] Add keyboard shortcuts for review.
  - Space toggles play/pause.
  - Arrow keys seek.
  - `/` focuses search.

## P2 - UI Polish From Screenshot Review

- [ ] Reduce visual weight in the left upload panel once a transcript is selected.
  - Make "Add audio" more compact.
  - Keep the transcript review area dominant.
- [ ] Improve long title handling in the history sidebar.
  - Clamp titles consistently.
  - Add full title on hover.
  - Consider a denser list mode.
- [ ] Replace text/symbol buttons with clearer icons and accessible labels.
  - Rename, download, copy, delete, play, and close actions.
  - Keep visible tooltips for ambiguous controls.
- [ ] Make the bottom player feel connected to the active transcript.
  - Ensure active segment scrolls into view during playback.
  - Show current segment text or title near the player on narrow screens.
- [ ] Tighten responsive behavior.
  - Check desktop, tablet, and mobile layouts.
  - Make sure the fixed-height shell does not trap content on small screens.

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
