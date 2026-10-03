import unittest
from unittest.mock import patch

from backend import ConversionResult
from worker import AudioToTextThread


class WorkerTests(unittest.TestCase):
    def test_forwards_service_progress_and_result(self):
        result = ConversionResult("success", "text", 2, 2, "audio.txt")
        worker = AudioToTextThread("audio.wav")
        results, progress, errors = [], [], []
        worker.done.connect(results.append)
        worker.progress.connect(progress.append)
        worker.error.connect(errors.append)

        def convert(file_path, progress_callback):
            self.assertEqual("audio.wav", file_path)
            progress_callback(50)
            progress_callback(100)
            return result

        with patch("worker.backend.convert_audio", side_effect=convert):
            worker.run()
        self.assertEqual([50, 100], progress)
        self.assertEqual([result], results)
        self.assertEqual([], errors)

    def test_service_exception_emits_error_without_success(self):
        worker = AudioToTextThread("audio.wav")
        results, errors = [], []
        worker.done.connect(results.append)
        worker.error.connect(errors.append)
        with patch("worker.backend.convert_audio", side_effect=PermissionError("output denied")):
            worker.run()
        self.assertEqual([], results)
        self.assertEqual(1, len(errors))
        self.assertIn("output denied", errors[0])


if __name__ == "__main__":
    unittest.main()
