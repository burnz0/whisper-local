#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging

try:
    from flask import Flask
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Flask is not installed for this Python interpreter.\n"
        "Run PYTHON=python3.12 make install-core"
    ) from exc

from config import DEFAULT_LANGUAGE, DEFAULT_MODEL, DEFAULT_SETTINGS, LANGUAGES, MODELS
from dependencies import format_dependency_report, runtime_dependency_report
from routes import friendly_transcription_error, register_routes
from storage import (
    LIBRARY_PATH,
    SETTINGS_PATH,
    TRANSCRIPT_DIR,
    UPLOAD_DIR,
    TranscriptRecord,
    ensure_dirs,
    get_record,
    load_library,
    load_settings,
    migrate_library,
)
from summaries import (
    format_duration,
    generate_summary,
    generate_title_from_summary,
    keyword_title_from_text,
    normalize_settings,
    normalize_title_candidate,
    parse_summary_output,
    summarize_with_local_model,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
register_routes(app)


def report_dependency_status() -> None:
    report = runtime_dependency_report()
    for item in report:
        log = logger.warning if item.status in {"missing", "unsupported"} and item.kind == "required" else logger.info
        log("dependency %s kind=%s status=%s detail=%s", item.name, item.kind, item.status, item.detail)


def main() -> None:
    ensure_dirs()
    parser = argparse.ArgumentParser(description="Local audio transcription web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--migrate-library", action="store_true", help="Backfill missing local library metadata and exit.")
    parser.add_argument("--check-deps", action="store_true", help="Check local runtime dependencies and exit.")
    args = parser.parse_args()

    if args.check_deps:
        print(format_dependency_report(runtime_dependency_report()))
        return

    if args.migrate_library:
        changed_count = migrate_library()
        print(f"Migrated {changed_count} local library record(s).")
        return

    report_dependency_status()
    print(f"Open http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
