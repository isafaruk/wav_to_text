from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch
import multiprocessing
import subprocess
import time
import unittest

from core.backend import ConversionResult, convert_audio
from core.engines import RecognitionOptions, _local_whisper, _segment_paragraphs, validate_options
from core.job_control import ConversionCancelled, JobControl
from core.local_engine_process import local_session
from core.media_converter import prepare_wav
from core.transcript_checkpoint import TranscriptCheckpoint
from services.conversion_service import ConversionService
from helpers import ConversionTestCase


def waiting_model(connection, options):
    connection.send(("event", {"loading_started": True}))
    time.sleep(20)


def streaming_model(connection, options):
    connection.send(("ready", None))
    connection.recv()
    connection.send(("event", {"append_text": "Türkçe ilk bölüm."}))
    time.sleep(20)


class ProcessCancellationTests(unittest.TestCase):
    def test_cancel_during_loading_and_inference_reaps_real_children(self):
        for target in (waiting_model, streaming_model):
            with self.subTest(target=target.__name__):
                received = []
                control = JobControl()

                def on_event(event):
                    received.append(event)
                    if "loading_started" in event or "append_text" in event:
                        control.cancelled.set()

                control.on_event = on_event
                before = {p.pid for p in multiprocessing.active_children()}
                started = time.monotonic()
                with patch("core.local_engine_process._serve", target), self.assertRaises(ConversionCancelled):
                    with local_session(RecognitionOptions(engine="faster_whisper"), control=control) as transcribe:
                        transcribe("audio.wav")
                self.assertLess(time.monotonic() - started, 8)
                self.assertTrue(received)
                self.assertEqual(before, {p.pid for p in multiprocessing.active_children()})


class ControlledConversionTests(ConversionTestCase):
    def test_live_text_is_saved_before_completion_and_survives_cancel_and_retry(self):
        emitted, release = Event(), Event()
        service = ConversionService()

        def convert(*args, control, **kwargs):
            control.emit(phase="transcribing", duration_seconds=120)
            control.emit(append_text="İlk bölüm.", processed_seconds=30)
            emitted.set()
            release.wait(5)
            control.check()

        with patch("services.conversion_service.convert_audio", side_effect=convert):
            service.start(str(self.source), {"engine": "faster_whisper"})
            try:
                self.assertTrue(emitted.wait(5))
                state = service.snapshot()
                self.assertEqual("İlk bölüm.", state["text"])
                checkpoint = Path(state["checkpoint_path"])
                self.assertIn("İlk bölüm.", checkpoint.read_text(encoding="utf-8"))
                self.assertEqual("cancelling", service.cancel()["status"])
                self.assertFalse(service.try_close())
                with self.assertRaises(ValueError):
                    service.start(str(self.source), {})
            finally:
                release.set()
                service._thread.join(5)
        self.assertEqual("cancelled", service.snapshot()["status"])
        self.assertFalse(self.source.with_suffix(".txt").exists())
        self.assertTrue(checkpoint.exists())
        service.start(str(self.source), {})
        service._thread.join(5)
        self.assertEqual("success", service.snapshot()["status"])
        self.assertIsNone(service.snapshot()["checkpoint_path"])
        self.assertTrue(checkpoint.exists(), "A retry must preserve the previous job's recovery file")

    def test_cloud_cancel_saves_inflight_result_without_starting_next_request(self):
        self.write_wav(self.source, duration_ms=50100)
        events = []
        control = JobControl(events.append)

        def recognize(*args, **kwargs):
            control.cancelled.set()
            return "Tamamlanan istek"

        self.recognize.side_effect = recognize
        with self.assertRaises(ConversionCancelled):
            convert_audio(str(self.source), control=control)
        self.recognize.assert_called_once()
        self.assertTrue(any(e.get("append_text") == "Tamamlanan istek" for e in events))
        self.assertFalse(self.source.with_suffix(".txt").exists())

    def test_success_replaces_recovery_with_final_output(self):
        service = ConversionService()
        service.start(str(self.source), {})
        service._thread.join(5)
        state = service.snapshot()
        self.assertEqual("success", state["status"])
        self.assertEqual([], list(self.root.glob("*.partial.txt")))
        self.assertEqual("first", Path(state["output_path"]).read_text(encoding="utf-8"))
        self.assertEqual("success", service.cancel()["status"])

    def test_failure_retains_checkpoint_and_live_text(self):
        service = ConversionService()

        def fail(*args, control, **kwargs):
            control.emit(append_text="Kurtarılacak metin")
            raise RuntimeError("model crashed")

        with patch("services.conversion_service.convert_audio", side_effect=fail):
            service.start(str(self.source), {})
            service._thread.join(5)
        state = service.snapshot()
        self.assertEqual("error", state["status"])
        self.assertEqual("Kurtarılacak metin", state["text"])
        self.assertIn(state["text"], Path(state["checkpoint_path"]).read_text(encoding="utf-8"))

    def test_checkpoint_failure_does_not_lose_live_or_final_text(self):
        service = ConversionService()
        with patch.object(TranscriptCheckpoint, "append", side_effect=PermissionError):
            service.start(str(self.source), {})
            service._thread.join(5)
        state = service.snapshot()
        self.assertEqual("success", state["status"])
        self.assertEqual("first", state["text"])
        self.assertTrue(state["warnings"])

    def test_eta_excludes_model_loading_and_is_unavailable_without_progress(self):
        emitted, release = Event(), Event()
        service = ConversionService()

        def convert(*args, control, **kwargs):
            control.emit(phase="transcribing", duration_seconds=120, processed_seconds=30)
            emitted.set()
            release.wait(5)
            return ConversionResult("failed", "", 0, 1, None)

        with patch("services.conversion_service.convert_audio", side_effect=convert):
            service.start(str(self.source), {})
            try:
                self.assertTrue(emitted.wait(5))
                with patch("services.conversion_service.monotonic", return_value=service._transcribing_started + 10):
                    state = service.snapshot()
                self.assertEqual(3, state["speed"])
                self.assertEqual(30, state["remaining_seconds"])
                service._update(progress_available=False)
                self.assertIsNone(service.snapshot()["remaining_seconds"])
            finally:
                release.set()
                service._thread.join(5)

    def test_cancel_at_save_boundary_cannot_override_committed_success(self):
        service = ConversionService()
        reached, release = Event(), Event()

        def convert(*args, control, **kwargs):
            control.emit(phase="saving")
            reached.set()
            release.wait(5)
            return ConversionResult("success", "text", 1, 1, "result.txt")

        with patch("services.conversion_service.convert_audio", side_effect=convert):
            service.start(str(self.source), {})
            try:
                self.assertTrue(reached.wait(5))
                self.assertFalse(service.snapshot()["can_cancel"])
                self.assertEqual("running", service.cancel()["status"])
            finally:
                release.set()
                service._thread.join(5)
        self.assertEqual("success", service.snapshot()["status"])

    def test_checkpoint_does_not_overwrite_an_existing_path(self):
        checkpoint = TranscriptCheckpoint(self.source)
        checkpoint.path.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            checkpoint.append("new")
        self.assertEqual("existing", checkpoint.path.read_text(encoding="utf-8"))

    def test_controlled_media_conversion_and_cleanup(self):
        # A non-PCM WAV goes through the cancellable FFmpeg code path.
        from core.media_converter import get_ffmpeg_exe
        source = self.root / "input.flac"
        subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(self.source), str(source)],
                       check=True, capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with prepare_wav(source, control=JobControl()) as prepared:
            self.assertTrue(Path(prepared).is_file())
        self.assertFalse(Path(prepared).parent.exists())

    def test_media_cancel_kills_process_and_cleans_partial_wav(self):
        source = self.root / "input.mp3"
        source.write_bytes(b"fake")
        control = JobControl()
        destinations = []
        process = MagicMock()
        process.__enter__.return_value = process
        process.poll.return_value = None

        def start(command, **kwargs):
            destinations.append(Path(command[-1]))
            destinations[-1].write_bytes(b"partial WAV")
            control.cancelled.set()
            return process

        with patch("core.media_converter.subprocess.Popen", side_effect=start):
            with self.assertRaises(ConversionCancelled), prepare_wav(source, control=control):
                self.fail("Cancelled preparation must not yield a WAV")
        process.kill.assert_called_once()
        process.communicate.assert_called_once()
        self.assertFalse(destinations[0].parent.exists())


class LiveEngineTests(unittest.TestCase):
    def test_incremental_text_matches_final_paragraphs_and_progress(self):
        events = []
        result = _segment_paragraphs([(0, 2, " ilk "), (5, 10, "ikinci"), (61, 62, "son")],
                                     62, event_callback=events.append)
        self.assertEqual("ilk ikinci\n\nson", result)
        self.assertEqual(result, "".join(event.get("append_text", "") for event in events))
        self.assertEqual(62, events[-1]["processed_seconds"])

    def test_turbo_gpu_quantization_and_explicit_cpu_threads_are_used(self):
        module = MagicMock()
        for compute in ("int8_float16", "float16"):
            options = RecognitionOptions(engine="faster_whisper", model="turbo", device="cuda",
                                         gpu_compute_type=compute, cpu_threads="2")
            with patch("core.engines.os.cpu_count", return_value=8):
                validate_options(options)
            with patch("core.engines._load", return_value=module):
                _local_whisper(options)
            self.assertEqual(compute, module.WhisperModel.call_args.kwargs["compute_type"])
            self.assertEqual(2, module.WhisperModel.call_args.kwargs["cpu_threads"])
            self.assertEqual("turbo", module.WhisperModel.call_args.args[0])

    def test_invalid_performance_options_are_rejected(self):
        for options in [RecognitionOptions(cpu_threads="0"), RecognitionOptions(cpu_threads="-1"),
                        RecognitionOptions(cpu_threads="1000"), RecognitionOptions(cpu_threads="nan"),
                        RecognitionOptions(cpu_threads=4), RecognitionOptions(gpu_compute_type="invalid")]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                validate_options(options)
