# Bug Tickets From Playwright QA

Tested on 2026-05-12 against `http://127.0.0.1:8765` with Playwright. Screenshots are in `output/playwright/` and are intentionally ignored by git.

## BUG-001: Settings view is rendered inside the narrow sidebar

Priority: P0

Observed:

- Clicking `Settings` replaces the history list with app settings inside the left sidebar.
- Controls are clipped horizontally and vertically.
- The main transcript remains active, so the page reads as both "settings" and "current transcript" at the same time.
- At 1024px width, settings are partially hidden and the local data section is not usable.

Evidence:

- `output/playwright/settings-sidebar.png`
- `output/playwright/narrow-desktop.png`

Acceptance criteria:

- Settings render in the main content area or a dedicated full-height panel wide enough for form controls and local data.
- Sidebar navigation state and main content state cannot conflict.
- At 1024px desktop width, all settings controls and destructive actions are reachable without clipping.

## BUG-002: Add-audio drawer stacks over stale settings state

Priority: P1

Observed:

- Opening `New Transcription` while Settings is active keeps the settings sidebar open.
- The upload drawer opens on the right while the old transcript and settings remain visible underneath.
- The result is visually overloaded and hard to understand; there are three competing contexts on screen.

Evidence:

- `output/playwright/add-audio-over-settings.png`

Acceptance criteria:

- Opening the ingest drawer closes or suspends conflicting panels such as Settings.
- Background content is dimmed/inert consistently.
- Focus is trapped inside the drawer until it is closed.

## BUG-003: Running jobs show a queued-cancel action

Priority: P0

Observed:

- After submitting an audio file, the job banner showed stage `Transcribing`.
- The same banner still displayed `Cancel queued job`.
- Backend metadata says active OpenAI Whisper jobs cannot be cancelled, so the visible action is misleading.

Acceptance criteria:

- `Cancel queued job` is visible only while `job.can_cancel` is true.
- Running active jobs show either no cancel control or a disabled explanatory state.
- Clicking an unavailable cancel action is impossible; users should not hit a 409 for normal UI behavior.

## BUG-004: Generated transcript title can be hallucinated nonsense

Priority: P0

Observed:

- A new German transcription using `tiny` generated the title `Jugendermens Zünnschneuer`.
- The title starts with a capital letter but is not a usable title.
- It appears to amplify transcription errors instead of falling back to a safer title.

Acceptance criteria:

- Titles must be a short, human-readable sentence or phrase derived from validated summary content.
- Reject titles made mostly of low-confidence, rare, or unknown terms.
- If validation fails, use a safe fallback such as date plus source filename until a better model/title job succeeds.

## BUG-005: Extractive summary turns ASR errors into nonsense

Priority: P0

Observed:

- The generated summary for the same transcript was `Es geht um Jugendermens, Zünnschneuer sowie Kanarein.`
- This is worse than no summary because it presents ASR artifacts as the main topics.
- The UI labels it `Reliable extractive`, which overstates quality for this case.

Acceptance criteria:

- Extractive fallback must not summarize by selecting isolated hallucinated capitalized words.
- If confidence/quality checks fail, show `Summary pending` or a neutral fallback instead of nonsense.
- Summary density settings must influence the final amount of text for every provider path.

## BUG-006: Bottom audio player blocks content and actions

Priority: P1

Observed:

- The persistent bottom player consumes a large amount of vertical space.
- At 1024px width, the `Save notes` button is partially hidden behind the player.
- Transcript, text, summary, and notes panels do not reserve enough bottom padding for the player.

Evidence:

- `output/playwright/narrow-desktop.png`

Acceptance criteria:

- Main panel content reserves enough bottom space for the player.
- Form actions such as `Save notes` remain fully visible and clickable.
- At 1024px desktop width, the player uses a compact layout or can collapse.

## BUG-007: Header action toolbar wraps poorly on narrower desktop

Priority: P2

Observed:

- At 1024px width, transcript action icons wrap into multiple rows.
- The title, metadata chips, collection/tags forms, and actions compete for the same header area.
- The result feels crowded and makes primary actions harder to scan.

Evidence:

- `output/playwright/narrow-desktop.png`

Acceptance criteria:

- Header metadata, edit controls, and export/delete actions use stable responsive regions.
- Icon buttons do not wrap into a floating cluster detached from their transcript context.
- Long titles truncate gracefully with full text available on hover or edit.

## BUG-008: Sidebar transcript cards are too cramped for generated titles

Priority: P2

Observed:

- The recent transcript card truncates generated titles aggressively.
- The delete `x` appears detached from the selected card.
- The active transcript title and metadata are hard to scan in the sidebar.

Evidence:

- `output/playwright/home-desktop.png`

Acceptance criteria:

- Sidebar cards support two-line titles without awkward clipping.
- Destructive controls are visually attached to the card they affect.
- The active transcript remains scannable with title, collection, duration, and language visible.

## BUG-009: Missing favicon produces a console error on every load

Priority: P3

Observed:

- Browser console reports `GET /favicon.ico 404`.

Acceptance criteria:

- Add a favicon route or static asset.
- Fresh page load has no console errors.

