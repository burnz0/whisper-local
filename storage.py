from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj

from config import (
    ALLOWED_EXTENSIONS,
    DATA_DIR,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_SETTINGS,
    LANGUAGES,
    LIBRARY_PATH,
    MODELS,
    SETTINGS_PATH,
    TRANSCRIPT_DIR,
    UPLOAD_DIR,
)
from summaries import (
    generate_summary,
    generate_title_from_summary,
    normalize_settings,
    paragraphize_summary,
    sentence_summary,
    slugify_title,
)
from transcription import transcribe_file


logger = logging.getLogger(__name__)
DEFAULT_COLLECTION = "Inbox"


@dataclass
class TranscriptRecord:
    id: str
    title: str
    title_source: str
    filename: str
    stored_filename: str
    transcript_filename: str
    created_at: str
    model: str
    language: str
    duration_seconds: float
    transcript_text: str
    summary: list[str]
    summary_provider: str
    segments: list[dict]
    tags: list[str]
    collection: str
    notes: str

    @property
    def audio_path(self) -> Path:
        return UPLOAD_DIR / self.stored_filename

    @property
    def transcript_path(self) -> Path:
        return TRANSCRIPT_DIR / self.transcript_filename


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, TRANSCRIPT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not LIBRARY_PATH.exists():
        LIBRARY_PATH.write_text("[]\n", encoding="utf-8")
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps(DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8")


def backup_invalid_json(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.stem}.corrupt-{timestamp}{path.suffix}")
    path.replace(backup_path)
    logger.warning("invalid json backed up path=%s backup=%s", path, backup_path)
    return backup_path


def load_json_file(path: Path, default_value, expected_type: type):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup_invalid_json(path)
        path.write_text(json.dumps(default_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return default_value
    except OSError:
        path.write_text(json.dumps(default_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return default_value

    if not isinstance(payload, expected_type):
        backup_invalid_json(path)
        path.write_text(json.dumps(default_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return default_value

    return payload


def is_allowed_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix in ALLOWED_EXTENSIONS


def load_settings() -> dict:
    ensure_dirs()
    raw = load_json_file(SETTINGS_PATH, DEFAULT_SETTINGS, dict)
    return normalize_settings(raw)


def save_settings(settings: dict) -> None:
    ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def load_library() -> list[TranscriptRecord]:
    ensure_dirs()
    raw = load_json_file(LIBRARY_PATH, [], list)
    records = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        records.append(record_from_payload(item))
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def migrate_library() -> int:
    ensure_dirs()
    settings = load_settings()
    raw = load_json_file(LIBRARY_PATH, [], list)
    migrated = []
    changed_count = 0

    for item in raw:
        if not isinstance(item, dict):
            changed_count += 1
            continue

        next_item = dict(item)
        transcript_text = str(next_item.get("transcript_text", ""))
        stored_summary = next_item.get("summary")
        stored_provider = str(next_item.get("summary_provider", ""))
        if not isinstance(stored_summary, list) or not stored_summary or not stored_provider:
            summary, used_provider = generate_summary(
                transcript_text,
                str(next_item.get("language", DEFAULT_LANGUAGE)),
                settings,
            )
            next_item["summary"] = summary
            next_item["summary_provider"] = used_provider
            if str(next_item.get("title_source", "manual")) == "auto":
                fallback_title = Path(str(next_item.get("filename", ""))).stem.replace("_", " ")
                next_item["title"] = generate_title_from_summary(summary, fallback_title)
            changed_count += 1

        migrated.append(record_from_payload(next_item))

    if changed_count:
        save_library(migrated)

    return changed_count


def save_library(records: list[TranscriptRecord]) -> None:
    ensure_dirs()
    payload = [asdict(record) for record in records]
    LIBRARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def record_from_payload(item: dict) -> TranscriptRecord:
    transcript_text = str(item.get("transcript_text", ""))
    filename = str(item.get("filename", "upload"))
    transcript_id = str(item.get("id") or uuid.uuid4().hex[:12])
    language = str(item.get("language", DEFAULT_LANGUAGE))
    model = str(item.get("model", DEFAULT_MODEL))
    raw_segments = item.get("segments") if isinstance(item.get("segments"), list) else []
    segments = []
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        next_segment = dict(segment)
        next_segment["bookmarked"] = bool(next_segment.get("bookmarked", False))
        next_segment["highlighted"] = bool(next_segment.get("highlighted", False))
        next_segment["speaker"] = normalize_speaker(next_segment.get("speaker", ""))
        segments.append(next_segment)
    summary = item.get("summary") if isinstance(item.get("summary"), list) else []
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []

    if not summary:
        summary = paragraphize_summary(sentence_summary(transcript_text, language=language), max_chars=320)

    return TranscriptRecord(
        id=transcript_id,
        title=slugify_title(str(item.get("title") or Path(filename).stem)),
        title_source=str(item.get("title_source", "manual")),
        filename=filename,
        stored_filename=str(item.get("stored_filename", "")),
        transcript_filename=str(item.get("transcript_filename") or f"{transcript_id}.txt"),
        created_at=str(item.get("created_at", "")),
        model=model if model in MODELS else DEFAULT_MODEL,
        language=language if language in LANGUAGES else DEFAULT_LANGUAGE,
        duration_seconds=coerce_float(item.get("duration_seconds")),
        transcript_text=transcript_text,
        summary=[str(entry) for entry in summary],
        summary_provider=str(item.get("summary_provider") or "extractive"),
        segments=segments,
        tags=normalize_tags(tags),
        collection=normalize_collection(item.get("collection", DEFAULT_COLLECTION)),
        notes=str(item.get("notes", "")),
    )


def get_record(record_id: str) -> TranscriptRecord | None:
    for record in load_library():
        if record.id == record_id:
            return record
    return None


def persist_record(record: TranscriptRecord) -> None:
    records = load_library()
    records = [item for item in records if item.id != record.id]
    records.append(record)
    save_library(records)
    record.transcript_path.write_text(record.transcript_text, encoding="utf-8")


def save_upload(file_storage) -> tuple[Path, str, str]:
    ensure_dirs()
    source_name = Path(file_storage.filename or "upload").name
    if not is_allowed_file(source_name):
        raise ValueError("This file format is not supported yet.")

    transcript_id = uuid.uuid4().hex[:12]
    stored_filename = f"{transcript_id}{Path(source_name).suffix.lower()}"
    audio_path = UPLOAD_DIR / stored_filename

    with audio_path.open("wb") as target:
        copyfileobj(file_storage.stream, target)

    return audio_path, transcript_id, source_name


def create_transcript_from_audio(audio_path: Path, transcript_id: str, source_name: str, model_name: str, language: str) -> TranscriptRecord:
    settings = load_settings()
    text, segments, duration = transcribe_file(audio_path, model_name=model_name, language=language)
    title = slugify_title(Path(source_name).stem.replace("_", " "))
    created_at = datetime.now().isoformat(timespec="seconds")
    transcript_filename = f"{transcript_id}.txt"
    summary, summary_provider = generate_summary(text, language=language, settings=settings)
    generated_title = generate_title_from_summary(summary, title)

    record = TranscriptRecord(
        id=transcript_id,
        title=generated_title,
        title_source="auto",
        filename=source_name,
        stored_filename=audio_path.name,
        transcript_filename=transcript_filename,
        created_at=created_at,
        model=model_name,
        language=language,
        duration_seconds=duration,
        transcript_text=text,
        summary=summary,
        summary_provider=summary_provider,
        segments=segments,
        tags=[],
        collection=DEFAULT_COLLECTION,
        notes="",
    )
    persist_record(record)
    return record


def create_transcript_from_upload(file_storage, model_name: str, language: str) -> TranscriptRecord:
    audio_path, transcript_id, source_name = save_upload(file_storage)
    return create_transcript_from_audio(audio_path, transcript_id, source_name, model_name, language)


def rename_record(record_id: str, title: str) -> bool:
    cleaned = slugify_title(title)
    records = load_library()
    updated = False
    for record in records:
        if record.id == record_id:
            record.title = cleaned
            record.title_source = "manual"
            updated = True
            break
    if updated:
        save_library(records)
    return updated


def normalize_tags(tags: list[object] | str) -> list[str]:
    if isinstance(tags, str):
        raw_tags = tags.split(",")
    else:
        raw_tags = tags
    normalized = []
    seen = set()
    for tag in raw_tags:
        cleaned = " ".join(str(tag).strip().lower().split())
        cleaned = cleaned.strip(" #,;")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned[:32])
        if len(normalized) == 12:
            break
    return normalized


def normalize_collection(collection: object) -> str:
    cleaned = " ".join(str(collection or "").strip().split())
    cleaned = cleaned.strip(" /\\")
    return cleaned[:48] if cleaned else DEFAULT_COLLECTION


def normalize_speaker(speaker: object) -> str:
    cleaned = " ".join(str(speaker or "").strip().split())
    cleaned = cleaned.strip(" :,;")
    return cleaned[:40]


def build_transcript_text(segments: list[dict], fallback: str = "") -> str:
    texts = [str(segment.get("text", "")).strip() for segment in segments if str(segment.get("text", "")).strip()]
    return "\n".join(texts) if texts else fallback


def update_record_tags(record_id: str, tags: list[object] | str) -> TranscriptRecord | None:
    records = load_library()
    updated_record = None
    for record in records:
        if record.id == record_id:
            record.tags = normalize_tags(tags)
            updated_record = record
            break
    if updated_record is None:
        return None
    save_library(records)
    return updated_record


def update_record_collection(record_id: str, collection: object) -> TranscriptRecord | None:
    records = load_library()
    updated_record = None
    for record in records:
        if record.id == record_id:
            record.collection = normalize_collection(collection)
            updated_record = record
            break
    if updated_record is None:
        return None
    save_library(records)
    return updated_record


def update_record_notes(record_id: str, notes: object) -> TranscriptRecord | None:
    records = load_library()
    updated_record = None
    for record in records:
        if record.id == record_id:
            record.notes = str(notes or "").strip()[:8000]
            updated_record = record
            break
    if updated_record is None:
        return None
    save_library(records)
    return updated_record


def update_segment_text(record_id: str, segment_id: int, text: str) -> TranscriptRecord | None:
    cleaned = " ".join(text.strip().split())
    records = load_library()
    updated_record = None
    for record in records:
        if record.id != record_id:
            continue
        for segment in record.segments:
            if int(segment.get("id", -1)) == segment_id:
                segment["text"] = cleaned
                record.transcript_text = build_transcript_text(record.segments, record.transcript_text)
                updated_record = record
                break
        break
    if updated_record is None:
        return None
    save_library(records)
    updated_record.transcript_path.write_text(updated_record.transcript_text, encoding="utf-8")
    return updated_record


def update_segment_flags(record_id: str, segment_id: int, *, bookmarked: bool | None = None, highlighted: bool | None = None) -> TranscriptRecord | None:
    records = load_library()
    updated_record = None
    for record in records:
        if record.id != record_id:
            continue
        for segment in record.segments:
            if int(segment.get("id", -1)) == segment_id:
                if bookmarked is not None:
                    segment["bookmarked"] = bookmarked
                if highlighted is not None:
                    segment["highlighted"] = highlighted
                updated_record = record
                break
        break
    if updated_record is None:
        return None
    save_library(records)
    return updated_record


def update_segment_speaker(record_id: str, segment_id: int, speaker: object) -> TranscriptRecord | None:
    records = load_library()
    updated_record = None
    for record in records:
        if record.id != record_id:
            continue
        for segment in record.segments:
            if int(segment.get("id", -1)) == segment_id:
                segment["speaker"] = normalize_speaker(speaker)
                updated_record = record
                break
        break
    if updated_record is None:
        return None
    save_library(records)
    return updated_record


def markdown_export(record: TranscriptRecord) -> str:
    lines = [
        f"# {record.title}",
        "",
        f"- Date: {record.created_at[:10]}",
        f"- Duration: {record.duration_seconds:.0f}s",
        f"- Language: {record.language}",
        f"- Model: {record.model}",
    ]
    if record.tags:
        lines.append(f"- Tags: {', '.join(record.tags)}")
    lines.append(f"- Collection: {record.collection}")
    lines.extend(["", "## Summary", ""])
    lines.extend(record.summary or ["No summary available yet."])
    if record.notes:
        lines.extend(["", "## Notes", "", record.notes])
    lines.extend(["", "## Transcript", ""])
    if record.segments:
        for segment in record.segments:
            flags = []
            if segment.get("bookmarked"):
                flags.append("bookmarked")
            if segment.get("highlighted"):
                flags.append("highlighted")
            flag_label = f" _{', '.join(flags)}_" if flags else ""
            speaker_label = f" **{segment.get('speaker')}:**" if segment.get("speaker") else ""
            lines.append(f"**{segment.get('start_label', '00:00')}**{flag_label}{speaker_label} {segment.get('text', '').strip()}")
            lines.append("")
    else:
        lines.append(record.transcript_text)
    return "\n".join(lines).rstrip() + "\n"


def json_export(record: TranscriptRecord) -> dict:
    return asdict(record)


def cleaned_transcript_text(record: TranscriptRecord) -> str:
    import re

    text = record.transcript_text
    filler_patterns = [
        r"\bähm\b",
        r"\bäh\b",
        r"\bum\b",
        r"\buh\b",
        r"\bsozusagen\b",
    ]
    for pattern in filler_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def delete_record(record_id: str) -> bool:
    records = load_library()
    target = next((record for record in records if record.id == record_id), None)
    if target is None:
        return False

    remaining = [record for record in records if record.id != record_id]
    save_library(remaining)

    for path in (target.audio_path, target.transcript_path):
        if path.exists():
            path.unlink()
    return True


def delete_all_records() -> int:
    records = load_library()
    save_library([])
    deleted_count = 0
    for record in records:
        for path in (record.audio_path, record.transcript_path):
            if path.exists():
                path.unlink()
        deleted_count += 1
    return deleted_count
