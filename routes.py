from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from flask import Response, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

from config import DATA_DIR, LANGUAGES, SETTINGS_PATH, SUMMARY_MODEL_NAME, SUMMARY_PROVIDERS, TRANSCRIPT_DIR, UPLOAD_ACCEPT, UPLOAD_DIR
from dependencies import runtime_dependency_report
from errors import friendly_transcription_error
from jobs import cancel_job, get_import_batch, get_job, start_transcription_batch
from storage import (
    delete_record,
    delete_all_records,
    get_record,
    is_allowed_file,
    json_export,
    load_library,
    load_settings,
    markdown_export,
    rename_record,
    save_settings,
    save_upload,
    cleaned_transcript_text,
    update_record_collection,
    update_record_notes,
    update_record_summary,
    update_record_tags,
    update_segment_flags,
    update_segment_speaker,
    update_segment_text,
)
from summaries import (
    generate_summary,
    normalize_settings,
    slugify_title,
    format_duration,
)
from transcription import active_backend_info, media_duration_seconds, supported_models


def model_choices() -> tuple[str, ...]:
    return supported_models()


def build_record_durations(records) -> dict[str, float]:
    return {
        record.id: media_duration_seconds(record.audio_path) or record.duration_seconds
        for record in records
    }


def build_stats(records, record_durations: dict[str, float] | None = None) -> dict[str, str]:
    record_durations = record_durations or {}
    total_duration = sum(record_durations.get(item.id, item.duration_seconds) for item in records)
    return {
        "count": str(len(records)),
        "duration": format_duration(total_duration),
        "last_model": records[0].model if records else "small",
    }


def build_collections(records) -> list[dict[str, str]]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.collection] = counts.get(record.collection, 0) + 1
    names = sorted(counts, key=lambda name: (name.lower() != "inbox", name.lower()))
    return [{"name": name, "count": str(counts[name])} for name in names]


def build_tags(records) -> list[dict[str, str]]:
    counts: dict[str, int] = {}
    for record in records:
        for tag in record.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return [{"name": name, "count": str(counts[name])} for name in sorted(counts)]


def build_speakers(record) -> list[str]:
    if record is None:
        return []
    speakers = {
        str(segment.get("speaker", "")).strip()
        for segment in record.segments
        if str(segment.get("speaker", "")).strip()
    }
    return sorted(speakers, key=str.lower)


def sentence_boundary(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "…"))


def build_transcript_sections(segments: list[dict], max_duration: float | None = None) -> list[dict]:
    sections: list[dict] = []
    current_segments: list[dict] = []
    current_text = ""
    current_start = 0.0

    def flush() -> None:
        nonlocal current_segments, current_text, current_start
        if not current_segments:
            return
        end = float(current_segments[-1].get("end", current_start))
        text = " ".join(str(segment.get("text", "")).strip() for segment in current_segments).strip()
        sections.append(
            {
                "id": f"{current_segments[0].get('id', len(sections))}-{current_segments[-1].get('id', len(sections))}",
                "start": current_start,
                "end": end,
                "start_label": format_duration(current_start),
                "duration_label": format_duration(max(0.0, end - current_start)),
                "text": text,
                "segments": current_segments,
                "highlighted": any(bool(segment.get("highlighted")) for segment in current_segments),
                "bookmarked": any(bool(segment.get("bookmarked")) for segment in current_segments),
            }
        )
        current_segments = []
        current_text = ""
        current_start = 0.0

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if max_duration and start > max_duration + 0.25:
            continue
        if max_duration:
            end = min(end, max_duration)
            segment = {
                **segment,
                "end": end,
                "end_label": format_duration(end),
            }
        if not current_segments:
            current_start = start
        current_segments.append(segment)
        current_text = f"{current_text} {text}".strip()

        elapsed = end - current_start
        at_sentence_boundary = sentence_boundary(text)
        should_flush = (
            (at_sentence_boundary and (len(current_text) >= 180 or elapsed >= 14 or len(current_segments) >= 4))
            or len(current_text) >= 320
            or elapsed >= 24
        )
        if should_flush:
            flush()

    flush()
    return sections


def format_bytes(size: int) -> str:
    value = float(max(size, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def capped_dir_size(path: Path, *, max_files: int = 5000) -> str:
    if not path.exists():
        return "0 B"

    total = 0
    scanned = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
                scanned += 1
                if scanned >= max_files:
                    return f"{format_bytes(total)}+"
    except OSError:
        return "Unavailable"
    return format_bytes(total)


def build_local_info() -> list[dict[str, str]]:
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    whisper_cache = cache_root / "whisper"
    hf_cache = Path(os.environ.get("HF_HOME", cache_root / "huggingface"))
    disk_root = DATA_DIR if DATA_DIR.exists() else DATA_DIR.parent
    usage = shutil.disk_usage(disk_root)
    backend = active_backend_info()
    dependency_summary = runtime_dependency_report()
    missing_required = [item.name for item in dependency_summary if item.kind == "required" and item.status in {"missing", "unsupported"}]
    return [
        {"label": "Python target", "value": "3.11 or 3.12"},
        {"label": "Transcription backend", "value": backend.label},
        {"label": "Backend mode", "value": backend.active_device_label},
        {"label": "Supported models", "value": ", ".join(backend.supported_models)},
        {"label": "Backend setup", "value": backend.setup_hint},
        {"label": "Active cancellation", "value": "No" if not backend.can_cancel_active_job else "Yes"},
        {"label": "Required dependency health", "value": "OK" if not missing_required else f"Missing/unsupported: {', '.join(missing_required)}"},
        {"label": "Storage path", "value": str(DATA_DIR)},
        {"label": "Audio uploads", "value": str(UPLOAD_DIR)},
        {"label": "Transcript exports", "value": str(TRANSCRIPT_DIR)},
        {"label": "Settings file", "value": str(SETTINGS_PATH)},
        {"label": "Whisper model cache", "value": f"{whisper_cache} ({capped_dir_size(whisper_cache)})"},
        {"label": "Summary model", "value": SUMMARY_MODEL_NAME},
        {"label": "Summary model cache", "value": f"{hf_cache} ({capped_dir_size(hf_cache)})"},
        {"label": "Disk available", "value": format_bytes(usage.free)},
    ]


def build_model_download_info() -> list[dict[str, str]]:
    backend = active_backend_info()
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    whisper_cache = cache_root / "whisper"
    disk_root = DATA_DIR if DATA_DIR.exists() else DATA_DIR.parent
    usage = shutil.disk_usage(disk_root)
    if backend.name == "whisper.cpp":
        model_paths = dict(zip(backend.supported_models, backend.model_paths))
        return [
            {
                "name": model,
                "label": model.capitalize(),
                "status": "Ready" if model in model_paths else "Missing GGML model",
                "size": format_bytes(Path(model_paths[model]).stat().st_size) if model in model_paths and Path(model_paths[model]).exists() else "Manual download",
                "eta": "Ready now" if model in model_paths else "Set WHISPER_CPP_MODEL_DIR or WHISPER_CPP_MODEL",
                "storage": format_bytes(usage.free),
                "retry": backend.setup_hint,
                "cancel": "Active whisper.cpp jobs cannot be cancelled from this panel.",
            }
            for model in model_choices()
        ]
    expected_sizes = {
        "tiny": "~75 MB",
        "base": "~142 MB",
        "small": "~466 MB",
        "medium": "~1.5 GB",
        "turbo": "~1.6 GB",
    }
    expected_eta = {
        "tiny": "Usually under a minute",
        "base": "A few minutes",
        "small": "Several minutes on first use",
        "medium": "Longer first-use download",
        "turbo": "Longer first-use download",
    }
    model_info = []
    for model in model_choices():
        cache_file = whisper_cache / f"{model}.pt"
        cached = cache_file.exists()
        model_info.append(
            {
                "name": model,
                "label": model.capitalize(),
                "status": "Cached" if cached else "Downloads on first use",
                "size": format_bytes(cache_file.stat().st_size) if cached else expected_sizes.get(model, "Unknown"),
                "eta": "Ready now" if cached else expected_eta.get(model, "Depends on connection"),
                "storage": format_bytes(usage.free),
                "retry": "Retry by starting transcription again if the model download fails.",
                "cancel": "Cancel by closing the app before starting; active Whisper downloads cannot be cancelled here.",
            }
        )
    return model_info


def render_workspace(
    records,
    settings: dict,
    *,
    selected=None,
    default_model: str | None = None,
    default_language: str | None = None,
    error: str | None = None,
    job=None,
    import_batch=None,
):
    record_durations = build_record_durations(records)
    selected_duration_seconds = record_durations.get(selected.id, selected.duration_seconds) if selected else 0.0
    return render_template(
        "index.html",
        records=records,
        selected=selected,
        models=model_choices(),
        languages=LANGUAGES,
        summary_providers=SUMMARY_PROVIDERS,
        default_model=default_model or settings["default_model"],
        default_language=default_language or settings["default_language"],
        stats=build_stats(records, record_durations),
        local_info=build_local_info(),
        model_downloads=build_model_download_info(),
        collections=build_collections(records),
        tag_filters=build_tags(records),
        speakers=build_speakers(selected),
        transcript_sections=build_transcript_sections(selected.segments, selected_duration_seconds) if selected else [],
        selected_duration_seconds=selected_duration_seconds,
        record_durations=record_durations,
        upload_accept=UPLOAD_ACCEPT,
        settings=settings,
        error=error,
        job=job,
        import_batch=import_batch,
    )


def register_routes(app) -> None:
    @app.get("/favicon.ico")
    def favicon():
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#0f141c"/><path d="M7 16h2m3-6v12m4-16v20m4-14v8m4-12v16" stroke="#52cf7d" stroke-width="2.4" stroke-linecap="round"/></svg>"""
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/")
    def index():
        records = load_library()
        settings = load_settings()
        selected = records[0] if records else None
        return render_workspace(records, settings, selected=selected)

    @app.get("/transcripts/<record_id>")
    def transcript_detail(record_id: str):
        records = load_library()
        settings = load_settings()
        selected = next((record for record in records if record.id == record_id), None)
        if selected is None:
            abort(404)
        return render_workspace(records, settings, selected=selected)

    @app.post("/transcribe")
    def transcribe_route():
        records = load_library()
        settings = load_settings()
        model_name = request.form.get("model", settings["default_model"])
        language = request.form.get("language", settings["default_language"])
        uploads = [upload for upload in request.files.getlist("audio_file") if upload and upload.filename]
        models = model_choices()
        default_model = model_name if model_name in models else settings["default_model"]
        default_language = language if language in LANGUAGES else settings["default_language"]

        if model_name not in models or language not in LANGUAGES:
            return (
                render_workspace(
                    records,
                    settings,
                    selected=records[0] if records else None,
                    default_model=default_model,
                    default_language=default_language,
                    error="Please choose a supported model and language.",
                ),
                400,
            )

        if not uploads:
            return (
                render_workspace(
                    records=records,
                    settings=settings,
                    selected=records[0] if records else None,
                    default_model=default_model,
                    default_language=default_language,
                    error="Please choose an audio file.",
                ),
                400,
            )

        unsupported_files = [Path(upload.filename or "upload").name for upload in uploads if not is_allowed_file(upload.filename or "")]
        if unsupported_files:
            return (
                render_workspace(
                    records=records,
                    settings=settings,
                    selected=records[0] if records else None,
                    default_model=default_model,
                    default_language=default_language,
                    error=f"Unsupported file type: {', '.join(unsupported_files[:3])}.",
                ),
                400,
            )

        try:
            saved_uploads = [save_upload(upload) for upload in uploads]
            batch = start_transcription_batch(saved_uploads, model_name, language)
        except Exception as exc:
            error, status_code = friendly_transcription_error(exc)
            return (
                render_workspace(
                    records=records,
                    settings=settings,
                    selected=records[0] if records else None,
                    default_model=default_model,
                    default_language=default_language,
                    error=error,
                ),
                status_code,
            )

        redirect_url = url_for("import_detail", batch_id=batch.id)
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, "redirect_url": redirect_url, "batch": batch.as_dict()})
        return redirect(redirect_url)

    @app.get("/imports/<batch_id>")
    def import_detail(batch_id: str):
        batch = get_import_batch(batch_id)
        if batch is None:
            abort(404)
        records = load_library()
        settings = load_settings()
        selected = records[0] if records else None
        return render_workspace(records, settings, selected=selected, import_batch=batch.as_dict())

    @app.get("/imports/<batch_id>.json")
    def import_status(batch_id: str):
        batch = get_import_batch(batch_id)
        if batch is None:
            return jsonify({"ok": False, "error": "Import batch not found."}), 404
        payload = batch.as_dict()
        if payload.get("first_record_id"):
            payload["first_record_url"] = url_for("transcript_detail", record_id=payload["first_record_id"])
        return jsonify({"ok": True, "batch": payload})

    @app.get("/jobs/<job_id>")
    def job_detail(job_id: str):
        job = get_job(job_id)
        if job is None:
            abort(404)
        records = load_library()
        settings = load_settings()
        selected = records[0] if records else None
        return render_workspace(records, settings, selected=selected, job=job.as_dict())

    @app.get("/jobs/<job_id>.json")
    def job_status(job_id: str):
        job = get_job(job_id)
        if job is None:
            return jsonify({"ok": False, "error": "Job not found."}), 404
        payload = {"ok": True, "job": job.as_dict()}
        if job.record_id:
            payload["redirect_url"] = url_for("transcript_detail", record_id=job.record_id)
        return jsonify(payload)

    @app.post("/jobs/<job_id>/cancel")
    def job_cancel(job_id: str):
        if not cancel_job(job_id):
            return jsonify({"ok": False, "error": "Only queued transcription jobs can be canceled."}), 409
        return jsonify({"ok": True, "job": get_job(job_id).as_dict()})

    @app.post("/transcripts/<record_id>/rename")
    def rename_route(record_id: str):
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        if not title:
            return jsonify({"ok": False, "error": "Missing title."}), 400
        if not rename_record(record_id, title):
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "title": slugify_title(title)})

    @app.post("/transcripts/<record_id>/delete")
    def delete_route(record_id: str):
        if not delete_record(record_id):
            return jsonify({"ok": False, "error": "Record not found."}), 404

        remaining = load_library()
        next_url = url_for("transcript_detail", record_id=remaining[0].id) if remaining else url_for("index")
        return jsonify({"ok": True, "redirect_url": next_url, "remaining_count": len(remaining)})

    @app.post("/local-data/delete")
    def delete_local_data_route():
        deleted_count = delete_all_records()
        return jsonify({"ok": True, "redirect_url": url_for("index"), "deleted_count": deleted_count})

    @app.post("/transcripts/<record_id>/tags")
    def tags_route(record_id: str):
        payload = request.get_json(silent=True) or {}
        record = update_record_tags(record_id, payload.get("tags", []))
        if record is None:
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "tags": record.tags})

    @app.post("/transcripts/<record_id>/collection")
    def collection_route(record_id: str):
        payload = request.get_json(silent=True) or {}
        record = update_record_collection(record_id, payload.get("collection", ""))
        if record is None:
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "collection": record.collection})

    @app.post("/transcripts/<record_id>/notes")
    def notes_route(record_id: str):
        payload = request.get_json(silent=True) or {}
        record = update_record_notes(record_id, payload.get("notes", ""))
        if record is None:
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "notes": record.notes})

    @app.post("/transcripts/<record_id>/segments/<int:segment_id>")
    def segment_update_route(record_id: str, segment_id: int):
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"ok": False, "error": "Segment text cannot be empty."}), 400
        record = update_segment_text(record_id, segment_id, text)
        if record is None:
            return jsonify({"ok": False, "error": "Record or segment not found."}), 404
        return jsonify({"ok": True, "transcript_text": record.transcript_text})

    @app.post("/transcripts/<record_id>/segments/<int:segment_id>/flags")
    def segment_flags_route(record_id: str, segment_id: int):
        payload = request.get_json(silent=True) or {}
        record = update_segment_flags(
            record_id,
            segment_id,
            bookmarked=payload.get("bookmarked") if "bookmarked" in payload else None,
            highlighted=payload.get("highlighted") if "highlighted" in payload else None,
        )
        if record is None:
            return jsonify({"ok": False, "error": "Record or segment not found."}), 404
        segment = next((item for item in record.segments if int(item.get("id", -1)) == segment_id), {})
        return jsonify({"ok": True, "segment": segment})

    @app.post("/transcripts/<record_id>/segments/<int:segment_id>/speaker")
    def segment_speaker_route(record_id: str, segment_id: int):
        payload = request.get_json(silent=True) or {}
        record = update_segment_speaker(record_id, segment_id, payload.get("speaker", ""))
        if record is None:
            return jsonify({"ok": False, "error": "Record or segment not found."}), 404
        segment = next((item for item in record.segments if int(item.get("id", -1)) == segment_id), {})
        return jsonify({"ok": True, "segment": segment})

    @app.post("/settings")
    def settings_route():
        settings = load_settings()
        model = request.form.get("default_model", settings["default_model"])
        language = request.form.get("default_language", settings["default_language"])
        summary_provider = request.form.get("summary_provider", settings["summary_provider"])
        summary_sentences = request.form.get("summary_sentences", settings["summary_sentences"])

        save_settings(
            normalize_settings(
                {
                    "default_model": model,
                    "default_language": language,
                    "summary_provider": summary_provider,
                    "summary_sentences": summary_sentences,
                    "autoplay_on_seek": request.form.get("autoplay_on_seek") == "on",
                    "confirm_before_delete": request.form.get("confirm_before_delete") == "on",
                }
            )
        )
        return redirect(request.referrer or url_for("index"))

    @app.post("/transcripts/<record_id>/resummarize")
    def resummarize_route(record_id: str):
        settings = load_settings()
        target = get_record(record_id)
        if target is None:
            return jsonify({"ok": False, "error": "Record not found."}), 404

        summary, provider = generate_summary(target.transcript_text, target.language, settings)
        updated = update_record_summary(record_id, summary, provider)
        if updated is None:
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "summary": updated.summary, "provider": updated.summary_provider, "title": updated.title})

    @app.get("/audio/<filename>")
    def audio_file(filename: str):
        return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

    @app.get("/downloads/<record_id>.txt")
    def download_text(record_id: str):
        record = get_record(record_id)
        if record is None:
            abort(404)
        return send_from_directory(
            TRANSCRIPT_DIR,
            record.transcript_filename,
            as_attachment=True,
            download_name=f"{record.title}.txt",
        )

    @app.get("/downloads/<record_id>.md")
    def download_markdown(record_id: str):
        record = get_record(record_id)
        if record is None:
            abort(404)
        return Response(
            markdown_export(record),
            mimetype="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={record.title}.md"},
        )

    @app.get("/downloads/<record_id>.json")
    def download_json(record_id: str):
        record = get_record(record_id)
        if record is None:
            abort(404)
        return Response(
            json.dumps(json_export(record), ensure_ascii=False, indent=2) + "\n",
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={record.title}.json"},
        )

    @app.get("/downloads/<record_id>.clean.txt")
    def download_clean_text(record_id: str):
        record = get_record(record_id)
        if record is None:
            abort(404)
        return Response(
            cleaned_transcript_text(record),
            mimetype="text/plain",
            headers={"Content-Disposition": f"attachment; filename={record.title}.clean.txt"},
        )
