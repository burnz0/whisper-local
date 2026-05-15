from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field

from config import ANALYSIS_JOBS_PATH
from storage import load_json_file, locked_json_file, write_json_file


ANALYSIS_JOB_KINDS = ("title", "summary", "action_items", "entities")
FINISHED_ANALYSIS_STATUSES = {"complete", "failed", "canceled"}


@dataclass
class AnalysisJob:
    id: str
    kind: str
    record_id: str
    status: str
    queued_at: float
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    result: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        now = time.time()
        started_or_queued = self.started_at or self.queued_at
        payload = asdict(self)
        payload["elapsed_seconds"] = max(0, int((self.completed_at or now) - started_or_queued))
        return payload


def ensure_analysis_jobs_file() -> None:
    ANALYSIS_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ANALYSIS_JOBS_PATH.exists():
        write_json_file(ANALYSIS_JOBS_PATH, [])


def analysis_job_from_payload(payload: dict) -> AnalysisJob | None:
    kind = str(payload.get("kind", ""))
    record_id = str(payload.get("record_id", ""))
    if kind not in ANALYSIS_JOB_KINDS or not record_id:
        return None
    status = str(payload.get("status") or "queued")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return AnalysisJob(
        id=str(payload.get("id") or uuid.uuid4().hex[:12]),
        kind=kind,
        record_id=record_id,
        status=status,
        queued_at=float(payload.get("queued_at") or time.time()),
        started_at=float(payload["started_at"]) if payload.get("started_at") is not None else None,
        completed_at=float(payload["completed_at"]) if payload.get("completed_at") is not None else None,
        error=str(payload["error"]) if payload.get("error") is not None else None,
        result=result,
    )


def load_analysis_jobs() -> list[AnalysisJob]:
    ensure_analysis_jobs_file()
    raw = load_json_file(ANALYSIS_JOBS_PATH, [], list)
    jobs = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        job = analysis_job_from_payload(item)
        if job is not None:
            jobs.append(job)
    return sorted(jobs, key=lambda job: job.queued_at, reverse=True)


def save_analysis_jobs(jobs: list[AnalysisJob]) -> None:
    ensure_analysis_jobs_file()
    write_json_file(ANALYSIS_JOBS_PATH, [asdict(job) for job in jobs])


def create_analysis_job(kind: str, record_id: str) -> AnalysisJob:
    if kind not in ANALYSIS_JOB_KINDS:
        raise ValueError(f"Unsupported analysis job kind: {kind}")
    job = AnalysisJob(
        id=uuid.uuid4().hex[:12],
        kind=kind,
        record_id=record_id,
        status="queued",
        queued_at=time.time(),
    )
    with locked_json_file(ANALYSIS_JOBS_PATH):
        jobs = load_analysis_jobs()
        jobs.insert(0, job)
        save_analysis_jobs(jobs)
    return job


def update_analysis_job(job_id: str, **updates) -> AnalysisJob | None:
    allowed_fields = {"status", "started_at", "completed_at", "error", "result"}
    with locked_json_file(ANALYSIS_JOBS_PATH):
        jobs = load_analysis_jobs()
        updated_job = None
        for job in jobs:
            if job.id != job_id:
                continue
            for key, value in updates.items():
                if key in allowed_fields:
                    setattr(job, key, value)
            updated_job = job
            break
        if updated_job is None:
            return None
        save_analysis_jobs(jobs)
        return updated_job


def latest_analysis_job(record_id: str, kind: str) -> AnalysisJob | None:
    if kind not in ANALYSIS_JOB_KINDS:
        return None
    for job in load_analysis_jobs():
        if job.record_id == record_id and job.kind == kind:
            return job
    return None

