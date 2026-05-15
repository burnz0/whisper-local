from __future__ import annotations

import logging
import re

from analysis import ExtractionRequest, ExtractionResult, SummaryRequest, SummaryResult
from config import (
    DEFAULT_SETTINGS,
    FAST_INSTRUCTION_MODEL_NAME,
    INSTRUCTION_SUMMARY_MODEL_NAME,
    QUALITY_INSTRUCTION_MODEL_NAME,
    SUMMARY_MODEL_NAME,
    SUMMARY_PROVIDERS,
)

try:
    from transformers import AutoModelForCausalLM, AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:  # pragma: no cover
    AutoModelForCausalLM = None
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None


logger = logging.getLogger(__name__)
_SUMMARY_BACKEND: dict[str, object] = {}

STOPWORDS = {
    "aber", "als", "also", "am", "an", "auch", "auf", "aus", "bei", "bin", "bist", "da", "das",
    "dass", "dein", "dem", "den", "der", "des", "die", "dir", "doch", "du", "ein", "eine", "einen",
    "einer", "einem", "er", "es", "für", "hat", "hast", "hier", "ich", "ihr", "ihm", "im", "in",
    "ist", "ja", "kein", "keine", "mal", "mein", "mich", "mir", "mit", "nicht", "nur", "oder",
    "schon", "sehr", "sich", "sie", "so", "sowie", "um", "und", "uns", "vom", "von", "war", "was", "weib",
    "wenn", "wie", "wir", "wird", "wo", "zu", "zum", "zur",
    "abschnitt", "aussage", "beschreibt", "dieser", "diese", "dieses", "gespraech", "gespräch",
    "dinge", "geht", "gehts", "genau", "gestern", "halt", "kernaussage", "kurzfassung", "punkt", "punkte", "satz", "thema", "transkript", "wichtig",
    "wichtige", "wichtiger", "wichtigen",
    "the", "and", "for", "with", "this", "that", "from", "you", "your", "have", "has", "are", "was",
    "were", "into", "about", "they", "them", "their", "but", "not", "just", "what", "when", "where",
    "summary", "transcript", "conversation", "section", "sentence", "important", "topic", "point",
}

MIN_SUMMARY_WORDS = 5
PENDING_SUMMARY = "Summary pending."
MAX_EXTRACTIVE_SENTENCE_WORDS = 24

GERMAN_CONCEPTS = [
    ("Wertschätzung", r"\b(toll|klug|gebildet|erfolgreich|zuverlaessig|zuverlässig|schätze|schaetze|sozial|zielstrebig)\b"),
    ("Unsicherheit", r"\b(unsicher|unsicherheit|erschütter|erschuettern|nichtantwort|feuerwerk|ablehn)\w*\b"),
    ("Kontakt und gemeinsame Pläne", r"\b(kontakt|sehen|zweimal|pläne|plaene|urlaub|zusammen|nähe|naehe)\w*\b"),
    ("offene Kommunikation", r"\b(kommunikation|fragen|verstehen|verständnis|verstaendnis|interessiert|erklären|erklaeren|abklär|abklaer)\w*\b"),
    ("unterschiedliche Vorstellungen", r"\b(unterschied|verschieden|vorstellungen|meinungen|vorgehensweise|welt)\w*\b"),
    ("Beziehung und Verbindung", r"\b(verbindung|beziehung|zwischen zwei menschen)\b"),
    ("nächste Schritte", r"\b(nächste|naechste|follow-up|aufgabe|todo|termin|planen|klären|klaeren)\w*\b"),
]

ENGLISH_CONCEPTS = [
    ("appreciation", r"\b(appreciat|value|smart|successful|reliable|social|driven)\w*\b"),
    ("uncertainty", r"\b(uncertain|insecure|rejection|unanswered|anxious)\w*\b"),
    ("contact and shared plans", r"\b(contact|plans|vacation|together|closeness|wish)\w*\b"),
    ("open communication", r"\b(communication|ask|understand|explain|clarify|interested)\w*\b"),
    ("different expectations", r"\b(different|expectations|opinions|perspective|world)\w*\b"),
    ("relationship context", r"\b(connection|relationship|between two people)\b"),
    ("next steps", r"\b(next|follow-up|task|todo|schedule|plan|clarify)\w*\b"),
]


def slugify_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned[:80] if cleaned else "New Transcript"


def bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_settings(raw: dict | None = None) -> dict:
    from config import DEFAULT_LANGUAGE, DEFAULT_MODEL, LANGUAGES, MODELS
    from transcription import supported_models

    source = raw or {}
    settings = dict(DEFAULT_SETTINGS)
    settings.update(source)
    models = supported_models() or MODELS
    settings["default_model"] = settings["default_model"] if settings["default_model"] in models else DEFAULT_MODEL
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
    for item in summary:
        if is_pending_summary(item) or low_confidence_summary_text(item, "de"):
            continue
        title = sentence_title_from_text(item, fallback)
        if title.lower() != slugify_title(fallback).lower():
            return title
    return sentence_title_from_text(fallback, fallback)


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


def normalize_transcript_for_summary(text: str) -> str:
    cleaned = re.sub(r"\[[^\]]{1,80}\]", " ", text)
    cleaned = re.sub(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\b(?:ähm+|äh+|hm+|mhm+|uh+|um+)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def split_transcript_units(text: str) -> list[str]:
    normalized = normalize_transcript_for_summary(text)
    if not normalized:
        return []

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    if len(parts) > 1:
        return parts

    clauses = [part.strip() for part in re.split(r"\s(?:aber|und dann|danach|außerdem|deshalb|weil|wenn|also)\s", normalized) if part.strip()]
    if len(clauses) > 1:
        parts = clauses
    else:
        words = normalized.split()
        parts = [" ".join(words[start : start + 32]) for start in range(0, len(words), 32)]

    units = []
    buffer = ""
    for part in parts:
        candidate = f"{buffer} {part}".strip()
        if len(candidate.split()) < 10:
            buffer = candidate
            continue
        units.append(candidate)
        buffer = ""
    if buffer:
        if units:
            units[-1] = f"{units[-1]} {buffer}".strip()
        else:
            units.append(buffer)
    return units


def join_human_list(items: list[str], language: str) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    connector = " sowie " if language == "de" else " and "
    return ", ".join(items[:-1]) + connector + items[-1]


def domain_terms(text: str, limit: int = 3) -> list[str]:
    words = []
    for match in re.finditer(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{3,}\b", text):
        prefix = text[: match.start()].rstrip()
        if not prefix or prefix.endswith((".", "!", "?", "\n")):
            continue
        words.append(match.group(0))
    terms: dict[str, dict[str, object]] = {}
    for index, word in enumerate(words):
        lowered = word.lower()
        if lowered in STOPWORDS or lowered in {"Alex"}:
            continue
        entry = terms.setdefault(lowered, {"word": word, "count": 0, "index": index})
        entry["count"] = int(entry["count"]) + 1
    ranked = sorted(terms.values(), key=lambda item: (-int(item["count"]), int(item["index"])))
    return [str(item["word"]) for item in ranked[:limit]]


def candidate_topic_terms(text: str, limit: int = 4) -> list[str]:
    normalized = normalize_transcript_for_summary(text)
    terms: dict[str, dict[str, object]] = {}
    for index, match in enumerate(re.finditer(r"\b[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]{3,}\b", normalized)):
        word = match.group(0).strip("-")
        lowered = word.lower()
        if lowered in STOPWORDS or len(lowered) < 4:
            continue
        if re.search(r"\d", word):
            continue
        entry = terms.setdefault(lowered, {"word": word, "count": 0, "index": index, "capitalized": 0})
        entry["count"] = int(entry["count"]) + 1
        if word[:1].isupper() or "-" in word:
            entry["capitalized"] = int(entry["capitalized"]) + 1

    ranked = sorted(
        terms.values(),
        key=lambda item: (-int(item["count"]) - int(item["capitalized"]), int(item["index"])),
    )
    picked = []
    for item in ranked:
        word = str(item["word"])
        if any(word.lower() in existing.lower() or existing.lower() in word.lower() for existing in picked):
            continue
        picked.append(word)
        if len(picked) == limit:
            break
    return picked


def topic_summary_from_terms(text: str, language: str, max_items: int = 3) -> list[str]:
    terms = candidate_topic_terms(text, limit=4 if max_items > 1 else 3)
    if len(terms) < 2:
        return []
    if language == "de":
        return [f"Es geht um {join_human_list(terms, language)}."]
    return [f"It covers {join_human_list(terms, language)}."]


def detected_concepts(text: str, language: str, limit: int = 4) -> list[str]:
    normalized = normalize_transcript_for_summary(text).lower()
    concept_patterns = GERMAN_CONCEPTS if language == "de" else ENGLISH_CONCEPTS
    hits: list[tuple[int, str]] = []
    for label, pattern in concept_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            hits.append((match.start(), label))
    return [label for _, label in sorted(hits, key=lambda item: item[0])][:limit]


def concept_summary(text: str, language: str, max_items: int = 3) -> list[str]:
    concept_limit = 2 if max_items <= 1 else 4 if max_items <= 3 else 6
    concepts = detected_concepts(text, language, limit=concept_limit)
    if language == "de" and concepts == ["nächste Schritte"]:
        concepts = domain_terms(text) + concepts
    if not concepts:
        return []
    if language == "de":
        first_count = 2 if max_items <= 1 else 4
        summary = [f"Es geht um {join_human_list(concepts[:first_count], language)}."]
        if max_items >= 4 and len(concepts) > first_count:
            summary.append(f"Außerdem geht es um {join_human_list(concepts[first_count:], language)}.")
        return summary[:max_items]
    first_count = 2 if max_items <= 1 else 4
    summary = [f"It covers {join_human_list(concepts[:first_count], language)}."]
    if max_items >= 4 and len(concepts) > first_count:
        summary.append(f"It also covers {join_human_list(concepts[first_count:], language)}.")
    return summary[:max_items]


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


def sentence_title_from_text(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip("\"'`´“”‘’«»")
    cleaned = re.sub(r"^(zusammenfassung|summary|titel|title)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(es geht um|it covers)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(in diesem|in dieser|der abschnitt|dieser abschnitt)\s+", "", cleaned, flags=re.IGNORECASE)
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0].strip()
    first_sentence = first_sentence.rstrip(".!?").strip(",;:- ")
    if "," in first_sentence or re.search(r"\s(sowie|and)\s", first_sentence, flags=re.IGNORECASE):
        parts = [
            part.strip()
            for part in re.split(r"\s+sowie\s+|\s+and\s+|,", first_sentence, flags=re.IGNORECASE)
            if part.strip()
        ]
        if len(parts) > 2:
            first_sentence = ", ".join(parts[:2])
    if len(first_sentence.split()) < 3:
        return keyword_title_from_text(first_sentence, fallback)
    if len(first_sentence) > 64:
        first_sentence = first_sentence[:64].rsplit(" ", 1)[0].rstrip(",;:- ")
    return slugify_title(first_sentence or fallback)


def keyword_title_from_text(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]*", text)
    candidates: dict[str, dict[str, object]] = {}
    for index, word in enumerate(words):
        lowered = word.lower()
        if lowered in STOPWORDS or len(lowered) < 4:
            continue
        canonical = lowered.strip("-")
        entry = candidates.setdefault(canonical, {"word": word.strip("-"), "count": 0, "index": index})
        entry["count"] = int(entry["count"]) + 1
    ranked = sorted(
        candidates.values(),
        key=lambda item: (-int(item["count"]), int(item["index"])),
    )
    picked = [str(item["word"]) for item in ranked[:4]]
    if not picked:
        return slugify_title(fallback)
    return slugify_title(" ".join(picked))


def is_pending_summary(text: str) -> bool:
    return re.sub(r"\s+", " ", text).strip().lower().rstrip(".") in {
        PENDING_SUMMARY.lower().rstrip("."),
        "summary unavailable",
        "no summary available yet",
        "keine zusammenfassung verfügbar",
    }


def meaningful_word_details(text: str) -> list[tuple[str, bool]]:
    details = []
    for word in re.findall(r"\b[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]*\b", text):
        normalized = word.lower().strip("-")
        if len(normalized) < 4 or normalized in STOPWORDS:
            continue
        details.append((word, word[:1].isupper()))
    return details


def low_confidence_summary_text(text: str, language: str) -> bool:
    cleaned = normalize_transcript_for_summary(text)
    if not cleaned:
        return True
    if detected_concepts(cleaned, language):
        return False
    details = meaningful_word_details(cleaned)
    if not details:
        return True
    capitalized_count = sum(1 for _word, is_capitalized in details if is_capitalized)
    lowercase_count = len(details) - capitalized_count
    starts_with_topic_shell = bool(re.match(r"^(es geht um|it covers)\b", cleaned, flags=re.IGNORECASE))
    if starts_with_topic_shell and capitalized_count >= 2 and lowercase_count == 0:
        return True
    if len(details) <= 5 and capitalized_count >= max(2, len(details) - 1) and lowercase_count == 0:
        return True
    return False


def summary_looks_like_transcript(summary_text: str, transcript_text: str) -> bool:
    summary_cleaned = normalize_transcript_for_summary(summary_text).lower()
    transcript_cleaned = normalize_transcript_for_summary(transcript_text).lower()
    summary_words = summary_cleaned.split()
    transcript_words = transcript_cleaned.split()
    if not summary_words or not transcript_words:
        return False
    if len(summary_words) > 18 and summary_cleaned in transcript_cleaned:
        return True
    if len(summary_words) > max(90, int(len(transcript_words) * 0.45)):
        return True

    prefix = " ".join(transcript_words[: min(len(summary_words), 80)])
    overlap = sum(1 for a, b in zip(summary_words[:80], prefix.split()[:80]) if a == b)
    return overlap >= max(18, int(min(len(summary_words), 80) * 0.55))


def summary_looks_bad(summary_text: str, transcript_text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", summary_text).strip()
    if len(cleaned.split()) < MIN_SUMMARY_WORDS:
        return True
    lowered = cleaned.lower()
    words = lowered.split()
    if len(words) >= 2 and words[0] == words[1]:
        return True
    if lowered in {"no summary available yet.", "keine zusammenfassung verfügbar."}:
        return True
    if re.search(r"\b(zusammenfassung|summary|titel|title)\s*:", lowered):
        return True
    if re.search(r"\b(gespraechstranskript|gesprächstranskript|transkript|satz|satzs|sentence)\b", lowered):
        return True
    return summary_looks_like_transcript(cleaned, transcript_text)


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sentence_summary(text: str, max_items: int = 3, language: str = "de") -> list[str]:
    normalized = normalize_transcript_for_summary(text)
    if not normalized:
        return [PENDING_SUMMARY]
    if low_confidence_summary_text(normalized, language):
        return [PENDING_SUMMARY]
    concepts = concept_summary(normalized, language, max_items=max_items)
    if concepts:
        return concepts[:max_items]
    topic_summary = topic_summary_from_terms(normalized, language, max_items=max_items)
    if topic_summary:
        return topic_summary[:max_items]
    parts = split_transcript_units(normalized)
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
        cleaned = clean_generated_paragraph(sentence, max_chars=180)
        if cleaned and len(cleaned.split()) <= MAX_EXTRACTIVE_SENTENCE_WORDS and not summary_looks_bad(cleaned, normalized):
            summary.append(cleaned)
    if summary:
        return summary
    return [PENDING_SUMMARY]


def chunk_text(text: str, max_chars: int = 2200) -> list[str]:
    cleaned = normalize_transcript_for_summary(text)
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
    text = re.sub(r"^\s*(zusammenfassung|summary)\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip(" -•\t")]
    if len(lines) < 2:
        lines = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    cleaned = []
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        normalized = re.sub(r"^(?:satz|sentence)\s*\d+\s*:\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^(hauptthema|entscheidungen?|risiken?|nächste schritte|naechste schritte|next steps)\s*:\s*", "", normalized, flags=re.IGNORECASE)
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


def parse_extraction_output(text: str) -> tuple[list[str], list[str]]:
    cleaned = text.strip()
    if not cleaned:
        return [], []
    import json

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        action_items = payload.get("action_items", [])
        entities = payload.get("entities", [])
        return normalize_extraction_items(action_items, limit=8), normalize_extraction_items(entities, limit=16)

    action_items = []
    entities = []
    current = ""
    for line in cleaned.splitlines():
        normalized = line.strip(" -•\t")
        lowered = normalized.lower()
        if not normalized:
            continue
        if lowered.startswith(("action items", "actions", "aufgaben", "to-dos", "todos")):
            current = "action_items"
            normalized = normalized.split(":", 1)[-1].strip() if ":" in normalized else ""
        elif lowered.startswith(("entities", "personen", "entitaeten", "entitäten", "names")):
            current = "entities"
            normalized = normalized.split(":", 1)[-1].strip() if ":" in normalized else ""
        if not normalized:
            continue
        if current == "entities":
            entities.extend(part.strip() for part in normalized.split(","))
        else:
            action_items.append(normalized)
    return normalize_extraction_items(action_items, limit=8), normalize_extraction_items(entities, limit=16)


def normalize_extraction_items(items: object, *, limit: int) -> list[str]:
    if not isinstance(items, list):
        items = [items]
    normalized = []
    seen = set()
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "")).strip(" -•\t.,;:")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text[:160])
        if len(normalized) == limit:
            break
    return normalized


ACTION_ITEM_PATTERNS = {
    "de": r"\b(muss|muessen|müssen|soll|sollen|todo|aufgabe|erinner|klaeren|klären|vorbereiten|verteilen|bis)\b",
    "en": r"\b(must|should|need(?:s)? to|todo|task|follow up|prepare|assign|clarify|by)\b",
}


def extract_action_items_heuristic(text: str, language: str, limit: int = 8) -> list[str]:
    units = split_transcript_units(text)
    pattern = ACTION_ITEM_PATTERNS.get(language, ACTION_ITEM_PATTERNS["en"])
    candidates = []
    for unit in units:
        if re.search(pattern, unit, flags=re.IGNORECASE):
            candidates.append(clean_generated_paragraph(unit, max_chars=160))
    return normalize_extraction_items(candidates, limit=limit)


def extract_entities_heuristic(text: str, limit: int = 16) -> list[str]:
    cleaned = normalize_transcript_for_summary(text)
    candidates = []
    for match in re.finditer(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{2,}(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{2,}){0,2}\b", cleaned):
        value = match.group(0).strip()
        if value.lower() in STOPWORDS or value.lower().startswith(("ich ", "das ", "die ", "der ", "this ", "the ")):
            continue
        candidates.append(value)
    return normalize_extraction_items(candidates, limit=limit)


def build_instruction_extraction_prompt(text: str, language: str) -> str:
    if language == "de":
        return (
            "Extrahiere aus dem Transkript konkrete Aufgaben und wichtige Entitaeten.\n"
            "Antworte nur als kompaktes JSON mit den Schluesseln action_items und entities.\n"
            "action_items: kurze deutsche Aufgaben, keine erfundenen Punkte.\n"
            "entities: Personen, Organisationen, Produkte, Orte oder wichtige Eigennamen.\n\n"
            f"Transkript:\n{text[:3500]}\n\nJSON:"
        )
    return (
        "Extract concrete action items and important entities from the transcript.\n"
        "Return only compact JSON with keys action_items and entities.\n"
        "action_items: short tasks, no invented items.\n"
        "entities: people, organizations, products, places, or important named things.\n\n"
        f"Transcript:\n{text[:3500]}\n\nJSON:"
    )


def extract_with_instruction_model(text: str, language: str, model_name: str = INSTRUCTION_SUMMARY_MODEL_NAME) -> tuple[list[str], list[str]]:
    tokenizer, model = get_instruction_backend(model_name)
    cleaned = normalize_transcript_for_summary(text)
    if not cleaned:
        return [], []
    prompt = build_instruction_extraction_prompt(cleaned, language)
    decoded = run_instruction_generation(tokenizer, model, prompt, max_new_tokens=220)
    action_items, entities = parse_extraction_output(decoded)
    if not action_items and not entities:
        raise RuntimeError("local instruction extraction returned no usable items")
    return action_items, entities


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
    if "seq2seq_backend" in _SUMMARY_BACKEND:
        return _SUMMARY_BACKEND["seq2seq_backend"]
    if AutoTokenizer is None or AutoModelForSeq2SeqLM is None:
        raise RuntimeError("Transformers is not installed.")
    try:
        import google.protobuf  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Experimental German mT5 unavailable: protobuf is not installed.") from exc

    tokenizer = AutoTokenizer.from_pretrained(SUMMARY_MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(SUMMARY_MODEL_NAME)
    _SUMMARY_BACKEND["seq2seq_backend"] = (tokenizer, model)
    return tokenizer, model


def get_instruction_backend(model_name: str = INSTRUCTION_SUMMARY_MODEL_NAME):
    cache_key = f"instruction_backend:{model_name}"
    if cache_key in _SUMMARY_BACKEND:
        return _SUMMARY_BACKEND[cache_key]
    if AutoTokenizer is None or AutoModelForCausalLM is None:
        raise RuntimeError("Transformers is not installed.")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name, dtype="auto")
    _SUMMARY_BACKEND[cache_key] = (tokenizer, model)
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


def build_instruction_summary_prompt(text: str, language: str, item_count: int) -> str:
    density = "1 sehr kurzer Satz" if item_count <= 1 else f"{min(item_count, 5)} kurze Saetze"
    if language == "de":
        return (
            "Fasse das folgende Transkript auf Deutsch zusammen.\n"
            f"Schreibe {density} als normale Saetze, nicht als Liste.\n"
            "Keine Ueberschriften. Keine Zitate. Keine Wiederholung des Wortlauts. Keine Meta-Saetze.\n"
            "Nenne nur Hauptthema, wichtige Aussagen, Entscheidungen, Risiken und naechste Schritte.\n"
            "Gib nur die Zusammenfassung aus.\n\n"
            f"Transkript:\n{text}\n\nZusammenfassung:"
        )
    return (
        f"Summarize the following transcript in {min(item_count, 5)} short sentence(s).\n"
        "No quotes. Do not repeat the wording. No meta commentary.\n"
        "Only mention the main topic, important points, decisions, risks, and next steps.\n"
        "Return only the summary.\n\n"
        f"Transcript:\n{text}\n\nSummary:"
    )


def run_instruction_generation(tokenizer, model, prompt: str, max_new_tokens: int) -> str:
    messages = [{"role": "user", "content": prompt}]
    try:
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(rendered, return_tensors="pt", truncation=True, max_length=6144)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )
    decoded = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
    decoded = re.sub(r"<think>.*?</think>", "", decoded, flags=re.DOTALL | re.IGNORECASE)
    return decoded.strip()


def build_summary_prompt(text: str, language: str, item_count: int, *, aggregate: bool = False) -> str:
    if language == "de":
        if aggregate:
            return (
                "summarize: "
                "Schreibe eine sachliche deutsche Kurzfassung aus diesen Notizen. "
                "Nenne nur konkrete Themen, Entscheidungen und naechste Schritte. "
                "Keine Einleitung, keine Meta-Saetze, keine erfundenen Namen. Maximal 4 kurze Saetze.\n\n"
                f"{text}"
            )
        return (
            "summarize: "
            "Fasse diesen Abschnitt eines Gespraechstranskripts in einem konkreten deutschen Satz zusammen. "
            "Nur die Kernaussage, keine Wiederholung des Wortlauts, keine erfundenen Details.\n\n"
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
    if len(candidate.split()) > 6 or len(candidate) > 48 or low_confidence_summary_text(candidate, language):
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
        if compact and not summary_looks_bad(compact, chunk):
            chunk_summaries.append(compact)

    if not chunk_summaries:
        raise RuntimeError("local transformer output failed quality checks")

    if len(chunks) == 1:
        if summary_looks_bad(chunk_summaries[0], text):
            raise RuntimeError("local transformer output failed quality checks")
        return chunk_summaries[:max_items]

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
    if not final_paragraph or summary_looks_bad(final_paragraph, text):
        raise RuntimeError("local transformer output failed quality checks")
    return [final_paragraph]


def summarize_with_instruction_model(
    text: str,
    language: str,
    max_items: int,
    model_name: str = INSTRUCTION_SUMMARY_MODEL_NAME,
) -> list[str]:
    tokenizer, model = get_instruction_backend(model_name)
    cleaned = normalize_transcript_for_summary(text)
    if not cleaned:
        return ["No summary available yet."]

    prompt = build_instruction_summary_prompt(cleaned, language, max_items)
    decoded = run_instruction_generation(tokenizer, model, prompt, max_new_tokens=220)
    items = parse_summary_output(decoded, max_items=max(1, min(max_items, 5)))
    good_items = [item for item in items if not summary_looks_bad(item, cleaned)]
    if not good_items:
        compact = clean_generated_paragraph(decoded, max_chars=520)
        if compact and not summary_looks_bad(compact, cleaned):
            good_items = [compact]
    if not good_items:
        raise RuntimeError("local instruction output failed quality checks")
    return good_items[:max_items]


def generate_title_with_instruction_model(text: str, language: str, fallback: str) -> str:
    tokenizer, model = get_instruction_backend(FAST_INSTRUCTION_MODEL_NAME)
    cleaned = normalize_transcript_for_summary(text)
    if not cleaned:
        return slugify_title(fallback)
    if language == "de":
        prompt = (
            "Erzeuge einen kurzen deutschen Titel fuer dieses Transkript.\n"
            "Maximal 7 Woerter. Kein Satzzeichen am Ende. Keine Anfuehrungszeichen. Keine Erklaerung.\n\n"
            f"Transkript:\n{cleaned[:3500]}\n\nTitel:"
        )
    else:
        prompt = (
            "Generate a short title for this transcript.\n"
            "At most 7 words. No final punctuation. No quotes. No explanation.\n\n"
            f"Transcript:\n{cleaned[:3500]}\n\nTitle:"
        )
    decoded = run_instruction_generation(tokenizer, model, prompt, max_new_tokens=40)
    candidate = normalize_title_candidate(decoded, fallback)
    if len(candidate.split()) < 2 or candidate.lower() == slugify_title(fallback).lower() or low_confidence_summary_text(candidate, language):
        return generate_title_from_summary(sentence_summary(cleaned, max_items=2, language=language), fallback)
    return candidate


def generate_summary_for_request(request: SummaryRequest) -> SummaryResult:
    provider = request.provider
    max_items = bounded_int(request.density, DEFAULT_SETTINGS["summary_sentences"], minimum=1, maximum=6)
    if provider in {"local_instruction", "local_instruction_quality"}:
        try:
            model_name = QUALITY_INSTRUCTION_MODEL_NAME if provider == "local_instruction_quality" else FAST_INSTRUCTION_MODEL_NAME
            return SummaryResult(summarize_with_instruction_model(request.text, request.language, max_items, model_name=model_name), provider)
        except Exception as exc:
            message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
            if "not installed" in message or "unavailable" in message or "quality checks" in message:
                logger.info("summary provider unavailable; using extractive: %s", message)
            else:
                logger.warning("summary provider failed; falling back to extractive: %s", message)
    if provider == "local_transformer":
        try:
            return SummaryResult(summarize_with_local_model(request.text, request.language, max_items), provider)
        except Exception as exc:
            message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
            if "not installed" in message or "unavailable" in message or "quality checks" in message:
                logger.info("summary provider unavailable; using extractive: %s", message)
            else:
                logger.warning("summary provider failed; falling back to extractive: %s", message)
    return SummaryResult(sentence_summary(request.text, max_items=max_items, language=request.language), "extractive")


def generate_extractions_for_request(request: ExtractionRequest) -> ExtractionResult:
    provider = request.provider
    if provider in {"local_instruction", "local_instruction_quality"}:
        try:
            model_name = QUALITY_INSTRUCTION_MODEL_NAME if provider == "local_instruction_quality" else FAST_INSTRUCTION_MODEL_NAME
            action_items, entities = extract_with_instruction_model(request.text, request.language, model_name=model_name)
            return ExtractionResult(action_items, entities, provider)
        except Exception as exc:
            message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            logger.warning("extraction provider failed; falling back to extractive: %s", message)
    return ExtractionResult(
        extract_action_items_heuristic(request.text, request.language),
        extract_entities_heuristic(request.text),
        "extractive",
    )


def generate_extractions(text: str, language: str, settings: dict) -> tuple[list[str], list[str], str]:
    request = ExtractionRequest(
        text=text,
        language=language,
        provider=settings["summary_provider"],
    )
    result = generate_extractions_for_request(request)
    return result.action_items, result.entities, result.provider


def generate_summary(text: str, language: str, settings: dict) -> tuple[list[str], str]:
    request = SummaryRequest(
        text=text,
        language=language,
        provider=settings["summary_provider"],
        density=settings["summary_sentences"],
    )
    result = generate_summary_for_request(request)
    return result.items, result.provider
