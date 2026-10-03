import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from pydub.exceptions import CouldntDecodeError

import backend
from helpers import ConversionTestCase

REAL_RECOGNIZE_GOOGLE = backend.sr.Recognizer.recognize_google


class BackendTests(ConversionTestCase):
    def test_prepared_wav_output_uses_original_media_name_and_directory(self):
        media_directory = self.root / "original media"
        media_directory.mkdir()
        original_media = media_directory / "recording.mp4"
        existing_text = original_media.with_suffix(".txt")
        existing_text.write_text("existing transcript")
        result = backend.convert_audio(str(self.source), output_source_path=str(original_media))
        self.assertEqual(media_directory / "recording(1).txt", Path(result.output_path))
        self.assertEqual("first", Path(result.output_path).read_text())
        self.assertEqual("existing transcript", existing_text.read_text())
        self.assertFalse(self.source.with_suffix(".txt").exists())

    def test_input_named_chunk1_and_neighboring_chunks_are_preserved(self):
        original = self.source.read_bytes()
        neighbor = self.root / "chunk2.wav"
        neighbor.write_bytes(b"existing user file")
        with chdir(self.root):
            backend.convert_audio(str(self.source))
        self.assertTrue(self.source.exists())
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(b"existing user file", neighbor.read_bytes())
        self.assertEqual("first", self.source.with_suffix(".txt").read_text())

    def test_each_run_uses_a_new_directory_and_cleans_it(self):
        exported = []
        original_export = backend.AudioSegment.export

        def track_export(segment, destination, *args, **kwargs):
            exported.append(Path(getattr(destination, "name", destination)))
            return original_export(segment, destination, *args, **kwargs)

        with patch.object(backend.AudioSegment, "export", track_export), chdir(self.root):
            for _ in range(2):
                backend.convert_audio(str(self.source))
        self.assertEqual(2, len(exported))
        self.assertNotEqual(exported[0].parent, exported[1].parent)
        for path in exported:
            self.assertNotEqual(self.root, path.parent)
            self.assertFalse(path.parent.exists())

    def test_corrupt_wav_raises_without_writing_output(self):
        self.source.write_bytes(b"not a wav")
        with self.assertRaises((OSError, CouldntDecodeError)):
            backend.convert_audio(str(self.source))
        self.assertFalse(self.source.with_suffix(".txt").exists())

    def test_export_failure_cleans_temporary_directory(self):
        directories = []

        def temporary_directory(**kwargs):
            directory = tempfile.TemporaryDirectory(**kwargs)
            directories.append(Path(directory.name))
            return directory

        with patch("backend.TemporaryDirectory", side_effect=temporary_directory), patch.object(
            backend.AudioSegment, "export", side_effect=PermissionError("export denied")
        ):
            with self.assertRaisesRegex(PermissionError, "export denied"):
                backend.convert_audio(str(self.source))
        self.assertTrue(directories)
        self.assertTrue(all(not path.exists() for path in directories))

    def test_output_permission_error_propagates_to_caller(self):
        real_open = open

        def restricted_open(path, mode="r", *args, **kwargs):
            if mode == "w":
                raise PermissionError("output denied")
            return real_open(path, mode, *args, **kwargs)

        with patch("backend.open", side_effect=restricted_open):
            with self.assertRaisesRegex(PermissionError, "output denied"):
                backend.convert_audio(str(self.source))

    def test_cleanup_error_propagates_to_caller(self):
        class FailingCleanup(tempfile.TemporaryDirectory):
            def cleanup(self):
                super().cleanup()
                raise PermissionError("cleanup denied")

        with patch("backend.TemporaryDirectory", FailingCleanup):
            with self.assertRaisesRegex(PermissionError, "cleanup denied"):
                backend.convert_audio(str(self.source))

    def test_recognition_results_distinguish_success_partial_and_failure(self):
        self.write_wav(self.source, duration_ms=50100)
        cases = [
            (["first", "second"], "success", 2),
            (["first", backend.sr.RequestError("offline")], "partial", 1),
            ([backend.sr.UnknownValueError(), "second"], "partial", 1),
            ([backend.sr.RequestError("offline"), backend.sr.RequestError("offline")], "failed", 0),
            ([backend.sr.UnknownValueError(), "  "], "failed", 0),
            (["first", TimeoutError("timed out")], "partial", 1),
        ]
        for responses, status, successful in cases:
            with self.subTest(status=status, responses=responses):
                self.recognize.side_effect = responses
                result = backend.convert_audio(str(self.source))
                self.assertEqual(status, result.status)
                self.assertEqual(successful, result.successful_chunks)
                self.assertEqual(2, result.total_chunks)
                self.assertEqual(2 - successful, len(result.errors))
                if successful:
                    self.assertEqual(result.text, Path(result.output_path).read_text())
                    Path(result.output_path).unlink()
                else:
                    self.assertIsNone(result.output_path)
                    self.assertFalse(self.source.with_suffix(".txt").exists())

    def test_transcript_chunks_are_separated_by_spaces(self):
        self.write_wav(self.source, duration_ms=50100)
        self.recognize.side_effect = ["  first ", " second  "]
        result = backend.convert_audio(str(self.source))
        self.assertEqual("first second", result.text)
        self.assertEqual("first second", Path(result.output_path).read_text())

    def test_unrecognized_chunks_remain_separated_in_partial_text(self):
        self.write_wav(self.source, duration_ms=100100)
        self.recognize.side_effect = ["first", backend.sr.UnknownValueError(), "second"]
        result = backend.convert_audio(str(self.source))
        self.assertEqual("first [2. parça: Ses algılanamadı.] second", result.text)

    def test_empty_wav_does_not_claim_success_or_write_output(self):
        self.write_wav(self.source, duration_ms=0)
        result = backend.convert_audio(str(self.source))
        self.assertEqual("failed", result.status)
        self.assertIsNone(result.output_path)
        self.recognize.assert_not_called()

    def test_network_request_receives_timeout_and_timeout_is_failure(self):
        with patch.object(backend.sr.Recognizer, "recognize_google", REAL_RECOGNIZE_GOOGLE), patch.object(
            backend.sr.AudioData, "get_flac_data", return_value=b"fake flac"
        ), patch("speech_recognition.recognizers.google.urlopen", side_effect=TimeoutError) as request:
            result = backend.convert_audio(str(self.source))
        self.assertEqual("failed", result.status)
        self.assertIn("zaman aşımı", result.errors[0])
        self.assertEqual(30, request.call_args.kwargs["timeout"])

    def test_progress_uses_actual_chunk_count_after_recognition(self):
        for duration_ms, expected in [
            (100, [100]),
            (50000, [100]),
            (50100, [50, 100]),
            (100000, [50, 100]),
            (100100, [33, 66, 100]),
        ]:
            with self.subTest(duration_ms=duration_ms):
                self.write_wav(self.source, duration_ms=duration_ms)
                events = []
                self.recognize.side_effect = lambda *args, **kwargs: events.append(
                    ("recognized", None)
                ) or "text"
                backend.convert_audio(
                    str(self.source), lambda value: events.append(("progress", value))
                )
                expected_events = []
                for value in expected:
                    expected_events.extend([("recognized", None), ("progress", value)])
                self.assertEqual(expected_events, events)

    def test_failed_recognition_is_counted_as_processed(self):
        self.write_wav(self.source, duration_ms=50100)
        events = []

        def fail_recognition(*args, **kwargs):
            events.append(("failed", None))
            raise backend.sr.RequestError("offline")

        self.recognize.side_effect = fail_recognition
        backend.convert_audio(str(self.source), lambda value: events.append(("progress", value)))
        self.assertEqual([
            ("failed", None), ("progress", 50),
            ("failed", None), ("progress", 100),
        ], events)

    def test_empty_audio_has_no_processed_chunks(self):
        self.write_wav(self.source, duration_ms=0)
        progress = []
        backend.convert_audio(str(self.source), progress.append)
        self.assertEqual([], progress)


if __name__ == "__main__":
    unittest.main()
