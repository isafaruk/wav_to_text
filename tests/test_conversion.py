import os
import tempfile
import unittest
import wave
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

import proje


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


if __name__ == "__main__":
    unittest.main()
