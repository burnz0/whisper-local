# Knowledge Storage Direction

## Current Decision

Keep the primary library JSON-backed for now. The app is local, single-user, and the existing import/export paths are simple and useful. Semantic search should start as an additive sidecar rather than a SQLite migration.

## Semantic Search Plan

- Embedding model: `intfloat/multilingual-e5-small`.
- Scope: transcript segments, transcript-level notes, and generated summaries.
- Storage: `data/search-index.json` sidecar keyed by record id and segment id.
- Refresh strategy: rebuild changed records after transcription, segment edits, notes edits, or summary refresh.
- Query path: embed the query locally, compare cosine similarity against sidecar vectors, and show matching transcript segments plus source transcript metadata.

This keeps the current `data/library.json`, transcript text downloads, Markdown export, and JSON export stable while allowing semantic search to be added without a schema migration.

## SQLite Trigger

Move to SQLite only when at least one of these becomes true:

- JSON write contention or corruption becomes a recurring issue.
- Search/index rebuilds become too slow for a normal local library.
- We need cross-record joins for speakers, entities, action items, collections, or notes.
- We need reliable partial updates for concurrent background analysis jobs.

## SQLite Shape If Needed

- `transcripts`: id, title, source filename, stored filename, transcript filename, created_at, model, language, duration, collection, notes.
- `segments`: transcript_id, segment_id, start, end, text, speaker, bookmarked, highlighted.
- `summaries`: transcript_id, provider, created_at, density, text.
- `tags`: name.
- `transcript_tags`: transcript_id, tag.
- `entities`: transcript_id, segment_id, label, kind, confidence.
- `action_items`: transcript_id, segment_id, text, owner, due_at, status.
- `embeddings`: scope, owner id, model, vector, updated_at.

## Import And Export

The existing JSON library remains the migration source of truth. A SQLite migration should preserve:

- `/downloads/<record_id>.txt`
- `/downloads/<record_id>.clean.txt`
- `/downloads/<record_id>.md`
- `/downloads/<record_id>.json`
- the current `data/library.json` export shape as a compatibility export.
