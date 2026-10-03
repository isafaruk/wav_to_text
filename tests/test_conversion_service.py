from contextlib import nullcontext
from threading import Event
from unittest.mock import patch

from backend import ConversionResult
from conversion_service import ConversionService
from helpers import ConversionTestCase


class ConversionServiceTests(ConversionTestCase):
    def test_real_backend_success_is_returned_as_plain_data(self):
        service = ConversionService()
        service.start(str(self.source), {})
        service._thread.join(timeout=5)
        state = service.snapshot()
        self.assertEqual("success", state["status"])
        self.assertEqual("first", state["text"])
        self.assertEqual(100, state["progress"])
        self.assertEqual(str(self.source.with_suffix(".txt")), state["output_path"])
        self.assertEqual(1, state["successful_chunks"])

    def test_running_job_cannot_be_replaced_or_abandoned(self):
        started, release = Event(), Event()
        service = ConversionService()

        def convert(*args, **kwargs):
            started.set()
            release.wait(5)
            return ConversionResult("failed", "", 0, 1, None)

        with patch("conversion_service.convert_audio", side_effect=convert):
            service.start(str(self.source), {})
            try:
                self.assertTrue(started.wait(5))
                self.assertFalse(service.try_close())
                with self.assertRaisesRegex(ValueError, "Devam eden"):
                    service.start(str(self.source), {})
            finally:
                release.set()
                service._thread.join(5)
        self.assertTrue(service.try_close())
        with self.assertRaisesRegex(ValueError, "kapanıyor"):
            service.start(str(self.source), {})

    def test_error_restores_service_for_retry(self):
        service = ConversionService()
        with patch("conversion_service.prepare_wav", side_effect=OSError("bad media")):
            service.start(str(self.source), {})
            service._thread.join(5)
        self.assertEqual("error", service.snapshot()["status"])
        self.assertEqual(["bad media"], service.snapshot()["errors"])
        service.start(str(self.source), {})
        service._thread.join(5)
        self.assertEqual("success", service.snapshot()["status"])
        self.assertEqual([], service.snapshot()["errors"])

    def test_partial_and_failed_results_remain_distinct(self):
        for status, successful, output in [("partial", 1, "partial.txt"), ("failed", 0, None)]:
            with self.subTest(status=status):
                result = ConversionResult(status, "text", successful, 2, output, ("chunk error",))
                service = ConversionService()
                with patch("conversion_service.convert_audio", return_value=result):
                    service.start(str(self.source), {})
                    service._thread.join(5)
                self.assertEqual(status, service.snapshot()["status"])
                self.assertEqual(output, service.snapshot()["output_path"])

    def test_settings_are_validated_and_never_included_in_state(self):
        service = ConversionService()
        with self.assertRaises(ValueError):
            service.start(str(self.source), {"surprise": "value"})
        with self.assertRaises(ValueError):
            service.start(str(self.source), {"engine": 123})
        result = ConversionResult("failed", "", 0, 1, None)
        with patch("conversion_service.convert_audio", return_value=result):
            service.start(str(self.source), {"engine": "groq", "api_key": "private-key"})
            service._thread.join(5)
        self.assertNotIn("private-key", str(service.snapshot()))
        state = service.snapshot()
        state["progress"] = 999
        self.assertNotEqual(999, service.snapshot()["progress"])

    def test_media_output_path_and_engine_settings_are_forwarded(self):
        media = self.root / "recording.mp4"
        media.write_bytes(b"fake media")
        service = ConversionService()
        result = ConversionResult("success", "text", 1, 1, "recording.txt")
        with patch("conversion_service.prepare_wav", return_value=nullcontext(str(self.source))), patch(
            "conversion_service.convert_audio", return_value=result
        ) as convert:
            service.start(str(media), {"engine": "faster_whisper", "model": "tiny"})
            service._thread.join(5)
        self.assertEqual(str(media), convert.call_args.kwargs["output_source_path"])
        self.assertEqual("faster_whisper", convert.call_args.kwargs["recognition_options"].engine)
