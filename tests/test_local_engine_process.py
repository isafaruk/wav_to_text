import multiprocessing
import os
import sys
import unittest
from unittest.mock import patch

import speech_recognition as sr

from core.engines import RecognitionOptions
from core.local_engine_process import LocalEngineError, local_session


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


def file_worker(connection, options):
    connection.send(("ready", None))
    path = connection.recv()
    assert isinstance(path, str)
    connection.send(("progress", 0))
    connection.send(("progress", 45))
    connection.send(("progress", 99))
    connection.send(("text", path))
    assert connection.recv() is None
    connection.close()


class LocalProcessTests(unittest.TestCase):
    def test_file_request_and_progress_cross_process_boundary(self):
        progress = []
        before = {p.pid for p in multiprocessing.active_children()}
        with patch("core.local_engine_process._serve", file_worker), local_session(
            RecognitionOptions(engine="faster_whisper"), progress_callback=progress.append
        ) as transcribe:
            self.assertEqual("recording.wav", transcribe("recording.wav"))
        self.assertEqual([0, 45, 99], progress)
        self.assertEqual(before, {p.pid for p in multiprocessing.active_children()})

    def test_audio_round_trip_reuses_process_without_gui_imports(self):
        before = {p.pid for p in multiprocessing.active_children()}
        with patch("core.local_engine_process._serve", echo_worker), local_session(RecognitionOptions()) as transcribe:
            audio = sr.AudioData(b"\x00\x00" * 100, 16000, 2)
            first = transcribe(audio)
            self.assertEqual(first, transcribe(audio))
            pid, rate, qt_loaded = first.split(":")
            self.assertNotEqual(os.getpid(), int(pid))
            self.assertEqual("16000", rate)
            self.assertEqual("False", qt_loaded)
        self.assertEqual(before, {p.pid for p in multiprocessing.active_children()})

    def test_model_failure_is_reported_and_process_is_reaped(self):
        with patch("core.local_engine_process._serve", failed_worker), self.assertRaisesRegex(
            LocalEngineError, "model unavailable"
        ), local_session(RecognitionOptions()):
            self.fail("The model did not load")

    def test_native_process_exit_becomes_error_instead_of_killing_gui(self):
        with patch("core.local_engine_process._serve", crashed_worker), self.assertRaisesRegex(
            LocalEngineError, "0x00000011"
        ), local_session(RecognitionOptions()):
            self.fail("The child process crashed")


if __name__ == "__main__":
    unittest.main()
