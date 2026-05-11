from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from errors import friendly_transcription_error
from storage import create_transcript_from_audio
from transcription import processing_mode_label


logger = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_LOCK = threading.Lock()
_JOBS: dict[str, "TranscriptionJob"] = {}


@dataclass
class TranscriptionJob:
    id: str
    status: str
    source_name: str
    model: str
    language: str
    processing_mode: str
    source_size_bytes: int
    queued_at: float
    started_at: float | None = None
    completed_at: float | None = None
    record_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        now = time.time()
        started_or_queued = self.started_at or self.queued_at
        return {
            "id": self.id,
            "status": self.status,
            "source_name": self.source_name,
            "model": self.model,
            "language": self.language,
            "processing_mode": self.processing_mode,
            "source_size_bytes": self.source_size_bytes,
            "source_size_label": format_bytes(self.source_size_bytes),
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "elapsed_seconds": max(0, int((self.completed_at or now) - started_or_queued)),
            "estimated_duration": estimate_duration_label(self.source_size_bytes, self.model),
            "record_id": self.record_id,
            "error": self.error,
        }


def format_bytes(size: int) -> str:
    value = float(max(size, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def estimate_duration_label(size_bytes: int, model_name: str) -> str:
    size_mb = size_bytes / (1024 * 1024)
    model_weight = {"tiny": 0.75, "base": 1.0, "small": 1.6}.get(model_name, 1.0)
    weighted_size = size_mb * model_weight
    if weighted_size < 8:
        return "Usually under a minute"
    if weighted_size < 40:
        return "A few minutes"
    return "Long-running local job"


def start_transcription_job(audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str) -> TranscriptionJob:
    job = TranscriptionJob(
        id=uuid.uuid4().hex[:12],
        status="queued",
        source_name=source_name,
        model=model_name,
        language=language,
        processing_mode=processing_mode_label(),
        source_size_bytes=audio_path.stat().st_size if audio_path.exists() else 0,
        queued_at=time.time(),
    )
    with _LOCK:
        _JOBS[job.id] = job

    _EXECUTOR.submit(_run_job, job.id, audio_path, transcript_id, source_name, model_name, language)
    logger.info("transcription job queued job=%s file=%s", job.id, source_name)
    return job


def _run_job(job_id: str, audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str) -> None:
    _update_job(job_id, status="running", started_at=time.time())
    try:
        record = create_transcript_from_audio(audio_path, transcript_id, source_name, model_name, language)
    except Exception as exc:
        logger.exception("transcription job failed job=%s", job_id)
        error, _status_code = friendly_transcription_error(exc)
        _update_job(job_id, status="failed", error=error, completed_at=time.time())
        return
    _update_job(job_id, status="complete", record_id=record.id, completed_at=time.time())
    logger.info("transcription job complete job=%s record=%s", job_id, record.id)


def _update_job(job_id: str, **updates) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        for key, value in updates.items():
            setattr(job, key, value)


def get_job(job_id: str) -> TranscriptionJob | None:
    with _LOCK:
        return _JOBS.get(job_id)
