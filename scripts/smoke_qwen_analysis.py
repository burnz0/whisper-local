#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from config import FAST_INSTRUCTION_MODEL_NAME, QUALITY_INSTRUCTION_MODEL_NAME  # noqa: E402
from summaries import generate_title_with_instruction_model, summarize_with_instruction_model  # noqa: E402


SAMPLE_TEXT = {
    "de": (
        "Anna bespricht den Produktlaunch. Das Team muss die Demo vorbereiten, "
        "Budgetrisiken klaeren und bis Freitag die offenen Aufgaben verteilen."
    ),
    "en": (
        "Anna reviews the product launch. The team needs to prepare the demo, "
        "clarify budget risks, and assign open tasks by Friday."
    ),
}


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


def summary_model_for(provider: str) -> str:
    if provider == "local_instruction_quality":
        return QUALITY_INSTRUCTION_MODEL_NAME
    if provider == "local_instruction":
        return FAST_INSTRUCTION_MODEL_NAME
    raise ValueError("provider must be local_instruction or local_instruction_quality")


def run_smoke(text: str, language: str, provider: str, summary_items: int) -> dict:
    summary_model = summary_model_for(provider)
    summary = summarize_with_instruction_model(text, language, max_items=summary_items, model_name=summary_model)
    title = generate_title_with_instruction_model(text, language, fallback="Qwen smoke test")
    return {
        "ok": True,
        "language": language,
        "provider": provider,
        "summary_model": summary_model,
        "title_model": FAST_INSTRUCTION_MODEL_NAME,
        "transformers": package_version("transformers"),
        "torch": package_version("torch"),
        "title": title,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test local Qwen title and summary generation.")
    parser.add_argument("--language", choices=sorted(SAMPLE_TEXT), default="de")
    parser.add_argument("--provider", choices=("local_instruction", "local_instruction_quality"), default="local_instruction")
    parser.add_argument("--summary-items", type=int, default=2)
    parser.add_argument("--text", default="", help="Override the built-in short smoke-test transcript.")
    args = parser.parse_args()

    text = args.text.strip() or SAMPLE_TEXT[args.language]
    try:
        payload = run_smoke(text, args.language, args.provider, args.summary_items)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "language": args.language,
                    "provider": args.provider,
                    "transformers": package_version("transformers"),
                    "torch": package_version("torch"),
                    "error": str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from exc

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

