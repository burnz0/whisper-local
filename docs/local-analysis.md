# Local Analysis Provider Boundary

## Decision

Local analysis is separate from transcription. Transcription produces text, segments, timing, and backend metadata. Analysis consumes transcript text plus metadata and may produce:

- summaries
- generated titles
- action items
- entities
- future semantic-search index updates

## Current Providers

- `extractive`: deterministic fallback; always safe to run during ingestion.
- `local_instruction_quality`: Qwen quality path for explicit summary refresh.
- `local_instruction`: Qwen fast path for background title generation.
- `local_transformer`: legacy German mT5 path; kept only as an experimental baseline.

## Runtime Rules

- Ingestion must not block on heavyweight analysis.
- New transcripts get an extractive placeholder summary.
- Background title generation uses the fast instruction model.
- Manual summary refresh can use the quality instruction model.
- Every generative provider must fall back to extractive output when the model is unavailable or fails quality checks.

## Next Extraction Shape

Action items:

- `text`
- `owner`
- `due_at`
- `status`
- `segment_id`

Entities:

- `text`
- `kind`
- `segment_id`
- `confidence`

These should be stored additively so old JSON libraries still load without migration.
