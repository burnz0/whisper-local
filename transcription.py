from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import MODELS
from summaries import format_duration

try:
    import whisper
except ImportError:  # pragma: no cover
    whisper = None


logger = logging.getLogger(__name__)
_MODEL_CACHE: dict[str, object] = {}


def check_dependencies() -> list[str]:
    missing = []
    if whisper is None:
        missing.append("openai-whisper")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    return missing


def get_model(name: str):
    if whisper is None:
        raise RuntimeError("Whisper is not installed for this Python interpreter.")
    if name not in MODELS:
        raise ValueError(f"Unsupported model: {name}")
    model = _MODEL_CACHE.get(name)
    if model is None:
        logger.info("loading whisper model=%s", name)
        model = whisper.load_model(name)
        _MODEL_CACHE[name] = model
    return model


def transcribe_file(file_path: Path, model_name: str, language: str) -> tuple[str, list[dict], float]:
    logger.info("transcription started file=%s model=%s language=%s", file_path.name, model_name, language)
    model = get_model(model_name)
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
    logger.info("transcription finished file=%s segments=%s duration=%.2f", file_path.name, len(segments), duration)
    return text, segments, duration
