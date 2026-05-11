from __future__ import annotations

import logging
import threading
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
    record_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "source_name": self.source_name,
            "model": self.model,
            "language": self.language,
            "processing_mode": self.processing_mode,
            "record_id": self.record_id,
            "error": self.error,
        }


def start_transcription_job(audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str) -> TranscriptionJob:
    job = TranscriptionJob(
        id=uuid.uuid4().hex[:12],
        status="queued",
        source_name=source_name,
        model=model_name,
        language=language,
        processing_mode=processing_mode_label(),
    )
    with _LOCK:
        _JOBS[job.id] = job

    _EXECUTOR.submit(_run_job, job.id, audio_path, transcript_id, source_name, model_name, language)
    logger.info("transcription job queued job=%s file=%s", job.id, source_name)
    return job


def _run_job(job_id: str, audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str) -> None:
    _update_job(job_id, status="running")
    try:
        record = create_transcript_from_audio(audio_path, transcript_id, source_name, model_name, language)
    except Exception as exc:
        logger.exception("transcription job failed job=%s", job_id)
        error, _status_code = friendly_transcription_error(exc)
        _update_job(job_id, status="failed", error=error)
        return
    _update_job(job_id, status="complete", record_id=record.id)
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
