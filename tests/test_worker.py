import unittest
from contextlib import contextmanager, nullcontext
from unittest.mock import patch

from core.backend import ConversionResult
from core.engines import RecognitionOptions
from core.media_converter import MediaConversionError
from eski.worker import AudioToTextThread


class WorkerTests(unittest.TestCase):
    def test_forwards_service_progress_and_result(self):
        result = ConversionResult("success", "text", 2, 2, "audio.txt")
        worker = AudioToTextThread("audio.wav")
        results, progress, errors = [], [], []
        worker.done.connect(results.append)
        worker.progress.connect(progress.append)
        worker.error.connect(errors.append)

        def convert(file_path, progress_callback, *, output_source_path, recognition_options):
            self.assertEqual("prepared.wav", file_path)
            self.assertEqual("audio.wav", output_source_path)
            self.assertEqual(RecognitionOptions(), recognition_options)
            progress_callback(50)
            progress_callback(100)
            return result

        with patch("eski.worker.prepare_wav", return_value=nullcontext("prepared.wav")), patch(
            "eski.worker.backend.convert_audio", side_effect=convert
        ):
            worker.run()
        self.assertEqual([50, 100], progress)
        self.assertEqual([result], results)
        self.assertEqual([], errors)

    def test_service_exception_emits_error_without_success(self):
        worker = AudioToTextThread("audio.wav")
        results, errors = [], []
        worker.done.connect(results.append)
        worker.error.connect(errors.append)
        with patch("eski.worker.prepare_wav", return_value=nullcontext("prepared.wav")), patch(
            "eski.worker.backend.convert_audio", side_effect=PermissionError("output denied")
        ):
            worker.run()
        self.assertEqual([], results)
        self.assertEqual(1, len(errors))
        self.assertIn("output denied", errors[0])

    def test_preparation_error_skips_recognition(self):
        worker = AudioToTextThread("silent.mp4")
        results, errors = [], []
        worker.done.connect(results.append)
        worker.error.connect(errors.append)
        with patch("eski.worker.prepare_wav", side_effect=MediaConversionError("no audio")), patch(
            "eski.worker.backend.convert_audio"
        ) as convert:
            worker.run()
        convert.assert_not_called()
        self.assertEqual([], results)
        self.assertIn("no audio", errors[0])

    def test_prepared_audio_is_released_after_backend_failure(self):
        released = []

        @contextmanager
        def prepare(file_path):
            try:
                yield "prepared.wav"
            finally:
                released.append(file_path)

        with patch("eski.worker.prepare_wav", prepare), patch(
            "eski.worker.backend.convert_audio", side_effect=PermissionError("output denied")
        ):
            AudioToTextThread("audio.mp3").run()
        self.assertEqual(["audio.mp3"], released)

    def test_selected_engine_options_reach_backend(self):
        options = RecognitionOptions(engine="faster_whisper", model="base")
        worker = AudioToTextThread("audio.mp3", options)
        with patch("eski.worker.prepare_wav", return_value=nullcontext("prepared.wav")), patch(
            "eski.worker.backend.convert_audio"
        ) as convert:
            worker.run()
        self.assertIs(options, convert.call_args.kwargs["recognition_options"])

    def test_invalid_settings_fail_before_media_preparation(self):
        worker = AudioToTextThread("audio.mp3", RecognitionOptions(engine="unknown"))
        errors = []
        worker.error.connect(errors.append)
        with patch("eski.worker.prepare_wav") as prepare:
            worker.run()
        prepare.assert_not_called()
        self.assertEqual(1, len(errors))


if __name__ == "__main__":
    unittest.main()
