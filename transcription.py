from __future__ import annotations

import logging
import shutil
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
        duration = segments[-1]["end"] if segments else 0.0
        logger.info("transcription finished file=%s segments=%s duration=%.2f backend=%s", file_path.name, len(segments), duration, self.name)
        return TranscriptionResult(text=text, segments=segments, duration_seconds=duration)


_ACTIVE_BACKEND = OpenAIWhisperBackend()


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
