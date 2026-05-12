import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

import app
import jobs
import routes
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
        self.assertEqual(fallback_title, "Audio file")
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

    def test_instruction_summary_provider_success_and_fallback(self):
        with mock.patch.object(summaries, "summarize_with_instruction_model", return_value=["Launch-Risiken und nächste Schritte."]):
            summary, provider = app.generate_summary(
                "Anna bespricht den Produktlaunch und nächste Schritte.",
                "de",
                {"summary_provider": "local_instruction_quality", "summary_sentences": 3},
            )

        with mock.patch.object(summaries, "summarize_with_instruction_model", side_effect=RuntimeError("model unavailable")):
            fallback, fallback_provider = app.generate_summary(
                "Anna bespricht den Produktlaunch und nächste Schritte.",
                "de",
                {"summary_provider": "local_instruction_quality", "summary_sentences": 3},
            )

        self.assertEqual(provider, "local_instruction_quality")
        self.assertEqual(summary, ["Launch-Risiken und nächste Schritte."])
        self.assertEqual(fallback_provider, "extractive")
        self.assertTrue(fallback)

    def test_transcript_creation_uses_fast_initial_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            library_path = root / "library.json"
            transcripts_dir = root / "transcripts"
            uploads_dir = root / "uploads"
            transcripts_dir.mkdir()
            uploads_dir.mkdir()
            audio_path = uploads_dir / "abc123.ogg"
            audio_path.write_bytes(b"audio")
            settings_path.write_text(json.dumps({**app.DEFAULT_SETTINGS, "summary_provider": "local_instruction_quality"}), encoding="utf-8")
            library_path.write_text("[]\n", encoding="utf-8")

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", uploads_dir), mock.patch.object(
                storage, "TRANSCRIPT_DIR", transcripts_dir
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", library_path), mock.patch.object(
                storage, "transcribe_file", return_value=("Anna bespricht den Produktlaunch.", [], 4.0)
            ), mock.patch.object(storage, "generate_summary", wraps=storage.generate_summary) as generate_mock:
                record = storage.create_transcript_from_audio(audio_path, "abc123", "meeting.ogg", "base", "de")

            self.assertEqual(record.summary_provider, "extractive")
            self.assertEqual(generate_mock.call_args.kwargs["settings"]["summary_provider"], "extractive")

    def test_extractive_summary_cleans_timestamps_and_title_uses_summary(self):
        summary, provider = app.generate_summary(
            "00:00 ähm Anna bespricht den Produktlaunch mit Budgetfreigabe. "
            "00:12 Danach plant das Team die nächsten Schritte für die Demo.",
            "de",
            {"summary_provider": "extractive", "summary_sentences": 2},
        )
        title = app.generate_title_from_summary(summary, "bad_filename_001")

        self.assertEqual(provider, "extractive")
        self.assertNotIn("00:00", " ".join(summary))
        self.assertNotIn("ähm", " ".join(summary).lower())
        self.assertIn("Produktlaunch", title)
        self.assertTrue(title[0].isupper())
        self.assertNotIn("filename", title.lower())

    def test_conversation_summary_uses_topics_not_copied_sentences(self):
        text = (
            "Du bist toll und zuverlässig. Ich wünsche mir, dass wir unterschiedliche Vorstellungen "
            "in dieser Verbindung offen besprechen und besser verstehen."
        )
        summary, provider = app.generate_summary(
            text,
            "de",
            {"summary_provider": "extractive", "summary_sentences": 3},
        )
        dense_summary, _provider = app.generate_summary(
            text,
            "de",
            {"summary_provider": "extractive", "summary_sentences": 5},
        )

        self.assertEqual(provider, "extractive")
        self.assertEqual(
            summary,
            ["Es geht um Wertschätzung, unterschiedliche Vorstellungen, Beziehung und Verbindung sowie offene Kommunikation."],
        )
        self.assertGreaterEqual(len(dense_summary), len(summary))

    def test_extractive_summary_rejects_low_confidence_capitalized_artifacts(self):
        summary, provider = app.generate_summary(
            "Jugendermens, Zünnschneuer sowie Kanarein.",
            "de",
            {"summary_provider": "extractive", "summary_sentences": 3},
        )
        title = app.generate_title_from_summary(summary, "2026-05-12 sample audio")

        self.assertEqual(provider, "extractive")
        self.assertEqual(summary, ["Summary pending."])
        self.assertEqual(title, "2026-05-12 sample audio")

    def test_trailing_asr_artifact_block_is_trimmed(self):
        segments = [
            {"id": 0, "text": "Wir sprechen ueber die Beziehung."},
            {"id": 1, "text": "Ja, aber schon zusammen eroertern."},
            {"id": 2, "text": "gut, gut."},
            {"id": 3, "text": "Willst du schon ein bisschen drama"},
            {"id": 4, "text": "wie kann ready."},
            {"id": 5, "text": "Und ich will heute den Raum geben."},
            {"id": 6, "text": "情 glimpse es nicht zu einigen."},
            {"id": 7, "text": "Juenger 1.2."},
            {"id": 8, "text": "Gobeide interrupted."},
        ]
        text, cleaned_segments = storage.clean_transcription_tail(
            " ".join(segment["text"] for segment in segments),
            segments,
        )

        self.assertEqual([segment["id"] for segment in cleaned_segments], [0, 1])
        self.assertIn("zusammen eroertern", text)
        self.assertNotIn("interrupted", text)

    def test_duration_formatting(self):
        self.assertEqual(app.format_duration(0), "00:00")
        self.assertEqual(app.format_duration(65.9), "01:05")
        self.assertEqual(app.format_duration(3661), "1:01:01")

    def test_queued_job_can_be_canceled(self):
        job = jobs.TranscriptionJob(
            id="job123",
            status="queued",
            source_name="audio.ogg",
            model="base",
            language="de",
            processing_mode="CPU",
            source_size_bytes=12,
            queued_at=0,
        )
        with jobs._LOCK:
            jobs._JOBS[job.id] = job
        try:
            self.assertTrue(jobs.cancel_job("job123"))
            self.assertEqual(jobs.get_job("job123").status, "canceled")
            self.assertFalse(jobs.cancel_job("job123"))
        finally:
            with jobs._LOCK:
                jobs._JOBS.pop(job.id, None)

    def test_transcribe_route_accepts_multiple_files_as_import_batch(self):
        class FakeBatch:
            id = "batch123"

            def as_dict(self):
                return {
                    "id": self.id,
                    "status": "running",
                    "total_count": 2,
                    "finished_count": 0,
                    "complete_count": 0,
                    "failed_count": 0,
                    "canceled_count": 0,
                    "skipped_count": 0,
                    "running_count": 0,
                    "queued_count": 2,
                    "progress_percent": 0,
                    "first_record_id": None,
                    "jobs": [],
                }

        saved_uploads = [
            storage.SavedUpload(Path("one.ogg"), "one", "one.ogg", "hash-one", 3),
            storage.SavedUpload(Path("two.mp3"), "two", "two.mp3", "hash-two", 3),
        ]
        with mock.patch.object(routes, "save_upload", side_effect=saved_uploads) as save_mock, mock.patch.object(
            routes, "start_transcription_batch", return_value=FakeBatch()
        ) as batch_mock:
            response = app.app.test_client().post(
                "/transcribe",
                data={
                    "model": app.DEFAULT_MODEL,
                    "language": app.DEFAULT_LANGUAGE,
                    "audio_file": [(BytesIO(b"one"), "one.ogg"), (BytesIO(b"two"), "two.mp3")],
                },
                headers={"X-Requested-With": "fetch"},
                content_type="multipart/form-data",
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save_mock.call_count, 2)
        self.assertEqual(len(batch_mock.call_args.args[0]), 2)
        self.assertEqual(payload["redirect_url"], "/imports/batch123")

    def test_duplicate_import_is_skipped_without_transcription(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library_path = root / "library.json"
            settings_path = root / "settings.json"
            uploads_dir = root / "uploads"
            transcripts_dir = root / "transcripts"
            uploads_dir.mkdir()
            transcripts_dir.mkdir()
            duplicate_path = uploads_dir / "duplicate.ogg"
            duplicate_path.write_bytes(b"same audio")
            library_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "existing123",
                            "title": "Existing",
                            "filename": "recording.ogg",
                            "stored_filename": "existing123.ogg",
                            "transcript_filename": "existing123.txt",
                            "created_at": "2026-05-11T12:00:00",
                            "model": "base",
                            "language": "de",
                            "duration_seconds": 12,
                            "transcript_text": "Hallo Welt.",
                            "summary": ["Hallo Welt."],
                            "summary_provider": "extractive",
                            "segments": [],
                            "source_hash": "duplicate-hash",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            settings_path.write_text(json.dumps(app.DEFAULT_SETTINGS), encoding="utf-8")
            saved_upload = storage.SavedUpload(duplicate_path, "new123", "recording-copy.ogg", "duplicate-hash", duplicate_path.stat().st_size)

            with jobs._LOCK:
                jobs._JOBS.clear()
                jobs._BATCHES.clear()

            with mock.patch.object(storage, "DATA_DIR", root), mock.patch.object(storage, "UPLOAD_DIR", uploads_dir), mock.patch.object(
                storage, "TRANSCRIPT_DIR", transcripts_dir
            ), mock.patch.object(storage, "SETTINGS_PATH", settings_path), mock.patch.object(storage, "LIBRARY_PATH", library_path), mock.patch.object(
                jobs, "create_transcript_from_audio", side_effect=AssertionError("duplicate should not transcribe")
            ):
                batch = jobs.start_transcription_batch([saved_upload], "base", "de")
                payload = batch.as_dict()

            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["skipped_count"], 1)
            self.assertEqual(payload["finished_count"], 1)
            self.assertEqual(payload["first_record_id"], "existing123")
            self.assertEqual(payload["jobs"][0]["status"], "skipped")
            self.assertEqual(payload["jobs"][0]["record_id"], "existing123")
            self.assertFalse(duplicate_path.exists())

            with jobs._LOCK:
                jobs._JOBS.clear()
                jobs._BATCHES.clear()

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
