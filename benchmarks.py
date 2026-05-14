from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from transcription import active_backend_info, media_duration_seconds, transcribe_file


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


def benchmark_faster_whisper(
    audio: Path,
    model: str,
    language: str,
    expected_terms: list[str] | None = None,
    *,
    device: str = "cpu",
    compute_type: str = "int8",
) -> dict:
    if not module_installed("faster_whisper"):
        return candidate_status("faster-whisper")

    from faster_whisper import WhisperModel

    started = time.perf_counter()
    whisper_model = WhisperModel(model, device=device, compute_type=compute_type)
    segments_iter, info = whisper_model.transcribe(str(audio), language=language, task="transcribe")
    segments = list(segments_iter)
    elapsed = time.perf_counter() - started
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    duration = float(getattr(info, "duration", 0.0) or 0.0) or media_duration_seconds(audio) or 0.0
    return {
        "backend": "faster-whisper",
        "status": "complete",
        "model": model,
        "language": language,
        "audio": str(audio),
        "device": device,
        "compute_type": compute_type,
        "audio_duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(elapsed / duration, 3) if duration else None,
        "segments": len(segments),
        "quality": transcript_quality_signals(text, expected_terms or []),
    }


def default_whisper_cpp_model_path(model: str, extra_candidates: list[Path] | None = None) -> Path | None:
    env_path = os.environ.get("WHISPER_CPP_MODEL")
    candidates = [
        Path(env_path).expanduser() if env_path else None,
        *(extra_candidates or []),
        Path(f"/tmp/whisper-local-models/ggml-{model}.bin"),
        Path(f"data/models/ggml-{model}.bin"),
        Path(f"/opt/homebrew/share/whisper-cpp/ggml-{model}.bin"),
        Path(f"/opt/homebrew/opt/whisper-cpp/share/whisper-cpp/ggml-{model}.bin"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and "for-tests" not in candidate.name:
            return candidate
    return None


def convert_for_whisper_cpp(audio: Path) -> tuple[Path, Path | None]:
    if audio.suffix.lower() in {".flac", ".mp3", ".ogg", ".wav"}:
        return audio, None
    target = tempfile.NamedTemporaryFile(prefix="whisper-local-", suffix=".wav", delete=False)
    target_path = Path(target.name)
    target.close()
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-ar", "16000", "-ac", "1", str(target_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return target_path, target_path


def benchmark_whisper_cpp(
    audio: Path,
    model: str,
    language: str,
    expected_terms: list[str] | None = None,
    *,
    model_path: Path | None = None,
) -> dict:
    executable = shutil.which("whisper-cli")
    if not executable:
        return candidate_status("whisper.cpp")

    resolved_model = model_path or default_whisper_cpp_model_path(model)
    if resolved_model is None:
        return {
            "backend": "whisper.cpp",
            "status": "unavailable",
            "installed": True,
            "executable": executable,
            "model": model,
            "reason": f"No real GGML model found for {model}. Set WHISPER_CPP_MODEL or pass --whisper-cpp-model.",
            "next_step": f"Download ggml-{model}.bin from the whisper.cpp model repository.",
        }

    converted, cleanup_path = convert_for_whisper_cpp(audio)
    output_base = Path(tempfile.NamedTemporaryFile(prefix="whisper-cpp-", delete=True).name)
    started = time.perf_counter()
    try:
        command = [
            executable,
            "-m",
            str(resolved_model),
            "-l",
            language,
            "-nt",
            "-otxt",
            "-of",
            str(output_base),
            str(converted),
        ]
        result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=900)
        elapsed = time.perf_counter() - started
        output_path = output_base.with_suffix(".txt")
        text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if result.returncode != 0:
            return {
                "backend": "whisper.cpp",
                "status": "failed",
                "model": model,
                "model_path": str(resolved_model),
                "error": (result.stderr or result.stdout).strip()[-800:],
            }
        duration = media_duration_seconds(audio) or media_duration_seconds(converted) or 0.0
        return {
            "backend": "whisper.cpp",
            "status": "complete",
            "model": model,
            "language": language,
            "audio": str(audio),
            "model_path": str(resolved_model),
            "audio_duration_seconds": duration,
            "elapsed_seconds": round(elapsed, 3),
            "realtime_factor": round(elapsed / duration, 3) if duration else None,
            "quality": transcript_quality_signals(text, expected_terms or []),
        }
    finally:
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)
        output_base.with_suffix(".txt").unlink(missing_ok=True)


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

    has_expected_terms = any(int(item.get("quality", {}).get("expected_terms_total", 0) or 0) for item in completed)
    if has_expected_terms:
        ranked = sorted(
            completed,
            key=lambda item: (
                -int(item.get("quality", {}).get("expected_terms_found_count", 0) or 0),
                float(item["realtime_factor"]),
            ),
        )
        best = ranked[0]
    else:
        best = min(completed, key=lambda item: float(item["realtime_factor"]))

    unavailable = [item["backend"] for item in results if item.get("status") in {"unavailable", "adapter_missing"}]
    quality = best.get("quality", {})
    if unavailable:
        return {
            "choice": best["backend"],
            "model": best.get("model"),
            "reason": f"Best completed benchmark is {best['backend']}; unresolved candidates: {', '.join(unavailable)}.",
        }
    if has_expected_terms:
        return {
            "choice": best["backend"],
            "model": best.get("model"),
            "reason": (
                f"Best expected-term coverage ({quality.get('expected_terms_found_count', 0)}/"
                f"{quality.get('expected_terms_total', 0)}) with lowest realtime factor among ties."
            ),
        }
    return {
        "choice": best["backend"],
        "model": best.get("model"),
        "reason": "Lowest realtime factor among completed benchmark results.",
    }


def build_report(
    audio: Path,
    models: list[str],
    language: str,
    expected_terms: list[str],
    *,
    backends: list[str] | None = None,
    whisper_cpp_model: Path | None = None,
) -> dict:
    selected_backends = backends or ["openai-whisper", "faster-whisper", "whisper.cpp"]
    results = []
    for model in models:
        if "openai-whisper" in selected_backends:
            results.append(benchmark_openai_whisper(audio, model, language, expected_terms))
        if "faster-whisper" in selected_backends:
            results.append(benchmark_faster_whisper(audio, model, language, expected_terms))
        if "whisper.cpp" in selected_backends:
            results.append(benchmark_whisper_cpp(audio, model, language, expected_terms, model_path=whisper_cpp_model))
    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "active_backend": active_backend_info().name,
        "audio": str(audio),
        "language": language,
        "models": models,
        "backends": selected_backends,
        "results": results,
        "recommendation": recommend_backend(results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local transcription backends against one audio file.")
    parser.add_argument("--audio", required=True, help="Path to a representative local audio file.")
    parser.add_argument("--model", default="", help="Single Whisper model name for openai-whisper.")
    parser.add_argument("--models", default="small", help="Comma-separated OpenAI Whisper model names to benchmark.")
    parser.add_argument("--backends", default="openai-whisper,faster-whisper,whisper.cpp", help="Comma-separated backends to benchmark.")
    parser.add_argument("--language", default="de", help="Transcription language code.")
    parser.add_argument("--expected-terms", default="", help="Comma-separated words expected in a good transcript.")
    parser.add_argument("--whisper-cpp-model", default="", help="Path to a real ggml-*.bin model for whisper.cpp.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    audio = Path(args.audio).expanduser()
    if not audio.exists():
        raise SystemExit(f"Audio file not found: {audio}")

    models = [args.model] if args.model else parse_csv(args.models)
    expected_terms = parse_csv(args.expected_terms)
    backends = parse_csv(args.backends)
    whisper_cpp_model = Path(args.whisper_cpp_model).expanduser() if args.whisper_cpp_model else None
    report = build_report(audio, models, args.language, expected_terms, backends=backends, whisper_cpp_model=whisper_cpp_model)

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
