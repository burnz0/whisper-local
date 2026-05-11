from __future__ import annotations

import logging
import re

from config import DEFAULT_SETTINGS, SUMMARY_MODEL_NAME, SUMMARY_PROVIDERS

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:  # pragma: no cover
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None


logger = logging.getLogger(__name__)
_SUMMARY_BACKEND: dict[str, object] = {}

STOPWORDS = {
    "aber", "als", "also", "am", "an", "auch", "auf", "aus", "bei", "bin", "bist", "da", "das",
    "dass", "dein", "dem", "den", "der", "des", "die", "dir", "doch", "du", "ein", "eine", "einen",
    "einer", "einem", "er", "es", "für", "hat", "hast", "hier", "ich", "ihr", "ihm", "im", "in",
    "ist", "ja", "kein", "keine", "mal", "mein", "mich", "mir", "mit", "nicht", "nur", "oder",
    "schon", "sehr", "sich", "sie", "so", "um", "und", "uns", "vom", "von", "war", "was", "weib",
    "wenn", "wie", "wir", "wird", "wo", "zu", "zum", "zur",
    "the", "and", "for", "with", "this", "that", "from", "you", "your", "have", "has", "are", "was",
    "were", "into", "about", "they", "them", "their", "but", "not", "just", "what", "when", "where",
}


def slugify_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:80] if cleaned else "New Transcript"


def bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_settings(raw: dict | None = None) -> dict:
    from config import DEFAULT_LANGUAGE, DEFAULT_MODEL, LANGUAGES, MODELS

    source = raw or {}
    settings = dict(DEFAULT_SETTINGS)
    settings.update(source)
    settings["default_model"] = settings["default_model"] if settings["default_model"] in MODELS else DEFAULT_MODEL
    settings["default_language"] = settings["default_language"] if settings["default_language"] in LANGUAGES else DEFAULT_LANGUAGE
    settings["summary_provider"] = (
        settings["summary_provider"] if settings["summary_provider"] in SUMMARY_PROVIDERS else DEFAULT_SETTINGS["summary_provider"]
    )
    settings["summary_sentences"] = bounded_int(
        settings.get("summary_sentences"),
        DEFAULT_SETTINGS["summary_sentences"],
        minimum=1,
        maximum=6,
    )
    settings["autoplay_on_seek"] = bool(settings.get("autoplay_on_seek", True))
    settings["confirm_before_delete"] = bool(settings.get("confirm_before_delete", True))
    return settings


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
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
    picked: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in STOPWORDS or len(lowered) < 4:
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


def sentence_summary(text: str, max_items: int = 3) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ["No summary available yet."]
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    if not parts:
        return [normalized[:180]]

    tokens = re.findall(r"[a-zA-ZäöüÄÖÜß']+", normalized.lower())
    frequencies: dict[str, int] = {}
    for token in tokens:
        if len(token) < 4 or token in STOPWORDS:
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

    paragraph = " ".join(item if item.endswith((".", "!", "?")) else f"{item}." for item in cleaned)
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
        except Exception as exc:
            logger.warning("summary provider failed; falling back to extractive: %s", exc)
    return paragraphize_summary(sentence_summary(text, max_items=max_items), max_chars=320), "extractive"
