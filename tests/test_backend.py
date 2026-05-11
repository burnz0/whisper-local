import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import summaries
import storage


class BackendBehaviorTest(unittest.TestCase):
    def test_normalize_settings_falls_back_to_safe_defaults(self):
        settings = app.normalize_settings(
            {
                "default_model": "huge",
                "default_language": "fr",
                "summary_provider": "remote",
                "summary_sentences": "many",
                "autoplay_on_seek": "",
                "confirm_before_delete": 0,
            }
        )

        self.assertEqual(settings["default_model"], app.DEFAULT_MODEL)
        self.assertEqual(settings["default_language"], app.DEFAULT_LANGUAGE)
        self.assertEqual(settings["summary_provider"], app.DEFAULT_SETTINGS["summary_provider"])
        self.assertEqual(settings["summary_sentences"], app.DEFAULT_SETTINGS["summary_sentences"])
        self.assertFalse(settings["autoplay_on_seek"])
        self.assertFalse(settings["confirm_before_delete"])

    def test_title_cleanup_and_keyword_fallback(self):
        title = app.normalize_title_candidate("Titel: Eine sehr lange Aussage mit viel zu vielen Worten.", "fallback")
        fallback_title = app.generate_title_from_summary([], "audio file")
        keyword_title = app.keyword_title_from_text("und der die Kultur Festival Konzert", "fallback")

        self.assertEqual(title, "Eine sehr lange Aussage mit viel")
        self.assertEqual(fallback_title, "audio file")
        self.assertEqual(keyword_title, "Kultur Festival Konzert")

    def test_summary_parsing_and_fallback_generation(self):
        parsed = app.parse_summary_output("- Erstes Thema\n- Erstes Thema\n- Zweites Thema", 3)

        with mock.patch.object(summaries, "summarize_with_local_model", side_effect=RuntimeError("model unavailable")):
            summary, provider = app.generate_summary(
                "Das ist ein wichtiger Satz. Dieser Satz beschreibt ein zweites Thema.",
                "de",
                {"summary_provider": "local_transformer", "summary_sentences": 2},
            )

        self.assertEqual(parsed, ["Erstes Thema.", "Zweites Thema."])
        self.assertEqual(provider, "extractive")
        self.assertTrue(summary)

    def test_duration_formatting(self):
        self.assertEqual(app.format_duration(0), "00:00")
        self.assertEqual(app.format_duration(65.9), "01:05")
        self.assertEqual(app.format_duration(3661), "1:01:01")

    def test_friendly_transcription_errors(self):
        unsupported, unsupported_status = app.friendly_transcription_error(ValueError("This file format is not supported yet."))
        ffmpeg, ffmpeg_status = app.friendly_transcription_error(FileNotFoundError("ffmpeg"))
        cuda, cuda_status = app.friendly_transcription_error(RuntimeError("CUDA out of memory"))
        corrupt, corrupt_status = app.friendly_transcription_error(RuntimeError("Invalid data found when processing input"))
        model, model_status = app.friendly_transcription_error(RuntimeError("Whisper model unavailable"))

        self.assertIn("format", unsupported)
        self.assertEqual(unsupported_status, 400)
        self.assertIn("FFmpeg", ffmpeg)
        self.assertEqual(ffmpeg_status, 500)
        self.assertIn("GPU", cuda)
        self.assertEqual(cuda_status, 500)
        self.assertIn("decoded", corrupt)
        self.assertEqual(corrupt_status, 400)
        self.assertIn("Whisper", model)
        self.assertEqual(model_status, 500)

    def test_invalid_settings_json_is_backed_up_and_restored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            settings_path.write_text("{bad json", encoding="utf-8")

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", root / "uploads"), mock.patch.object(
                storage, "TRANSCRIPT_DIR", root / "transcripts"
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", root / "library.json"):
                settings = app.load_settings()

            backups = list(root.glob("settings.corrupt-*.json"))
            self.assertEqual(settings["default_model"], app.DEFAULT_MODEL)
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(settings_path.read_text(encoding="utf-8"))["default_model"], app.DEFAULT_MODEL)

    def test_load_library_does_not_rewrite_missing_summary_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_path = root / "library.json"
            settings_path = root / "settings.json"
            record = {
                "id": "abc123",
                "title": "Original",
                "filename": "recording.ogg",
                "stored_filename": "abc123.ogg",
                "transcript_filename": "abc123.txt",
                "created_at": "2026-05-11T12:00:00",
                "model": "base",
                "language": "de",
                "duration_seconds": 12,
                "transcript_text": "Ein Satz. Noch ein Satz.",
                "segments": [],
            }
            library_payload = json.dumps([record], ensure_ascii=False, indent=2) + "\n"
            library_path.write_text(library_payload, encoding="utf-8")
            settings_path.write_text(json.dumps(app.DEFAULT_SETTINGS), encoding="utf-8")

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", root / "uploads"), mock.patch.object(
                storage, "TRANSCRIPT_DIR", root / "transcripts"
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", library_path), mock.patch.object(
                storage, "generate_summary", side_effect=AssertionError("load_library must not generate summaries")
            ):
                records = app.load_library()

            self.assertEqual(library_path.read_text(encoding="utf-8"), library_payload)
            self.assertEqual(records[0].id, "abc123")
            self.assertTrue(records[0].summary)

    def test_tags_exports_cleanup_and_segment_edit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_path = root / "library.json"
            settings_path = root / "settings.json"
            transcripts_dir = root / "transcripts"
            transcripts_dir.mkdir()
            record = {
                "id": "abc123",
                "title": "Original",
                "filename": "recording.ogg",
                "stored_filename": "abc123.ogg",
                "transcript_filename": "abc123.txt",
                "created_at": "2026-05-11T12:00:00",
                "model": "base",
                "language": "de",
                "duration_seconds": 12,
                "transcript_text": "ähm Hallo Welt.",
                "summary": ["Hallo Welt."],
                "summary_provider": "extractive",
                "segments": [{"id": 0, "start_label": "00:00", "text": "ähm Hallo Welt."}],
            }
            library_path.write_text(json.dumps([record], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            settings_path.write_text(json.dumps(app.DEFAULT_SETTINGS), encoding="utf-8")

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", root / "uploads"), mock.patch.object(
                storage, "TRANSCRIPT_DIR", transcripts_dir
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", library_path):
                tagged = storage.update_record_tags("abc123", "Idea, idea, Follow Up")
                collected = storage.update_record_collection("abc123", " Client Calls ")
                noted = storage.update_record_notes("abc123", "Call Anna about the launch.")
                edited = storage.update_segment_text("abc123", 0, "Hallo Welt.")
                flagged = storage.update_segment_flags("abc123", 0, bookmarked=True, highlighted=True)
                spoken = storage.update_segment_speaker("abc123", 0, " Anna ")
                markdown = storage.markdown_export(spoken)
                clean_text = storage.cleaned_transcript_text(storage.get_record("abc123"))

            self.assertEqual(tagged.tags, ["idea", "follow up"])
            self.assertEqual(collected.collection, "Client Calls")
            self.assertEqual(noted.notes, "Call Anna about the launch.")
            self.assertEqual(edited.transcript_text, "Hallo Welt.")
            self.assertTrue(flagged.segments[0]["bookmarked"])
            self.assertTrue(flagged.segments[0]["highlighted"])
            self.assertEqual(spoken.segments[0]["speaker"], "Anna")
            self.assertIn("# Original", markdown)
            self.assertIn("- Collection: Client Calls", markdown)
            self.assertIn("## Notes", markdown)
            self.assertIn("Call Anna about the launch.", markdown)
            self.assertIn("**Anna:**", markdown)
            self.assertIn("bookmarked, highlighted", markdown)
            self.assertNotIn("ähm", clean_text)

    def test_delete_all_records_clears_library_and_saved_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_path = root / "library.json"
            settings_path = root / "settings.json"
            uploads_dir = root / "uploads"
            transcripts_dir = root / "transcripts"
            uploads_dir.mkdir()
            transcripts_dir.mkdir()
            (uploads_dir / "abc123.ogg").write_bytes(b"audio")
            (transcripts_dir / "abc123.txt").write_text("Transcript", encoding="utf-8")
            record = {
                "id": "abc123",
                "title": "Original",
                "filename": "recording.ogg",
                "stored_filename": "abc123.ogg",
                "transcript_filename": "abc123.txt",
                "created_at": "2026-05-11T12:00:00",
                "model": "base",
                "language": "de",
                "duration_seconds": 12,
                "transcript_text": "Hallo Welt.",
                "summary": ["Hallo Welt."],
                "summary_provider": "extractive",
                "segments": [],
            }
            library_path.write_text(json.dumps([record], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            settings_path.write_text(json.dumps(app.DEFAULT_SETTINGS), encoding="utf-8")

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", uploads_dir), mock.patch.object(
                storage, "TRANSCRIPT_DIR", transcripts_dir
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", library_path):
                deleted_count = storage.delete_all_records()

            self.assertEqual(deleted_count, 1)
            self.assertEqual(json.loads(library_path.read_text(encoding="utf-8")), [])
            self.assertFalse((uploads_dir / "abc123.ogg").exists())
            self.assertFalse((transcripts_dir / "abc123.txt").exists())


if __name__ == "__main__":
    unittest.main()
