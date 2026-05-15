# Whisper Local

Private local-first Flask workspace for turning audio recordings into searchable transcripts, summaries, notes, and exports. German is the default language, and runtime data stays under `data/` unless the user exports it.

## What It Does

- Upload one or more audio files and queue local transcription jobs.
- Store transcript history in `data/library.json`, with audio in `data/uploads/` and downloads in `data/transcripts/`.
- Persist background analysis job state in `data/analysis-jobs.json`.
- Review segment-based transcripts with timestamps, search, rename, delete, copy, download, and local audio playback.
- Generate local summaries and titles through a separate analysis provider boundary.
- Keep extractive summaries as the safe fallback when generative local models are unavailable or fail.
- Show backend/model capability metadata so unsupported transcription combinations are hidden or disabled.
- Cancel queued transcription jobs before they start. Active OpenAI Whisper jobs cannot be interrupted safely.

Supported upload types: `.opus`, `.oga`, `.ogg`, `.mp3`, `.m4a`, `.wav`, `.mp4`, `.mpeg`, `.webm`, `.aac`, `.flac`.

## Run Locally

The local target is Python 3.11 or 3.12. Create a repo-local environment and install the core app plus local ML extras:

```bash
PYTHON=python3.12 make install
```

Then run:

```bash
make run
```

This starts the app on `http://127.0.0.1:8765`.

You can override the local environment or port:

```bash
VENV=/path/to/venv PORT=8766 make run
```

Or run the app directly:

```bash
.venv/bin/python /Users/burnz0/workspace/pocs/whisper-local/app.py
```

Or:

```bash
cd /Users/burnz0/workspace/pocs/whisper-local
.venv/bin/flask --app app run --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

## Common Commands

```bash
make run
make test
make deps
make migrate
make benchmark AUDIO=/path/to/audio.ogg LANGUAGE=de EXPECTED_TERMS=Festival,Lagerhallen
make smoke-analysis
```

The benchmark command reports timing, realtime factor, expected-term coverage, candidate backend availability, and a recommendation. Include whisper.cpp with:

```bash
WHISPER_CPP_MODEL=/path/to/ggml-base.bin make benchmark AUDIO=/path/to/audio.ogg MODELS=base LANGUAGE=de
```

## Transcription Backends

OpenAI Whisper remains the default production backend:

```bash
make run
```

`whisper.cpp` is available as an opt-in backend when `whisper-cli` is installed and a real GGML model path is configured:

```bash
TRANSCRIPTION_BACKEND=whisper.cpp WHISPER_CPP_MODEL=/path/to/ggml-base.bin make run
```

Or point at a directory containing files named `ggml-tiny.bin`, `ggml-base.bin`, `ggml-small.bin`, `ggml-medium.bin`, `ggml-turbo.bin`, and so on:

```bash
TRANSCRIPTION_BACKEND=whisper.cpp WHISPER_CPP_MODEL_DIR=/path/to/whisper-cpp-models make run
```

Native whisper.cpp inputs are `flac`, `mp3`, `ogg`, and `wav`; other supported upload formats are converted through `ffmpeg` before transcription. The settings panel reports the active backend, supported models, model paths, setup guidance, and active-job cancellation capability.

## Repo Layout

```text
whisper-local/
  app.py                 Flask entrypoint
  routes.py              HTTP routes and request handling
  storage.py             JSON-backed library and settings persistence
  transcription.py       Transcription backend interface and implementations
  analysis.py            Local analysis provider interface
  analysis_jobs.py       Durable local analysis job state
  scripts/               Local smoke-test helpers
  summaries.py           Summary helpers and fallback behavior
  benchmarks.py          Backend benchmark runner
  templates/             Flask templates
  static/                Browser UI assets
  data/                  Ignored local runtime data and examples
  tests/                 Backend tests
```

## Architecture Notes

- `requirements-core.txt` contains the web app dependency; `requirements-ml.txt` contains local transcription and analysis dependencies.
- Local transcript history, settings, and durable analysis job state live in `data/library.json`, `data/settings.json`, and `data/analysis-jobs.json`; these files are ignored by git.
- If old local records need metadata backfilled, run `make migrate`.
- To check local runtime dependencies, run `make deps`.
- Persistence intentionally stays JSON-backed while the app is single-user and local-first. Consider SQLite only when contention, corruption risk, slow sidecar rebuilds, cross-record joins, or reliable partial updates become real limitations.
- Semantic search should start as an additive sidecar such as `data/search-index.json`, likely using `intfloat/multilingual-e5-small` over transcript segments, notes, and summaries.
- Transcription and analysis are intentionally separate. Ingestion should stay fast and safe; heavier analysis can run on demand or in background jobs.
- New transcripts save quickly with an extractive placeholder summary; Qwen only runs when a summary/title job is requested.
- Default manual summary provider is the quality local Qwen model (`Qwen/Qwen3-1.7B`).
- Background auto-title generation uses the faster Qwen model (`Qwen/Qwen3-0.6B`).
- Override models with `QUALITY_INSTRUCTION_MODEL_NAME=...` or `FAST_INSTRUCTION_MODEL_NAME=...`.
- Before upgrading `transformers`, run `make smoke-analysis` to verify Qwen title and summary generation still work with the local model APIs.
- Active transcription backend: OpenAI Whisper by default, with opt-in whisper.cpp support through `TRANSCRIPTION_BACKEND=whisper.cpp`. Supported models are discovered from the installed backend and configured model paths. The benchmark command defaults to the full comparison matrix: `tiny`, `base`, `small`, `medium`, and `turbo`.
- Current non-goals: cloud transcription, hosted storage, multi-user collaboration, heavy database migration before it is needed, and a large framework rewrite.

## Benchmark Status

The latest local backend benchmark used:

```bash
make benchmark AUDIO=data/uploads/8351948977d7.opus MODELS=tiny,base,small LANGUAGE=de EXPECTED_TERMS=Festival,Lagerhallen,Booster,Hund
```

Setup: OpenAI Whisper in the repo venv, faster-whisper on CPU int8, and whisper.cpp via Homebrew with GGML models in `/tmp/whisper-local-models`.

| Backend | Model | Realtime factor | Expected terms |
| --- | --- | ---: | ---: |
| openai-whisper | tiny | 0.019 | 3/4 |
| faster-whisper | tiny | 0.038 | 4/4 |
| whisper.cpp | tiny | 0.020 | 3/4 |
| openai-whisper | base | 0.033 | 4/4 |
| faster-whisper | base | 0.054 | 4/4 |
| whisper.cpp | base | 0.020 | 4/4 |
| openai-whisper | small | 0.080 | 3/4 |
| faster-whisper | small | 0.161 | 3/4 |
| whisper.cpp | small | 0.049 | 4/4 |

Recommendation: keep OpenAI Whisper as the default production baseline for now. Use `whisper.cpp` with `base` as the next opt-in backend experiment because it matched expected-term coverage with the best measured speed on this sample. Do not switch the default until there is a broader German/English benchmark set.
