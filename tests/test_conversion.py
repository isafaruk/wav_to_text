import os
import tempfile
import unittest
import wave
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

import proje

REAL_RECOGNIZE_GOOGLE = proje.sr.Recognizer.recognize_google


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "chunk1.wav"
        self.write_wav(self.source)
        self.messages = self.enterContext(patch("proje.QMessageBox"))
        self.recognize = self.enterContext(
            patch.object(proje.sr.Recognizer, "recognize_google", return_value="first")
        )

    @staticmethod
    def write_wav(path, duration_ms=100):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x01\x00" * (8 * duration_ms))

    def test_input_named_chunk1_and_neighboring_chunks_are_preserved(self):
        original = self.source.read_bytes()
        neighbor = self.root / "chunk2.wav"
        neighbor.write_bytes(b"existing user file")
        worker = proje.AudioToTextThread(str(self.source))
        with chdir(self.root):
            worker.run()
        self.assertTrue(self.source.exists())
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(b"existing user file", neighbor.read_bytes())
        self.assertEqual("first", self.source.with_suffix(".txt").read_text())

    def test_each_run_uses_a_new_directory_and_cleans_it(self):
        exported = []
        original_export = proje.AudioSegment.export

        def track_export(segment, destination, *args, **kwargs):
            exported.append(Path(getattr(destination, "name", destination)))
            return original_export(segment, destination, *args, **kwargs)

        with patch.object(proje.AudioSegment, "export", track_export), chdir(self.root):
            for _ in range(2):
                proje.AudioToTextThread(str(self.source)).run()
        self.assertEqual(2, len(exported))
        self.assertNotEqual(exported[0].parent, exported[1].parent)
        for path in exported:
            self.assertNotEqual(self.root, path.parent)
            self.assertFalse(path.parent.exists())

    def test_worker_does_not_create_a_message_box(self):
        proje.AudioToTextThread(str(self.source)).run()
        self.assertEqual([], self.messages.mock_calls)

    def test_completion_message_runs_on_gui_thread(self):
        dialog = QtWidgets.QDialog()
        ui = proje.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        message_threads = []
        self.messages.information.side_effect = lambda *args: message_threads.append(
            QtCore.QThread.currentThread()
        )
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.assertEqual([self.app.thread()], message_threads)
        self.assertFalse(ui.label_2.isHidden())
        self.assertTrue(ui.pushButton.isEnabled())
        self.assertTrue(ui.pushButton_2.isEnabled())
        dialog.close()

    def run_worker(self):
        worker = proje.AudioToTextThread(str(self.source))
        results, errors = [], []
        worker.done.connect(results.append)
        worker.error.connect(errors.append)
        worker.run()
        return results, errors

    def test_corrupt_wav_reports_error(self):
        self.source.write_bytes(b"not a wav")
        results, errors = self.run_worker()
        self.assertEqual([], results)
        self.assertEqual(1, len(errors))
        self.assertFalse(self.source.with_suffix(".txt").exists())

    def test_export_failure_cleans_temporary_directory(self):
        directories = []

        def temporary_directory(**kwargs):
            directory = tempfile.TemporaryDirectory(**kwargs)
            directories.append(Path(directory.name))
            return directory

        with patch("proje.TemporaryDirectory", side_effect=temporary_directory), patch.object(
            proje.AudioSegment, "export", side_effect=PermissionError("export denied")
        ):
            results, errors = self.run_worker()
        self.assertEqual([], results)
        self.assertIn("export denied", errors[0])
        self.assertTrue(directories)
        self.assertTrue(all(not path.exists() for path in directories))

    def test_output_permission_error_is_reported(self):
        real_open = open

        def restricted_open(path, mode="r", *args, **kwargs):
            if mode == "w":
                raise PermissionError("output denied")
            return real_open(path, mode, *args, **kwargs)

        with patch("proje.open", side_effect=restricted_open):
            results, errors = self.run_worker()
        self.assertEqual([], results)
        self.assertIn("output denied", errors[0])

    def test_cleanup_error_is_reported(self):
        class FailingCleanup(tempfile.TemporaryDirectory):
            def cleanup(self):
                super().cleanup()
                raise PermissionError("cleanup denied")

        with patch("proje.TemporaryDirectory", FailingCleanup):
            results, errors = self.run_worker()
        self.assertEqual([], results)
        self.assertIn("cleanup denied", errors[0])

    def test_file_error_restores_buttons_and_allows_retry(self):
        dialog = QtWidgets.QDialog()
        ui = proje.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        self.source.unlink()
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.messages.critical.assert_called_once()
        self.messages.information.assert_not_called()
        self.assertTrue(ui.pushButton.isEnabled())
        self.assertTrue(ui.pushButton_2.isEnabled())
        self.assertTrue(ui.label_2.isHidden())
        self.assertTrue(ui.label_3.isHidden())
        self.write_wav(self.source)
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.messages.information.assert_called_once()
        dialog.close()

    def test_recognition_results_distinguish_success_partial_and_failure(self):
        self.write_wav(self.source, duration_ms=50100)
        cases = [
            (["first", "second"], "success", 2),
            (["first", proje.sr.RequestError("offline")], "partial", 1),
            ([proje.sr.UnknownValueError(), "second"], "partial", 1),
            ([proje.sr.RequestError("offline"), proje.sr.RequestError("offline")], "failed", 0),
            ([proje.sr.UnknownValueError(), "  "], "failed", 0),
            (["first", TimeoutError("timed out")], "partial", 1),
        ]
        for responses, status, successful in cases:
            with self.subTest(status=status, responses=responses):
                self.recognize.side_effect = responses
                results, errors = self.run_worker()
                self.assertEqual([], errors)
                self.assertEqual(1, len(results))
                result = results[0]
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

    def test_empty_wav_does_not_claim_success_or_write_output(self):
        self.write_wav(self.source, duration_ms=0)
        results, errors = self.run_worker()
        self.assertEqual([], errors)
        self.assertEqual("failed", results[0].status)
        self.assertIsNone(results[0].output_path)
        self.recognize.assert_not_called()

    def test_network_request_receives_timeout_and_timeout_is_failure(self):
        with patch.object(proje.sr.Recognizer, "recognize_google", REAL_RECOGNIZE_GOOGLE), patch.object(
            proje.sr.AudioData, "get_flac_data", return_value=b"fake flac"
        ), patch("speech_recognition.recognizers.google.urlopen", side_effect=TimeoutError) as request:
            results, errors = self.run_worker()
        self.assertEqual([], errors)
        self.assertEqual("failed", results[0].status)
        self.assertIn("zaman aşımı", results[0].errors[0])
        self.assertEqual(30, request.call_args.kwargs["timeout"])

    def test_partial_and_failed_results_show_the_correct_message(self):
        self.write_wav(self.source, duration_ms=50100)
        for responses, message in [
            (["first", proje.sr.RequestError("offline")], "warning"),
            ([proje.sr.RequestError("offline")] * 2, "critical"),
        ]:
            with self.subTest(message=message):
                self.messages.reset_mock()
                self.recognize.side_effect = responses
                dialog = QtWidgets.QDialog()
                ui = proje.Ui_Dialog()
                ui.setupUi(dialog)
                ui.path = str(self.source)
                ui.donustur()
                self.assertTrue(ui.thread.wait(5000))
                self.app.processEvents()
                getattr(self.messages, message).assert_called_once()
                self.messages.information.assert_not_called()
                self.assertEqual(message == "critical", ui.label_3.isHidden())
                self.assertTrue(ui.pushButton.isEnabled())
                self.assertTrue(ui.pushButton_2.isEnabled())
                dialog.close()


if __name__ == "__main__":
    unittest.main()
