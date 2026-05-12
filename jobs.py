from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from errors import friendly_transcription_error
from storage import SavedUpload, create_transcript_from_audio, find_duplicate_record
from transcription import processing_mode_label


logger = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_LOCK = threading.Lock()
_JOBS: dict[str, "TranscriptionJob"] = {}
_BATCHES: dict[str, "ImportBatch"] = {}


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
    cancel_requested: bool = False
    batch_id: str | None = None
    source_hash: str = ""
    skip_reason: str | None = None

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
            "cancel_requested": self.cancel_requested,
            "can_cancel": self.status == "queued",
            "batch_id": self.batch_id,
            "source_hash": self.source_hash,
            "skip_reason": self.skip_reason,
        }


@dataclass
class ImportBatch:
    id: str
    job_ids: list[str]
    created_at: float

    def as_dict(self) -> dict:
        with _LOCK:
            jobs = [_JOBS[job_id] for job_id in self.job_ids if job_id in _JOBS]
        job_payloads = [job.as_dict() for job in jobs]
        finished_statuses = {"complete", "failed", "canceled", "skipped"}
        finished_count = sum(1 for job in jobs if job.status in finished_statuses)
        complete_count = sum(1 for job in jobs if job.status == "complete")
        failed_count = sum(1 for job in jobs if job.status == "failed")
        canceled_count = sum(1 for job in jobs if job.status == "canceled")
        skipped_count = sum(1 for job in jobs if job.status == "skipped")
        running_count = sum(1 for job in jobs if job.status == "running")
        queued_count = sum(1 for job in jobs if job.status == "queued")
        total_count = len(jobs)
        progress_percent = int((finished_count / total_count) * 100) if total_count else 0
        first_record_id = next((job.record_id for job in jobs if job.record_id), None)
        return {
            "id": self.id,
            "job_ids": list(self.job_ids),
            "jobs": job_payloads,
            "total_count": total_count,
            "finished_count": finished_count,
            "complete_count": complete_count,
            "failed_count": failed_count,
            "canceled_count": canceled_count,
            "skipped_count": skipped_count,
            "running_count": running_count,
            "queued_count": queued_count,
            "progress_percent": progress_percent,
            "status": "complete" if total_count and finished_count == total_count else "running",
            "first_record_id": first_record_id,
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


def start_transcription_job(
    audio_path: Path,
    transcript_id: str,
    source_name: str,
    model_name: str,
    language: str,
    *,
    batch_id: str | None = None,
    source_hash: str = "",
    source_size_bytes: int | None = None,
) -> TranscriptionJob:
    job = TranscriptionJob(
        id=uuid.uuid4().hex[:12],
        status="queued",
        source_name=source_name,
        model=model_name,
        language=language,
        processing_mode=processing_mode_label(),
        source_size_bytes=source_size_bytes if source_size_bytes is not None else (audio_path.stat().st_size if audio_path.exists() else 0),
        queued_at=time.time(),
        batch_id=batch_id,
        source_hash=source_hash,
    )
    with _LOCK:
        _JOBS[job.id] = job

    _EXECUTOR.submit(_run_job, job.id, audio_path, transcript_id, source_name, model_name, language, source_hash)
    logger.info("transcription job queued job=%s file=%s", job.id, source_name)
    return job


def _find_active_duplicate_job(source_hash: str) -> TranscriptionJob | None:
    if not source_hash:
        return None
    with _LOCK:
        for job in _JOBS.values():
            if job.source_hash == source_hash and job.status in {"queued", "running", "complete"}:
                return job
    return None


def _skip_duplicate_upload(
    saved_upload: SavedUpload,
    model_name: str,
    language: str,
    batch_id: str,
    *,
    record_id: str | None,
    skip_reason: str,
) -> TranscriptionJob:
    try:
        saved_upload.audio_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("could not remove duplicate upload file path=%s", saved_upload.audio_path)

    job = TranscriptionJob(
        id=uuid.uuid4().hex[:12],
        status="skipped",
        source_name=saved_upload.source_name,
        model=model_name,
        language=language,
        processing_mode=processing_mode_label(),
        source_size_bytes=saved_upload.source_size_bytes,
        queued_at=time.time(),
        completed_at=time.time(),
        record_id=record_id,
        batch_id=batch_id,
        source_hash=saved_upload.source_hash,
        skip_reason=skip_reason,
    )
    with _LOCK:
        _JOBS[job.id] = job
    logger.info("duplicate upload skipped job=%s file=%s record=%s", job.id, saved_upload.source_name, record_id)
    return job


def start_transcription_batch(saved_uploads: list[SavedUpload], model_name: str, language: str) -> ImportBatch:
    batch_id = uuid.uuid4().hex[:12]
    jobs = []
    seen_hashes: set[str] = set()
    for saved_upload in saved_uploads:
        duplicate_record = find_duplicate_record(saved_upload.source_hash)
        if duplicate_record is not None:
            jobs.append(
                _skip_duplicate_upload(
                    saved_upload,
                    model_name,
                    language,
                    batch_id,
                    record_id=duplicate_record.id,
                    skip_reason="Already imported; using the existing transcript.",
                )
            )
            continue

        duplicate_job = _find_active_duplicate_job(saved_upload.source_hash)
        if saved_upload.source_hash in seen_hashes or duplicate_job is not None:
            jobs.append(
                _skip_duplicate_upload(
                    saved_upload,
                    model_name,
                    language,
                    batch_id,
                    record_id=duplicate_job.record_id if duplicate_job is not None else None,
                    skip_reason="Duplicate in this import; transcription was not started again.",
                )
            )
            continue

        seen_hashes.add(saved_upload.source_hash)
        jobs.append(
            start_transcription_job(
                saved_upload.audio_path,
                saved_upload.transcript_id,
                saved_upload.source_name,
                model_name,
                language,
                batch_id=batch_id,
                source_hash=saved_upload.source_hash,
                source_size_bytes=saved_upload.source_size_bytes,
            )
        )
    batch = ImportBatch(id=batch_id, job_ids=[job.id for job in jobs], created_at=time.time())
    with _LOCK:
        _BATCHES[batch.id] = batch
    logger.info("transcription import batch queued batch=%s files=%s", batch.id, len(jobs))
    return batch


def _run_job(job_id: str, audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str, source_hash: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None and job.cancel_requested:
            job.status = "canceled"
            job.completed_at = time.time()
            return
    _update_job(job_id, status="running", started_at=time.time())
    try:
        record = create_transcript_from_audio(audio_path, transcript_id, source_name, model_name, language, source_hash=source_hash)
    except Exception as exc:
        logger.exception("transcription job failed job=%s", job_id)
        error, _status_code = friendly_transcription_error(exc)
        _update_job(job_id, status="failed", error=error, completed_at=time.time())
        return
    _update_job(job_id, status="complete", record_id=record.id, completed_at=time.time())
    _ANALYSIS_EXECUTOR.submit(_run_background_title_job, record.id)
    logger.info("transcription job complete job=%s record=%s", job_id, record.id)


def _run_background_title_job(record_id: str) -> None:
    try:
        from storage import update_record_title_with_instruction_model

        updated = update_record_title_with_instruction_model(record_id)
        if updated is not None:
            logger.info("background title generation complete record=%s title=%s", record_id, updated.title)
    except Exception:
        logger.exception("background title generation failed record=%s", record_id)


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


def get_import_batch(batch_id: str) -> ImportBatch | None:
    with _LOCK:
        return _BATCHES.get(batch_id)


def cancel_job(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return False
        if job.status != "queued":
            return False
        job.cancel_requested = True
        job.status = "canceled"
        job.completed_at = time.time()
        return True
