from __future__ import annotations

from pathlib import Path


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

SUMMARY_PROVIDERS = {
    "local_transformer": "Local German model",
    "extractive": "Fallback extractive",
}
SUMMARY_MODEL_NAME = "deutsche-telekom/mt5-small-sum-de-mit-v1"

DEFAULT_SETTINGS = {
    "default_model": DEFAULT_MODEL,
    "default_language": DEFAULT_LANGUAGE,
    "summary_provider": "local_transformer",
    "summary_sentences": 3,
    "autoplay_on_seek": True,
    "confirm_before_delete": True,
}
