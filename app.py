#!/Users/burnz0/.transcribe-venv/bin/python3
from __future__ import annotations

import argparse
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj

try:
    import whisper
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Whisper is not installed for this Python interpreter.\n"
        "Run this app with /Users/burnz0/.transcribe-venv/bin/python app.py"
    ) from exc

try:
    from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Flask is not installed for this Python interpreter.\n"
        "Run /Users/burnz0/.transcribe-venv/bin/pip install flask"
    ) from exc

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:  # pragma: no cover
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
LIBRARY_PATH = DATA_DIR / "library.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
MODELS = ("tiny", "base", "small")
LANGUAGES = {"de": "German", "en": "English"}
DEFAULT_MODEL = "small"
DEFAULT_LANGUAGE = "de"
UPLOAD_ACCEPT = ".ogg,.mp3,.m4a,.wav,.mp4,.mpeg,.webm,.aac,.flac"
ALLOWED_EXTENSIONS = {ext.strip(".") for ext in UPLOAD_ACCEPT.split(",")}
_MODEL_CACHE: dict[str, whisper.Whisper] = {}
_SUMMARY_BACKEND: dict[str, object] = {}
SUMMARY_PROVIDERS = {
    "local_transformer": "Local German model",
    "extractive": "Fallback extractive",
}
SUMMARY_MODEL_NAME = "deutsche-telekom/mt5-small-sum-de-mit-v1"

app = Flask(__name__)

DEFAULT_SETTINGS = {
    "default_model": DEFAULT_MODEL,
    "default_language": DEFAULT_LANGUAGE,
    "summary_provider": "local_transformer",
    "summary_sentences": 3,
    "autoplay_on_seek": True,
    "confirm_before_delete": True,
}


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


def get_model(name: str) -> whisper.Whisper:
    if name not in MODELS:
        raise ValueError(f"Unsupported model: {name}")
    model = _MODEL_CACHE.get(name)
    if model is None:
        model = whisper.load_model(name)
        _MODEL_CACHE[name] = model
    return model


def is_allowed_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix in ALLOWED_EXTENSIONS


def slugify_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:80] if cleaned else "New Transcript"


def generate_title_from_summary(summary: list[str], fallback: str) -> str:
    source = summary[0] if summary else fallback
    return keyword_title_from_text(source, fallback)


def clean_generated_paragraph(text: str, max_chars: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"^(zusammenfassung|summary|titel|title)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" -•")
    if len(cleaned) > max_chars:
        shortened = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(",;:- ")
        cleaned = shortened or cleaned[:max_chars]
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def normalize_title_candidate(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip("\"'`´“”‘’«»")
    cleaned = re.sub(r"^(titel|title)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.split(r"[.!?:\n]", cleaned)[0].strip()
    cleaned = re.split(r"\s[-–]\s", cleaned)[0].strip()
    cleaned = cleaned.strip(",;:- ")
    words = cleaned.split()
    if len(words) > 6:
        cleaned = " ".join(words[:6])
    cleaned = re.sub(r"[\"'`´“”‘’«»]", "", cleaned).strip()
    return slugify_title(cleaned or fallback)


def keyword_title_from_text(text: str, fallback: str) -> str:
    stopwords = {
        "aber", "auch", "auf", "aus", "bei", "bin", "bist", "das", "dass", "dein", "dem", "den", "der",
        "des", "die", "dir", "doch", "du", "ein", "eine", "einen", "einer", "einem", "er", "es", "für",
        "hat", "hast", "hier", "ich", "ihr", "ihm", "im", "in", "ist", "ja", "kein", "keine", "mal",
        "mein", "mich", "mir", "mit", "nicht", "nur", "oder", "schon", "sehr", "sie", "so", "und",
        "uns", "von", "war", "was", "wenn", "wie", "wir", "wird", "wo", "zu", "zum", "zur",
        "the", "and", "for", "with", "this", "that", "from", "your", "have", "has", "are", "was", "were",
    }
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
    picked: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in stopwords or len(lowered) < 4:
            continue
        picked.append(word)
        if len(picked) == 4:
            break
    if not picked:
        return slugify_title(fallback)
    return slugify_title(" ".join(picked))


def summary_looks_like_transcript(summary_text: str, transcript_text: str) -> bool:
    summary_words = summary_text.lower().split()
    transcript_words = transcript_text.lower().split()
    if not summary_words or not transcript_words:
        return False
    if len(summary_words) > max(90, int(len(transcript_words) * 0.45)):
        return True

    prefix = " ".join(transcript_words[: min(len(summary_words), 80)])
    overlap = sum(1 for a, b in zip(summary_words[:80], prefix.split()[:80]) if a == b)
    return overlap >= max(18, int(min(len(summary_words), 80) * 0.55))


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def load_settings() -> dict:
    ensure_dirs()
    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    settings = dict(DEFAULT_SETTINGS)
    settings.update(raw)
    settings["default_model"] = settings["default_model"] if settings["default_model"] in MODELS else DEFAULT_MODEL
    settings["default_language"] = settings["default_language"] if settings["default_language"] in LANGUAGES else DEFAULT_LANGUAGE
    settings["summary_provider"] = (
        settings["summary_provider"] if settings["summary_provider"] in SUMMARY_PROVIDERS else DEFAULT_SETTINGS["summary_provider"]
    )
    settings["summary_sentences"] = max(1, min(6, int(settings.get("summary_sentences", 3))))
    settings["autoplay_on_seek"] = bool(settings.get("autoplay_on_seek", True))
    settings["confirm_before_delete"] = bool(settings.get("confirm_before_delete", True))
    return settings


def save_settings(settings: dict) -> None:
    ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def sentence_summary(text: str, max_items: int = 3) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ["No summary available yet."]
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    if not parts:
        return [normalized[:180]]

    stopwords = {
        "aber", "als", "also", "am", "an", "auch", "auf", "aus", "bei", "bin", "bist", "da", "das",
        "dass", "dein", "dem", "den", "der", "des", "die", "dir", "doch", "du", "ein", "eine", "einer",
        "einem", "einen", "er", "es", "für", "hat", "hast", "hier", "ich", "ihr", "ihm", "im", "in",
        "ist", "ja", "mal", "mein", "mich", "mir", "mit", "nicht", "nur", "oder", "schon", "sehr",
        "sich", "sie", "so", "um", "und", "uns", "vom", "von", "war", "was", "weib", "wenn", "wie",
        "wir", "wird", "wo", "zu", "zum", "zur",
        "the", "and", "for", "with", "this", "that", "from", "you", "your", "have", "has", "are", "was",
        "were", "into", "about", "they", "them", "their", "but", "not", "just", "what", "when", "where",
    }

    tokens = re.findall(r"[a-zA-ZäöüÄÖÜß']+", normalized.lower())
    frequencies: dict[str, int] = {}
    for token in tokens:
        if len(token) < 4 or token in stopwords:
            continue
        frequencies[token] = frequencies.get(token, 0) + 1

    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(parts):
        words = re.findall(r"[a-zA-ZäöüÄÖÜß']+", sentence.lower())
        if not words:
            continue
        score = sum(frequencies.get(word, 0) for word in words)
        score += min(len(words), 24) / 24
        if len(words) > 36:
            score *= 0.92
        scored.append((score, index, sentence))

    if not scored:
        return parts[:max_items]

    top_ranked = sorted(scored, key=lambda item: item[0], reverse=True)[:max_items]
    ordered = [sentence for _, _, sentence in sorted(top_ranked, key=lambda item: item[1])]
    summary = []
    for sentence in ordered:
        cleaned = sentence.rstrip(".!?")
        summary.append(cleaned if cleaned.endswith(":") else f"{cleaned}.")
    return summary


def chunk_text(text: str, max_chars: int = 2200) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if not sentences:
        return [cleaned[:max_chars]]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def parse_summary_output(text: str, max_items: int) -> list[str]:
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip(" -•\t")]
    if len(lines) < 2:
        lines = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    cleaned = []
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized:
            continue
        if normalized[-1] not in ".!?":
            normalized += "."
        cleaned.append(normalized)
    unique: list[str] = []
    seen = set()
    for item in cleaned:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)
    return unique[:max_items]


def paragraphize_summary(items: list[str], max_chars: int = 420) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", item).strip() for item in items if item and item.strip()]
    if not cleaned:
        return ["No summary available yet."]

    paragraph = " ".join(
        item if item.endswith((".", "!", "?")) else f"{item}."
        for item in cleaned
    )
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if len(paragraph) > max_chars:
        cut = paragraph[:max_chars].rsplit(" ", 1)[0].rstrip(",;:- ")
        if cut and cut[-1] not in ".!?":
            cut += "."
        paragraph = cut or paragraph[:max_chars].rstrip() + "."
    return [paragraph]


def get_summary_backend():
    if "backend" in _SUMMARY_BACKEND:
        return _SUMMARY_BACKEND["backend"]
    if AutoTokenizer is None or AutoModelForSeq2SeqLM is None:
        raise RuntimeError("Transformers is not installed.")

    tokenizer = AutoTokenizer.from_pretrained(SUMMARY_MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(SUMMARY_MODEL_NAME)
    _SUMMARY_BACKEND["backend"] = (tokenizer, model)
    return tokenizer, model


def run_summary_generation(tokenizer, model, prompt: str, max_new_tokens: int) -> str:
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=768)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        num_beams=4,
        no_repeat_ngram_size=3,
        length_penalty=1.0,
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)


def build_summary_prompt(text: str, language: str, item_count: int, *, aggregate: bool = False) -> str:
    if language == "de":
        if aggregate:
            return (
                "summarize: "
                "Erstelle aus diesen Notizen einen kurzen deutschen Absatz mit 2 bis 4 Sätzen. "
                "Fasse nur die Kernaussagen zusammen, abstrahiere vom Wortlaut und bleibe unter 320 Zeichen.\n\n"
                f"{text}"
            )
        return (
            "summarize: "
            "Fasse diesen Abschnitt eines Gesprächstranskripts in einem kurzen deutschen Satz zusammen. "
            "Nur Inhalt, keine Wiederholung des Wortlauts.\n\n"
            f"{text}"
        )
    if aggregate:
        return (
            "summarize: "
            f"Write one short paragraph in {language} from these notes. Use 2 to 4 sentences, keep only the key points, stay under 320 characters.\n\n{text}"
        )
    return (
        "summarize: "
        f"Summarize this transcript section in one short sentence in {language}. Focus on substance and avoid repeating the wording.\n\n{text}"
    )


def build_title_prompt(summary_text: str, language: str) -> str:
    if language == "de":
        return (
            "summarize: "
            "Erzeuge einen extrem kurzen deutschen Titel mit höchstens 5 Wörtern für diese Zusammenfassung. "
            "Kein vollständiger Satz. Keine Anführungszeichen. Keine Erklärung. Nur den Titel ausgeben.\n\n"
            f"{summary_text}"
        )
    return (
        "summarize: "
        "Generate an extremely short title with at most 5 words for this summary. "
        "No full sentence. No quotes. Return only the title.\n\n"
        f"{summary_text}"
    )


def generate_title_with_local_model(summary: list[str], language: str, fallback: str) -> str:
    tokenizer, model = get_summary_backend()
    prompt = build_title_prompt(" ".join(summary), language)
    decoded = run_summary_generation(tokenizer, model, prompt, max_new_tokens=24)
    candidate = normalize_title_candidate(decoded, fallback)
    if len(candidate.split()) > 6 or len(candidate) > 48:
        return keyword_title_from_text(" ".join(summary), fallback)
    return candidate


def summarize_with_local_model(text: str, language: str, max_items: int) -> list[str]:
    tokenizer, model = get_summary_backend()
    chunks = chunk_text(text)
    if not chunks:
        return ["No summary available yet."]

    chunk_summaries: list[str] = []
    for chunk in chunks:
        prompt = build_summary_prompt(chunk, language, 1, aggregate=False)
        decoded = run_summary_generation(tokenizer, model, prompt, max_new_tokens=90)
        compact = clean_generated_paragraph(decoded, max_chars=160)
        if compact:
            chunk_summaries.append(compact)

    if len(chunks) == 1:
        one = paragraphize_summary(chunk_summaries[:max_items], max_chars=320)
        if summary_looks_like_transcript(one[0], text):
            return paragraphize_summary(sentence_summary(text, max_items=max_items), max_chars=320)
        return one

    aggregate_round = chunk_summaries
    while len(aggregate_round) > max_items:
        next_round: list[str] = []
        for start in range(0, len(aggregate_round), 8):
            batch = aggregate_round[start : start + 8]
            combined = " ".join(batch)
            prompt = build_summary_prompt(combined, language, max_items, aggregate=True)
            decoded = run_summary_generation(tokenizer, model, prompt, max_new_tokens=180)
            compact = clean_generated_paragraph(decoded, max_chars=220)
            next_round.extend([compact] if compact else batch[:1])
        if next_round == aggregate_round:
            break
        aggregate_round = next_round

    final_prompt = build_summary_prompt(" ".join(aggregate_round), language, max_items, aggregate=True)
    final_text = run_summary_generation(tokenizer, model, final_prompt, max_new_tokens=180)
    final_paragraph = clean_generated_paragraph(final_text, max_chars=320)
    if not final_paragraph or summary_looks_like_transcript(final_paragraph, text):
        return paragraphize_summary(sentence_summary(text, max_items=max_items), max_chars=320)
    return [final_paragraph]


def generate_summary(text: str, language: str, settings: dict) -> tuple[list[str], str]:
    provider = settings["summary_provider"]
    max_items = int(settings["summary_sentences"])
    if provider == "local_transformer":
        try:
            return summarize_with_local_model(text, language, max_items), provider
        except Exception:
            pass
    return paragraphize_summary(sentence_summary(text, max_items=max_items), max_chars=320), "extractive"


def transcribe_file(file_path: Path, model_name: str, language: str) -> tuple[str, list[dict], float]:
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
    return text, segments, duration


def load_library() -> list[TranscriptRecord]:
    ensure_dirs()
    settings = load_settings()
    raw = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    records = []
    library_changed = False
    for item in raw:
        transcript_text = str(item.get("transcript_text", ""))
        stored_provider = str(item.get("summary_provider", ""))
        stored_summary = item.get("summary") or []
        item["title_source"] = str(item.get("title_source", "manual"))
        if not stored_provider or not stored_summary:
            summary, used_provider = generate_summary(transcript_text, str(item.get("language", DEFAULT_LANGUAGE)), settings)
            item["summary"] = summary
            item["summary_provider"] = used_provider
            if item["title_source"] == "auto":
                item["title"] = generate_title_from_summary(summary, Path(str(item.get("filename", ""))).stem)
            library_changed = True
        else:
            item["summary"] = stored_summary
            item["summary_provider"] = stored_provider
        records.append(TranscriptRecord(**item))
    if library_changed:
        save_library(records)
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def save_library(records: list[TranscriptRecord]) -> None:
    ensure_dirs()
    payload = [asdict(record) for record in records]
    LIBRARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def build_stats(records: list[TranscriptRecord]) -> dict[str, str]:
    total_duration = sum(item.duration_seconds for item in records)
    return {
        "count": str(len(records)),
        "duration": format_duration(total_duration),
        "last_model": records[0].model if records else DEFAULT_MODEL,
    }


def create_transcript_from_upload(file_storage, model_name: str, language: str) -> TranscriptRecord:
    ensure_dirs()
    settings = load_settings()
    source_name = Path(file_storage.filename or "upload").name
    if not is_allowed_file(source_name):
        raise ValueError("This file format is not supported yet.")

    transcript_id = uuid.uuid4().hex[:12]
    stored_filename = f"{transcript_id}{Path(source_name).suffix.lower()}"
    audio_path = UPLOAD_DIR / stored_filename

    with audio_path.open("wb") as target:
        copyfileobj(file_storage.stream, target)

    text, segments, duration = transcribe_file(audio_path, model_name=model_name, language=language)
    title = slugify_title(Path(source_name).stem.replace("_", " "))
    created_at = datetime.now().isoformat(timespec="seconds")
    transcript_filename = f"{transcript_id}.txt"
    summary, summary_provider = generate_summary(text, language=language, settings=settings)
    generated_title = title
    if summary_provider == "local_transformer":
        try:
            generated_title = generate_title_with_local_model(summary, language, title)
        except Exception:
            generated_title = generate_title_from_summary(summary, title)
    else:
        generated_title = generate_title_from_summary(summary, title)

    record = TranscriptRecord(
        id=transcript_id,
        title=generated_title,
        title_source="auto",
        filename=source_name,
        stored_filename=stored_filename,
        transcript_filename=transcript_filename,
        created_at=created_at,
        model=model_name,
        language=language,
        duration_seconds=duration,
        transcript_text=text,
        summary=summary,
        summary_provider=summary_provider,
        segments=segments,
    )
    persist_record(record)
    return record


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


@app.get("/")
def index():
    records = load_library()
    settings = load_settings()
    selected = records[0] if records else None
    return render_template(
        "index.html",
        records=records,
        selected=selected,
        models=MODELS,
        languages=LANGUAGES,
        summary_providers=SUMMARY_PROVIDERS,
        default_model=settings["default_model"],
        default_language=settings["default_language"],
        stats=build_stats(records),
        upload_accept=UPLOAD_ACCEPT,
        settings=settings,
        error=None,
    )


@app.get("/transcripts/<record_id>")
def transcript_detail(record_id: str):
    records = load_library()
    settings = load_settings()
    selected = next((record for record in records if record.id == record_id), None)
    if selected is None:
        abort(404)
    return render_template(
        "index.html",
        records=records,
        selected=selected,
        models=MODELS,
        languages=LANGUAGES,
        summary_providers=SUMMARY_PROVIDERS,
        default_model=settings["default_model"],
        default_language=settings["default_language"],
        stats=build_stats(records),
        upload_accept=UPLOAD_ACCEPT,
        settings=settings,
        error=None,
    )


@app.post("/transcribe")
def transcribe_route():
    records = load_library()
    settings = load_settings()
    model_name = request.form.get("model", settings["default_model"])
    language = request.form.get("language", settings["default_language"])
    upload = request.files.get("audio_file")

    if upload is None or not upload.filename:
        return (
            render_template(
                "index.html",
                records=records,
                selected=records[0] if records else None,
                models=MODELS,
                languages=LANGUAGES,
                summary_providers=SUMMARY_PROVIDERS,
                default_model=model_name if model_name in MODELS else DEFAULT_MODEL,
                default_language=language if language in LANGUAGES else DEFAULT_LANGUAGE,
                stats=build_stats(records),
                upload_accept=UPLOAD_ACCEPT,
                settings=settings,
                error="Please choose an audio file.",
            ),
            400,
        )

    try:
        record = create_transcript_from_upload(upload, model_name=model_name, language=language)
    except Exception as exc:
        return (
            render_template(
                "index.html",
                records=records,
                selected=records[0] if records else None,
                models=MODELS,
                languages=LANGUAGES,
                summary_providers=SUMMARY_PROVIDERS,
                default_model=model_name if model_name in MODELS else DEFAULT_MODEL,
                default_language=language if language in LANGUAGES else DEFAULT_LANGUAGE,
                stats=build_stats(records),
                upload_accept=UPLOAD_ACCEPT,
                settings=settings,
                error=f"Transcription failed: {exc}",
            ),
            500,
        )

    return redirect(url_for("transcript_detail", record_id=record.id))


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


@app.post("/settings")
def settings_route():
    settings = load_settings()
    model = request.form.get("default_model", settings["default_model"])
    language = request.form.get("default_language", settings["default_language"])
    summary_provider = request.form.get("summary_provider", settings["summary_provider"])
    summary_sentences = request.form.get("summary_sentences", settings["summary_sentences"])

    settings["default_model"] = model if model in MODELS else DEFAULT_MODEL
    settings["default_language"] = language if language in LANGUAGES else DEFAULT_LANGUAGE
    settings["summary_provider"] = (
        summary_provider if summary_provider in SUMMARY_PROVIDERS else DEFAULT_SETTINGS["summary_provider"]
    )
    settings["summary_sentences"] = max(1, min(6, int(summary_sentences)))
    settings["autoplay_on_seek"] = request.form.get("autoplay_on_seek") == "on"
    settings["confirm_before_delete"] = request.form.get("confirm_before_delete") == "on"

    save_settings(settings)
    return redirect(request.referrer or url_for("index"))


@app.post("/transcripts/<record_id>/resummarize")
def resummarize_route(record_id: str):
    settings = load_settings()
    records = load_library()
    target = next((record for record in records if record.id == record_id), None)
    if target is None:
        return jsonify({"ok": False, "error": "Record not found."}), 404

    summary, provider = generate_summary(target.transcript_text, target.language, settings)
    next_title = target.title
    for record in records:
        if record.id == record_id:
            record.summary = summary
            record.summary_provider = provider
            if record.title_source == "auto":
                fallback_title = Path(record.filename).stem
                if provider == "local_transformer":
                    try:
                        record.title = generate_title_with_local_model(summary, record.language, fallback_title)
                    except Exception:
                        record.title = generate_title_from_summary(summary, fallback_title)
                else:
                    record.title = generate_title_from_summary(summary, fallback_title)
                next_title = record.title
            else:
                next_title = record.title
            break
    save_library(records)
    return jsonify({"ok": True, "summary": summary, "provider": provider, "title": next_title})


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


def main() -> None:
    ensure_dirs()
    parser = argparse.ArgumentParser(description="Local audio transcription web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    print(f"Open http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
