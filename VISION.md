# Vision

Whisper Local is a private, local-first workspace for turning recordings into useful text. It should feel like a focused desktop tool in the browser: fast to open, clear to operate, and trustworthy with personal audio.

## Product Direction

- Keep transcription, playback, transcripts, summaries, and exported text in one coherent workflow.
- Treat local privacy as a core feature. Audio and generated text should stay inside the project data directory unless the user explicitly exports them.
- Make transcript review efficient: segment playback, search, rename, delete, copy, download, and summary refresh should stay quick and predictable.
- Support German well by default while keeping the architecture open for additional languages.
- Prefer useful summaries over clever summaries. If the local model fails or produces weak output, the app should fall back gracefully.

## Engineering Principles

- Keep the app easy to run locally with minimal setup.
- Separate web routes, persistence, transcription, and summarization as the code grows.
- Validate inputs at boundaries and normalize settings in one place.
- Avoid hidden data mutations during read paths unless there is a deliberate migration step.
- Protect user data files from accidental churn in normal development.
- Add focused tests around pure logic first: settings normalization, title cleanup, summary parsing, and library persistence.

## Near-Term Refactor Targets

- Split `app.py` into small modules for routes, records/storage, transcription, and summarization.
- Add a lightweight test suite for pure functions before changing behavior.
- Make library loading tolerant of malformed records and settings files.
- Move data migrations out of `load_library()` so page loads do not unexpectedly rewrite `data/library.json`.
- Add clear error states for missing dependencies, failed model downloads, invalid uploads, and missing audio files.
- Consider background jobs for transcription and summarization so long-running requests do not block the web server.

## Non-Goals For Now

- Cloud transcription or hosted storage.
- Multi-user accounts.
- Heavy database infrastructure before JSON persistence becomes a real limitation.
- A large framework rewrite unless the app outgrows the current Flask shape.
