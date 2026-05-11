from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass

from config import FAST_INSTRUCTION_MODEL_NAME, QUALITY_INSTRUCTION_MODEL_NAME, SUMMARY_MODEL_NAME
from transcription import active_backend_info


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    kind: str
    status: str
    detail: str


def module_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def runtime_dependency_report() -> list[DependencyStatus]:
    backend = active_backend_info()
    python_supported = sys.version_info >= (3, 11)
    return [
        DependencyStatus(
            "Python",
            "required",
            "installed" if python_supported else "unsupported",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; target is 3.11 or 3.12",
        ),
        DependencyStatus("Flask", "required", "installed" if module_installed("flask") else "missing", "web server"),
        DependencyStatus(
            "openai-whisper",
            "required",
            "installed" if module_installed("whisper") else "missing",
            f"active transcription backend: {backend.label}",
        ),
        DependencyStatus("ffmpeg", "required", "installed" if shutil.which("ffmpeg") else "missing", "audio decoding executable"),
        DependencyStatus("torch", "required", "installed" if module_installed("torch") else "missing", f"active mode: {backend.active_device_label}"),
        DependencyStatus("transformers", "optional", "installed" if module_installed("transformers") else "missing", "Qwen and mT5 local analysis"),
        DependencyStatus("sentencepiece", "optional", "installed" if module_installed("sentencepiece") else "missing", f"mT5 tokenizer for {SUMMARY_MODEL_NAME}"),
        DependencyStatus("protobuf", "optional", "installed" if module_installed("google.protobuf") else "missing", "mT5 tokenizer dependency"),
        DependencyStatus("faster-whisper", "optional", "installed" if module_installed("faster_whisper") else "missing", "benchmark candidate only"),
        DependencyStatus("whisper.cpp", "optional", "installed" if shutil.which("whisper-cli") else "missing", "benchmark candidate executable"),
        DependencyStatus("Qwen fast title model", "optional", "configured", FAST_INSTRUCTION_MODEL_NAME),
        DependencyStatus("Qwen quality summary model", "optional", "configured", QUALITY_INSTRUCTION_MODEL_NAME),
    ]


def format_dependency_report(report: list[DependencyStatus]) -> str:
    lines = ["Runtime dependency report:"]
    for item in report:
        lines.append(f"- {item.kind}: {item.name}: {item.status} ({item.detail})")
    return "\n".join(lines)
