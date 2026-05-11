# TODO

Fresh technical backlog from the May 2026 stack review. Product direction remains a calm, local-first workspace for turning conversations into searchable knowledge.

## Current Scope Notes

- Desktop browser layouts are the current product target.
- Mobile layout polish is intentionally deferred; avoid treating mobile-only issues as blockers unless they break desktop/tablet behavior.
- Keep the app local-first by default. Any cloud-backed option must be explicit, opt-in, and clearly labeled.

## P0 - Runtime And Dependency Health

- [x] Upgrade the local development/runtime target from Python 3.9 to Python 3.11 or 3.12.
- [x] Replace the implicit `/Users/burnz0/.transcribe-venv` assumption with documented environment setup.
- [x] Pin core runtime dependencies and split optional ML dependencies into explicit extras or install groups.
- [x] Add a startup dependency report that distinguishes required, optional, installed, missing, and unsupported components.
- [x] Make processing mode labels truthful: only show Metal/CUDA when the active transcription backend actually uses it.

## P0 - Transcription Backend

- [x] Introduce a transcription backend interface so model loading, transcription, timing, and errors are backend-specific.
- [x] Keep `openai-whisper` as the baseline backend until replacements are benchmarked.
- [ ] Benchmark `faster-whisper` for local CPU/GPU performance, memory use, model download size, and transcript quality.
- [ ] Benchmark `whisper.cpp` for Apple Silicon/CPU performance, quantized models, install friction, and integration cost.
- [x] Add `turbo` as an optional Whisper model tier if the selected backend supports it cleanly.
- [ ] Revisit default model choice after benchmarking `small`, `medium`, and `turbo` on representative German and English audio.

## P1 - Local Analysis And Summaries

- [ ] Create a local analysis provider interface separate from transcription.
- [x] Treat the current German mT5 summarizer as an optional baseline, not the long-term product bet.
- [x] Benchmark local instruction models for summaries, action items, entities, and title generation.
- [x] Keep extractive summaries as a reliable fallback path.
- [ ] Add AI extraction for action items and entities once the provider boundary is in place.

## P1 - Search And Knowledge Storage

- [ ] Explore semantic search for local knowledge retrieval.
- [ ] Choose a local embedding model and storage strategy for transcript segments and notes.
- [ ] Decide whether semantic search is enough on JSON or whether it should trigger a SQLite migration.
- [ ] If migrating to SQLite, model transcripts, segments, tags, collections, notes, speakers, summaries, and extracted entities explicitly.
- [ ] Preserve import/export paths so existing JSON-backed libraries can migrate safely.

## P2 - Product Architecture

- [ ] Make the context panel reusable for export, metadata, ingest, and model settings.
- [x] Add backend/model capability metadata to the UI so unsupported combinations are hidden or clearly disabled.
- [x] Add cancellation semantics for queued jobs and document which backends can cancel active transcription.
- [x] Add lightweight benchmark fixtures and commands for comparing transcription backends.
