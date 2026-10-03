import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import backend


class ConversionTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "chunk1.wav"
        self.write_wav(self.source)
        self.recognize = self.enterContext(
            patch.object(backend.sr.Recognizer, "recognize_google", return_value="first")
        )

    @staticmethod
    def write_wav(path, duration_ms=100):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x01\x00" * (8 * duration_ms))
