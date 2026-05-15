# TODO

Product direction: keep Whisper Local a calm, local-first desktop browser workspace for turning recordings into searchable knowledge.

## Current Decisions

- Desktop browser layouts are the current product target. Mobile polish is deferred unless it breaks desktop or tablet behavior.
- Cloud transcription, hosted storage, and multi-user collaboration are out of scope unless they become explicit opt-in features.
- JSON remains the primary library store while the app is local and single-user. Revisit SQLite only if contention, corruption risk, slow search rebuilds, joins, or reliable partial updates become real problems.
- Analysis stays separate from transcription. Ingestion should persist quickly with an extractive fallback; local instruction models can run for manual summaries, titles, action items, and entities.
- Semantic search should start as an additive sidecar over the JSON library, likely `data/search-index.json` with `intfloat/multilingual-e5-small`.
- OpenAI Whisper remains the production baseline. The 2026-05-14 benchmark points to `whisper.cpp` plus `base` as the next backend experiment, not the default yet.
- Keep Flask plus vanilla HTML/CSS/JS for now. The UI is a local single-user workspace, so a frontend build chain or SPA framework would add more maintenance than value today.
- Keep local ML dependencies split from the core Flask dependency. Do not make Qwen, mT5, faster-whisper, or whisper.cpp mandatory for starting the app.
- Hold `transformers` on the 4.x line until the Qwen and mT5 paths are smoke-tested on 5.x. The package has a newer major version, but this app uses direct model/tokenizer APIs that should not be upgraded blindly.
- Avoid adding SQLite, SQLAlchemy, Celery, Redis, Docker, or cloud services until there is a measured local limitation that justifies them.

## P0 - Transcription Backend

- [x] Build a production `whisper.cpp` backend adapter with model path validation, model download/setup guidance, timing, errors, and capability metadata.
- [ ] Expand the benchmark corpus across German and English audio, including short, long, noisy, conversational, and cleaner samples.
- [ ] Compare `tiny`, `base`, `small`, `medium`, and `turbo` where supported before changing the default backend or model.
- [x] Add atomic JSON writes and file locking around library/settings writes that can race with background jobs or UI edits.

## P1 - Local Analysis And Knowledge

- [x] Add durable background analysis job state for titles, summaries, action items, and entities.
- [x] Add AI extraction for action items and entities behind the analysis provider boundary.
- [ ] Implement the semantic search sidecar for transcript segments, notes, and summaries.
- [x] Add a small local-model smoke test script for Qwen title/summary generation before upgrading `transformers` to 5.x.
- [ ] Preserve import/export paths so existing JSON-backed libraries can migrate safely if SQLite becomes necessary.

## P2 - Product Architecture

- [ ] Make the context panel reusable for export, metadata, ingest, and model settings.
- [ ] Keep desktop/tablet layout polish focused on dense transcript review rather than marketing-style presentation.
- [ ] Add small benchmark fixtures or documented sample expectations so backend comparisons are repeatable without private audio.
- [ ] Add lightweight Python project metadata and dev tooling only when it starts paying for itself, likely `pyproject.toml` plus Ruff for formatting/import checks.

## Done Recently

- [x] Upgraded the local development/runtime target from Python 3.9 to Python 3.11 or 3.12.
- [x] Replaced the implicit `/Users/burnz0/.transcribe-venv` assumption with documented environment setup.
- [x] Split core web dependencies from optional local ML dependencies.
- [x] Added a startup dependency report for required, optional, installed, missing, and unsupported components.
- [x] Made processing mode labels truthful for the active backend.
- [x] Introduced a transcription backend interface.
- [x] Benchmarked OpenAI Whisper, faster-whisper, and whisper.cpp on a local German sample.
- [x] Added `turbo` as an optional Whisper model tier when supported by the selected backend.
- [x] Created a local analysis provider interface separate from transcription.
- [x] Kept extractive summaries as the reliable fallback path.
- [x] Added backend/model capability metadata to the UI.
- [x] Added queued-job cancellation semantics and documented active backend cancellation limits.
- [x] Added lightweight benchmark commands for comparing transcription backends.
- [x] Added atomic JSON writes and file locking for local library/settings persistence.
- [x] Added an opt-in production `whisper.cpp` backend adapter.
- [x] Added `medium` to the supported Whisper model tiers and default benchmark matrix.
- [x] Added durable JSON-backed analysis job state for local background analysis.
- [x] Added a Qwen local analysis smoke-test command.
- [x] Added action-item and entity extraction behind the local analysis provider boundary.
