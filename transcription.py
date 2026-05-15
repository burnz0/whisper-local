from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config import MODELS
from summaries import format_duration

try:
    import whisper
except ImportError:  # pragma: no cover
    whisper = None


logger = logging.getLogger(__name__)


def media_duration_seconds(file_path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("could not read media duration file=%s", file_path, exc_info=True)
        return None
    if result.returncode != 0:
        logger.debug("ffprobe duration failed file=%s stderr=%s", file_path, result.stderr.strip())
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: list[dict]
    duration_seconds: float


@dataclass(frozen=True)
class TranscriptionBackendInfo:
    name: str
    label: str
    installed: bool
    required_components: tuple[str, ...]
    supported_models: tuple[str, ...]
    active_device_label: str
    can_cancel_active_job: bool
    setup_hint: str = ""
    model_paths: tuple[str, ...] = ()


class TranscriptionBackend(Protocol):
    name: str
    label: str

    def info(self) -> TranscriptionBackendInfo:
        ...

    def load_model(self, name: str):
        ...

    def transcribe(self, file_path: Path, model_name: str, language: str) -> TranscriptionResult:
        ...


class OpenAIWhisperBackend:
    name = "openai-whisper"
    label = "OpenAI Whisper"

    def __init__(self) -> None:
        self._model_cache: dict[str, object] = {}

    def supported_models(self) -> tuple[str, ...]:
        if whisper is None:
            return ()
        available = set(getattr(whisper, "_MODELS", {}).keys())
        configured = [model for model in MODELS if model in available]
        return tuple(configured)

    def active_device_label(self) -> str:
        if whisper is None:
            return "Unavailable"
        try:
            import torch
        except ImportError:  # pragma: no cover
            return "CPU"

        try:
            # openai-whisper chooses CUDA when available and otherwise CPU. It does not use MPS/Metal here.
            return "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
        except Exception:  # pragma: no cover
            logger.debug("could not detect torch processing mode", exc_info=True)
            return "CPU"

    def info(self) -> TranscriptionBackendInfo:
        installed = whisper is not None and shutil.which("ffmpeg") is not None
        return TranscriptionBackendInfo(
            name=self.name,
            label=self.label,
            installed=installed,
            required_components=("openai-whisper", "ffmpeg"),
            supported_models=self.supported_models(),
            active_device_label=self.active_device_label(),
            can_cancel_active_job=False,
            setup_hint="Install requirements-ml.txt and ffmpeg. Models download into the Whisper cache on first use.",
        )

    def load_model(self, name: str):
        if whisper is None:
            raise RuntimeError("Whisper is not installed for this Python interpreter.")
        if name not in self.supported_models():
            raise ValueError(f"Unsupported model for {self.label}: {name}")
        model = self._model_cache.get(name)
        if model is None:
            logger.info("loading whisper model=%s backend=%s", name, self.name)
            model = whisper.load_model(name)
            self._model_cache[name] = model
        return model

    def transcribe(self, file_path: Path, model_name: str, language: str) -> TranscriptionResult:
        logger.info("transcription started file=%s model=%s language=%s backend=%s", file_path.name, model_name, language, self.name)
        model = self.load_model(model_name)
        result = model.transcribe(
            str(file_path),
            language=language,
            task="transcribe",
            fp16=False,
            verbose=False,
        )
        text = result.get("text", "").strip()
        segments = []
        for segment in result.get("segments", []):
            segments.append(
                {
                    "id": int(segment.get("id", len(segments))),
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                    "start_label": format_duration(float(segment.get("start", 0.0))),
                    "end_label": format_duration(float(segment.get("end", 0.0))),
                    "text": str(segment.get("text", "")).strip(),
                }
            )
        segment_duration = segments[-1]["end"] if segments else 0.0
        duration = media_duration_seconds(file_path) or segment_duration
        logger.info("transcription finished file=%s segments=%s duration=%.2f backend=%s", file_path.name, len(segments), duration, self.name)
        return TranscriptionResult(text=text, segments=segments, duration_seconds=duration)


WHISPER_CPP_MODEL_CANDIDATE_DIRS = (
    Path("/tmp/whisper-local-models"),
    Path("data/models"),
    Path("/opt/homebrew/share/whisper-cpp"),
    Path("/opt/homebrew/opt/whisper-cpp/share/whisper-cpp"),
)


def valid_whisper_cpp_model_path(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0 and "for-tests" not in path.name


def infer_whisper_cpp_model_name(path: Path) -> str | None:
    name = path.name.lower()
    for model in sorted(MODELS, key=len, reverse=True):
        if re.search(rf"(^|[-_.]){re.escape(model)}($|[-_.])", name):
            return model
    return None


def whisper_cpp_model_candidates(model: str, extra_candidates: list[Path] | None = None) -> list[Path]:
    env_model = os.environ.get("WHISPER_CPP_MODEL", "").strip()
    env_model_dir = os.environ.get("WHISPER_CPP_MODEL_DIR", "").strip()
    candidates = []
    if env_model:
        candidates.append(Path(env_model).expanduser())
    if extra_candidates:
        candidates.extend(extra_candidates)
    if env_model_dir:
        candidates.append(Path(env_model_dir).expanduser() / f"ggml-{model}.bin")
    candidates.extend(path / f"ggml-{model}.bin" for path in WHISPER_CPP_MODEL_CANDIDATE_DIRS)
    return candidates


def default_whisper_cpp_model_path(model: str, extra_candidates: list[Path] | None = None) -> Path | None:
    for candidate in whisper_cpp_model_candidates(model, extra_candidates):
        if valid_whisper_cpp_model_path(candidate):
            return candidate
    return None


def convert_for_whisper_cpp(audio: Path) -> tuple[Path, Path | None]:
    if audio.suffix.lower() in {".flac", ".mp3", ".ogg", ".wav"}:
        return audio, None
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to convert this audio format for whisper.cpp.")
    target = tempfile.NamedTemporaryFile(prefix="whisper-local-", suffix=".wav", delete=False)
    target_path = Path(target.name)
    target.close()
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-ar", "16000", "-ac", "1", str(target_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return target_path, target_path


def parse_whisper_cpp_timestamp(value: object, *, numeric_unit: str = "seconds") -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        if numeric_unit == "milliseconds":
            return number / 1000
        if numeric_unit == "centiseconds":
            return number / 100
        return number
    text = str(value or "").strip()
    if not text:
        return 0.0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[,.](\d{1,3}))?", text)
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int((match.group(4) or "0").ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def whisper_cpp_segment_times(segment: dict) -> tuple[float, float]:
    timestamps = segment.get("timestamps") if isinstance(segment.get("timestamps"), dict) else {}
    if timestamps:
        return (
            parse_whisper_cpp_timestamp(timestamps.get("from")),
            parse_whisper_cpp_timestamp(timestamps.get("to")),
        )
    offsets = segment.get("offsets") if isinstance(segment.get("offsets"), dict) else {}
    if offsets:
        return (
            parse_whisper_cpp_timestamp(offsets.get("from"), numeric_unit="milliseconds"),
            parse_whisper_cpp_timestamp(offsets.get("to"), numeric_unit="milliseconds"),
        )
    if "t0" in segment or "t1" in segment:
        return (
            parse_whisper_cpp_timestamp(segment.get("t0"), numeric_unit="centiseconds"),
            parse_whisper_cpp_timestamp(segment.get("t1"), numeric_unit="centiseconds"),
        )
    return (
        parse_whisper_cpp_timestamp(segment.get("start")),
        parse_whisper_cpp_timestamp(segment.get("end")),
    )


def parse_whisper_cpp_json(payload: object) -> tuple[str, list[dict]]:
    if isinstance(payload, dict):
        raw_segments = payload.get("transcription") or payload.get("segments") or []
        payload_text = str(payload.get("text") or payload.get("result") or "").strip()
    elif isinstance(payload, list):
        raw_segments = payload
        payload_text = ""
    else:
        return "", []

    segments = []
    if isinstance(raw_segments, list):
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                continue
            text = str(raw_segment.get("text", "")).strip()
            if not text:
                continue
            start, end = whisper_cpp_segment_times(raw_segment)
            segments.append(
                {
                    "id": int(raw_segment.get("id", len(segments))),
                    "start": start,
                    "end": end,
                    "start_label": format_duration(start),
                    "end_label": format_duration(end),
                    "text": text,
                }
            )
    text = " ".join(segment["text"] for segment in segments).strip() or payload_text
    return text, segments


class WhisperCppBackend:
    name = "whisper.cpp"
    label = "whisper.cpp"

    def executable(self) -> str | None:
        return shutil.which("whisper-cli")

    def model_path(self, model: str) -> Path | None:
        return default_whisper_cpp_model_path(model)

    def supported_models(self) -> tuple[str, ...]:
        if self.executable() is None:
            return ()
        env_model = os.environ.get("WHISPER_CPP_MODEL", "").strip()
        if env_model:
            path = Path(env_model).expanduser()
            if not valid_whisper_cpp_model_path(path):
                return ()
            inferred_model = infer_whisper_cpp_model_name(path)
            return (inferred_model,) if inferred_model in MODELS else tuple(MODELS)
        return tuple(model for model in MODELS if self.model_path(model) is not None)

    def active_device_label(self) -> str:
        return "Metal/CPU via whisper.cpp" if self.executable() else "Unavailable"

    def info(self) -> TranscriptionBackendInfo:
        executable = self.executable()
        supported = self.supported_models()
        model_paths = tuple(str(self.model_path(model)) for model in supported if self.model_path(model) is not None)
        installed = executable is not None and bool(supported)
        return TranscriptionBackendInfo(
            name=self.name,
            label=self.label,
            installed=installed,
            required_components=("whisper-cli", "GGML model", "ffmpeg for non-native formats"),
            supported_models=supported,
            active_device_label=self.active_device_label(),
            can_cancel_active_job=False,
            setup_hint=(
                "Install whisper.cpp so whisper-cli is on PATH, then set WHISPER_CPP_MODEL=/path/to/ggml-base.bin "
                "or WHISPER_CPP_MODEL_DIR=/path/to/models containing ggml-<model>.bin files."
            ),
            model_paths=model_paths,
        )

    def load_model(self, name: str) -> Path:
        executable = self.executable()
        if executable is None:
            raise RuntimeError("whisper.cpp is selected, but whisper-cli is not on PATH.")
        if name not in MODELS:
            raise ValueError(f"Unsupported model for {self.label}: {name}")
        model_path = self.model_path(name)
        if model_path is None:
            raise RuntimeError(
                f"No usable whisper.cpp GGML model found for '{name}'. "
                "Set WHISPER_CPP_MODEL to a real ggml-*.bin file or WHISPER_CPP_MODEL_DIR to a model directory."
            )
        return model_path

    def transcribe(self, file_path: Path, model_name: str, language: str) -> TranscriptionResult:
        executable = self.executable()
        if executable is None:
            raise RuntimeError("whisper.cpp is selected, but whisper-cli is not on PATH.")
        model_path = self.load_model(model_name)
        converted, cleanup_path = convert_for_whisper_cpp(file_path)
        output_base = Path(tempfile.NamedTemporaryFile(prefix="whisper-cpp-", delete=True).name)
        command = [
            executable,
            "-m",
            str(model_path),
            "-l",
            language,
            "-oj",
            "-otxt",
            "-of",
            str(output_base),
            str(converted),
        ]
        logger.info("transcription started file=%s model=%s language=%s backend=%s model_path=%s", file_path.name, model_name, language, self.name, model_path)
        started = time.perf_counter()
        try:
            result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=900)
            elapsed = time.perf_counter() - started
            if result.returncode != 0:
                error = (result.stderr or result.stdout or "whisper.cpp transcription failed.").strip()
                raise RuntimeError(error[-1200:])
            json_path = output_base.with_suffix(".json")
            txt_path = output_base.with_suffix(".txt")
            text = ""
            segments: list[dict] = []
            if json_path.exists():
                text, segments = parse_whisper_cpp_json(json.loads(json_path.read_text(encoding="utf-8")))
            if not text and txt_path.exists():
                text = txt_path.read_text(encoding="utf-8").strip()
            duration = media_duration_seconds(file_path) or media_duration_seconds(converted) or (segments[-1]["end"] if segments else 0.0)
            logger.info(
                "transcription finished file=%s segments=%s duration=%.2f elapsed=%.2f backend=%s",
                file_path.name,
                len(segments),
                duration,
                elapsed,
                self.name,
            )
            return TranscriptionResult(text=text, segments=segments, duration_seconds=duration)
        finally:
            if cleanup_path is not None:
                cleanup_path.unlink(missing_ok=True)
            output_base.with_suffix(".json").unlink(missing_ok=True)
            output_base.with_suffix(".txt").unlink(missing_ok=True)


def build_active_backend() -> TranscriptionBackend:
    backend_name = os.environ.get("TRANSCRIPTION_BACKEND", "openai-whisper").strip().lower()
    if backend_name in {"whisper.cpp", "whisper-cpp", "whisper_cpp"}:
        return WhisperCppBackend()
    if backend_name and backend_name != OpenAIWhisperBackend.name:
        logger.warning("unknown transcription backend=%s; falling back to %s", backend_name, OpenAIWhisperBackend.name)
    return OpenAIWhisperBackend()


_ACTIVE_BACKEND = build_active_backend()


def active_backend() -> TranscriptionBackend:
    return _ACTIVE_BACKEND


def active_backend_info() -> TranscriptionBackendInfo:
    return _ACTIVE_BACKEND.info()


def supported_models() -> tuple[str, ...]:
    return _ACTIVE_BACKEND.supported_models()


def check_dependencies() -> list[str]:
    missing = []
    if whisper is None:
        missing.append("openai-whisper")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    return missing


def processing_mode_label() -> str:
    return _ACTIVE_BACKEND.active_device_label()


def get_model(name: str):
    return _ACTIVE_BACKEND.load_model(name)


def transcribe_file(file_path: Path, model_name: str, language: str) -> tuple[str, list[dict], float]:
    result = _ACTIVE_BACKEND.transcribe(file_path, model_name, language)
    return result.text, result.segments, result.duration_seconds
