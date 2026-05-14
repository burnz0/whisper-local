from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

from transcription import active_backend_info, transcribe_file


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def transcript_quality_signals(text: str, expected_terms: list[str]) -> dict:
    normalized = text.lower()
    found_terms = [term for term in expected_terms if term.lower() in normalized]
    return {
        "expected_terms": expected_terms,
        "expected_terms_found": found_terms,
        "expected_terms_found_count": len(found_terms),
        "expected_terms_total": len(expected_terms),
        "characters": len(text),
        "preview": text[:240],
    }


def benchmark_openai_whisper(audio: Path, model: str, language: str, expected_terms: list[str] | None = None) -> dict:
    started = time.perf_counter()
    text, segments, duration = transcribe_file(audio, model_name=model, language=language)
    elapsed = time.perf_counter() - started
    return {
        "backend": "openai-whisper",
        "status": "complete",
        "model": model,
        "language": language,
        "audio": str(audio),
        "audio_duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(elapsed / duration, 3) if duration else None,
        "segments": len(segments),
        "quality": transcript_quality_signals(text, expected_terms or []),
    }


def module_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def candidate_status(name: str) -> dict:
    if name == "faster-whisper":
        installed = module_installed("faster_whisper")
        return {
            "backend": name,
            "status": "adapter_missing" if installed else "unavailable",
            "installed": installed,
            "reason": "Python package is installed but this app has no benchmark adapter yet."
            if installed
            else "Install faster-whisper before benchmarking this candidate.",
            "next_step": "Add a FasterWhisperBackend adapter and run the same audio/model matrix.",
        }
    if name == "whisper.cpp":
        executable = shutil.which("whisper-cli")
        return {
            "backend": name,
            "status": "adapter_missing" if executable else "unavailable",
            "installed": bool(executable),
            "executable": executable,
            "reason": "whisper-cli is installed but this app has no GGML model adapter yet."
            if executable
            else "Install whisper.cpp and make whisper-cli available before benchmarking this candidate.",
            "next_step": "Add a whisper.cpp adapter with an explicit GGML model path and run the same audio matrix.",
        }
    return {"backend": name, "status": "unknown", "reason": "Unknown benchmark candidate."}


def recommend_backend(results: list[dict]) -> dict:
    completed = [item for item in results if item.get("status") == "complete" and item.get("realtime_factor") is not None]
    if not completed:
        return {
            "choice": "no-change",
            "reason": "No completed benchmark result is available.",
        }

    fastest = min(completed, key=lambda item: float(item["realtime_factor"]))
    unavailable = [item["backend"] for item in results if item.get("status") in {"unavailable", "adapter_missing"}]
    if unavailable:
        return {
            "choice": fastest["backend"],
            "model": fastest.get("model"),
            "reason": f"Only completed local benchmark is {fastest['backend']}; unresolved candidates: {', '.join(unavailable)}.",
        }
    return {
        "choice": fastest["backend"],
        "model": fastest.get("model"),
        "reason": "Lowest realtime factor among completed benchmark results.",
    }


def build_report(audio: Path, models: list[str], language: str, expected_terms: list[str]) -> dict:
    results = [benchmark_openai_whisper(audio, model, language, expected_terms) for model in models]
    results.extend([candidate_status("faster-whisper"), candidate_status("whisper.cpp")])
    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "active_backend": active_backend_info().name,
        "audio": str(audio),
        "language": language,
        "models": models,
        "results": results,
        "recommendation": recommend_backend(results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local transcription backends against one audio file.")
    parser.add_argument("--audio", required=True, help="Path to a representative local audio file.")
    parser.add_argument("--model", default="", help="Single Whisper model name for openai-whisper.")
    parser.add_argument("--models", default="small", help="Comma-separated OpenAI Whisper model names to benchmark.")
    parser.add_argument("--language", default="de", help="Transcription language code.")
    parser.add_argument("--expected-terms", default="", help="Comma-separated words expected in a good transcript.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    audio = Path(args.audio).expanduser()
    if not audio.exists():
        raise SystemExit(f"Audio file not found: {audio}")

    models = [args.model] if args.model else parse_csv(args.models)
    expected_terms = parse_csv(args.expected_terms)
    report = build_report(audio, models, args.language, expected_terms)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"Active backend: {active_backend_info().label}")
    print(f"Audio: {audio}")
    print(f"Language: {args.language}")
    for result in report["results"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Recommendation:")
    print(json.dumps(report["recommendation"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
