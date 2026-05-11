from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from transcription import active_backend_info, transcribe_file


def benchmark_openai_whisper(audio: Path, model: str, language: str) -> dict:
    started = time.perf_counter()
    text, segments, duration = transcribe_file(audio, model_name=model, language=language)
    elapsed = time.perf_counter() - started
    return {
        "backend": "openai-whisper",
        "model": model,
        "language": language,
        "audio": str(audio),
        "audio_duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(elapsed / duration, 3) if duration else None,
        "segments": len(segments),
        "characters": len(text),
        "preview": text[:240],
    }


def unavailable_candidate(name: str, reason: str) -> dict:
    return {"backend": name, "status": "unavailable", "reason": reason}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local transcription backends against one audio file.")
    parser.add_argument("--audio", required=True, help="Path to a representative local audio file.")
    parser.add_argument("--model", default="small", help="Whisper model name for openai-whisper.")
    parser.add_argument("--language", default="de", help="Transcription language code.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    audio = Path(args.audio).expanduser()
    if not audio.exists():
        raise SystemExit(f"Audio file not found: {audio}")

    results = [
        benchmark_openai_whisper(audio, args.model, args.language),
        unavailable_candidate("faster-whisper", "Install faster-whisper and add an adapter before benchmarking."),
        unavailable_candidate("whisper.cpp", "Install whisper-cli and add a GGML model path before benchmarking.")
        if shutil.which("whisper-cli") is None
        else unavailable_candidate("whisper.cpp", "whisper-cli detected, but no adapter is implemented yet."),
    ]

    if args.json:
        print(json.dumps({"active_backend": active_backend_info().name, "results": results}, ensure_ascii=False, indent=2))
        return

    print(f"Active backend: {active_backend_info().label}")
    for result in results:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
