# Transcription Benchmark Results

Benchmarked on 2026-05-14 with the local representative German voice note:

```bash
make benchmark AUDIO=data/uploads/8351948977d7.opus MODELS=tiny,base,small LANGUAGE=de EXPECTED_TERMS=Festival,Lagerhallen,Booster,Hund
```

Candidate setup:

- `openai-whisper`: installed in the project virtual environment.
- `faster-whisper`: installed in the project virtual environment with CPU `int8` compute.
- `whisper.cpp`: installed via Homebrew `whisper-cpp`; real GGML models were downloaded to `/tmp/whisper-local-models/`.

| Backend | Model | Realtime factor | Expected terms | Notes |
| --- | --- | ---: | ---: | --- |
| openai-whisper | tiny | 0.019 | 3/4 | Fast, missed `Booster`. |
| faster-whisper | tiny | 0.038 | 4/4 | Better term coverage than OpenAI tiny, slower on CPU. |
| whisper.cpp | tiny | 0.020 | 3/4 | Fast, missed `Booster`. |
| openai-whisper | base | 0.033 | 4/4 | Good quality signal, slower than whisper.cpp base. |
| faster-whisper | base | 0.054 | 4/4 | Good quality signal, slower than OpenAI and whisper.cpp on this machine. |
| whisper.cpp | base | 0.020 | 4/4 | Best speed among full expected-term coverage results. |
| openai-whisper | small | 0.080 | 3/4 | Slower and missed `Lagerhallen` on this sample. |
| faster-whisper | small | 0.161 | 3/4 | Slowest candidate in this matrix. |
| whisper.cpp | small | 0.049 | 4/4 | Good quality signal, slower than whisper.cpp base. |

Recommendation from this benchmark:

- Prefer `whisper.cpp` with `base` for the next local backend experiment.
- Keep `openai-whisper` as the baseline until the app has a production `whisper.cpp` backend adapter, model-path management, and at least one more representative German and English benchmark file.
- Do not switch the default to `small` based on this sample; `small` was slower and did not improve expected-term coverage here.

Limitations:

- This is one representative German voice note, not a full corpus.
- Expected-term coverage is a lightweight quality proxy; human review is still needed for final default-model selection.
- Memory was not profiled separately in this run.
