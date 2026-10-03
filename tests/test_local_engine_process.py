import multiprocessing
import os
import sys
import unittest
from unittest.mock import patch

import speech_recognition as sr

from engines import RecognitionOptions
from local_engine_process import LocalEngineError, local_session


def echo_worker(connection, options):
    connection.send(("ready", None))
    while (audio := connection.recv()) is not None:
        connection.send(("text", "{0}:{1}:{2}".format(
            os.getpid(), audio.sample_rate, "PyQt5.QtCore" in sys.modules)))
    connection.close()


def failed_worker(connection, options):
    connection.send(("error", "model unavailable"))
    connection.close()


def crashed_worker(connection, options):
    os._exit(17)


class LocalProcessTests(unittest.TestCase):
    def test_audio_round_trip_reuses_process_without_gui_imports(self):
        before = {p.pid for p in multiprocessing.active_children()}
        with patch("local_engine_process._serve", echo_worker), local_session(RecognitionOptions()) as transcribe:
            audio = sr.AudioData(b"\x00\x00" * 100, 16000, 2)
            first = transcribe(audio)
            self.assertEqual(first, transcribe(audio))
            pid, rate, qt_loaded = first.split(":")
            self.assertNotEqual(os.getpid(), int(pid))
            self.assertEqual("16000", rate)
            self.assertEqual("False", qt_loaded)
        self.assertEqual(before, {p.pid for p in multiprocessing.active_children()})

    def test_model_failure_is_reported_and_process_is_reaped(self):
        with patch("local_engine_process._serve", failed_worker), self.assertRaisesRegex(
            LocalEngineError, "model unavailable"
        ), local_session(RecognitionOptions()):
            self.fail("The model did not load")

    def test_native_process_exit_becomes_error_instead_of_killing_gui(self):
        with patch("local_engine_process._serve", crashed_worker), self.assertRaisesRegex(
            LocalEngineError, "0x00000011"
        ), local_session(RecognitionOptions()):
            self.fail("The child process crashed")


if __name__ == "__main__":
    unittest.main()
