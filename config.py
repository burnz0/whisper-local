from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
LIBRARY_PATH = DATA_DIR / "library.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

MODELS = ("tiny", "base", "small", "turbo")
LANGUAGES = {"de": "German", "en": "English"}
DEFAULT_MODEL = "small"
DEFAULT_LANGUAGE = "de"
UPLOAD_ACCEPT = ".opus,.oga,.ogg,.mp3,.m4a,.wav,.mp4,.mpeg,.webm,.aac,.flac"
ALLOWED_EXTENSIONS = {ext.strip(".") for ext in UPLOAD_ACCEPT.split(",")}

SUMMARY_PROVIDERS = {
    "local_instruction_quality": "Quality local instruction (Qwen3 1.7B)",
    "local_instruction": "Fast local instruction (Qwen3 0.6B)",
    "extractive": "Extractive fallback",
    "local_transformer": "Experimental German mT5",
}
SUMMARY_MODEL_NAME = "deutsche-telekom/mt5-small-sum-de-mit-v1"
FAST_INSTRUCTION_MODEL_NAME = os.environ.get("FAST_INSTRUCTION_MODEL_NAME", "Qwen/Qwen3-0.6B")
QUALITY_INSTRUCTION_MODEL_NAME = os.environ.get("QUALITY_INSTRUCTION_MODEL_NAME", "Qwen/Qwen3-1.7B")
INSTRUCTION_SUMMARY_MODEL_NAME = os.environ.get("INSTRUCTION_SUMMARY_MODEL_NAME", FAST_INSTRUCTION_MODEL_NAME)

DEFAULT_SETTINGS = {
    "default_model": DEFAULT_MODEL,
    "default_language": DEFAULT_LANGUAGE,
    "summary_provider": "local_instruction_quality",
    "summary_sentences": 3,
    "autoplay_on_seek": True,
    "confirm_before_delete": True,
}
