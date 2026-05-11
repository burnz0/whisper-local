# TODO

Prioritized backlog from the expert UX/product review. Product direction: a calm, local-first workspace for turning conversations into searchable knowledge.

## Current Scope Notes

- Desktop browser layouts are the current product target.
- Mobile layout polish is intentionally deferred; avoid treating mobile-only issues as blockers unless they break desktop/tablet behavior.

## P0 - Layout Hierarchy

- [x] Move upload/model controls out of the permanent workspace column.
- [x] Make transcript review the dominant default workspace.
- [x] Add a command-palette or keyboard-accessible quick action for new transcripts.
- [ ] Make the context panel reusable for export, metadata, and model settings.

## P0 - State Design

- [x] Improve empty state for no transcript selected.
- [x] Add full-app drag/drop target state for audio ingest.
- [x] Add visible local-first processing copy during upload/transcription.
- [ ] Design model download state with progress, size, ETA, storage needs, cancel, retry.
- [ ] Design richer transcribing state with active model, CPU/GPU status, progress stages, estimated duration.
- [ ] Design summary generation states: generating, retrying, fallback, failed, local model used.
- [ ] Add specific failure states for missing FFmpeg, CUDA unavailable, corrupted audio, unsupported format, missing model.

## P1 - Transcript Review

- [x] Keep active segment highlighting and follow playback mode.
- [x] Add follow-playback toggle.
- [ ] Add current segment emphasis in the player.
- [ ] Add waveform seeking backed by real audio data or transcript timing.
- [ ] Improve segment edit flow beyond browser prompts.
- [ ] Add compact transcript density controls.

## P1 - Search

- [x] Highlight transcript hits and show hit count.
- [ ] Add previous/next hit navigation.
- [ ] Add transcript-only vs summary search scope.
- [ ] Add speaker/tag filters once speaker data exists.
- [ ] Explore semantic search for local knowledge retrieval.

## P1 - Local-First Trust

- [x] Surface "runs locally" and "no cloud upload" in ingest flow.
- [x] Keep local storage reassurance in persistent sidebar.
- [ ] Show storage path, model location, cache size, disk usage, export path in settings.
- [ ] Add delete local data controls.
- [ ] Show active model and CPU/GPU processing mode during jobs.

## P2 - Design System

- [x] Reduce upload glow dominance by moving ingest to contextual UI.
- [ ] Continue reducing broad glow/gradient usage toward matte, precise surfaces.
- [ ] Standardize spacing on 4/8/12/16/24/32px tokens throughout.
- [ ] Strengthen typography hierarchy for transcript, metadata, timestamps, and controls.
- [ ] Reduce corner-radius uniformity by role.
- [ ] Strengthen hover, selected, playing, focused, and active states.

## P2 - Knowledge Workspace Evolution

- [x] Support persistent transcripts, tags, summary, exports, and segment edits.
- [ ] Add folders or collections.
- [ ] Add bookmarks and highlights.
- [ ] Add linked notes.
- [ ] Add speaker labeling.
- [ ] Add AI extraction for action items and entities.
