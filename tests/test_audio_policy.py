from contextlib import contextmanager
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import wave

import audio_policy
import backend
from engines import RecognitionOptions
from helpers import ConversionTestCase
from transcript_format import format_paragraphs


class AudioPolicyTests(ConversionTestCase):
    def test_google_and_azure_keep_short_requests(self):
        self.write_wav(self.source, duration_ms=100100)
        for engine in ("google", "azure"):
            calls, progress = [], []

            @contextmanager
            def session(*args, **kwargs):
                def transcribe(audio):
                    calls.append(len(audio.frame_data) / (audio.sample_rate * audio.sample_width))
                    return "metin"
                yield transcribe

            with self.subTest(engine=engine), patch("backend.recognition_session", session):
                result = backend.convert_audio(str(self.source), progress.append, recognition_options=RecognitionOptions(
                    engine=engine, api_key="key", region="westeurope"))
                self.assertEqual([50, 50, 0.1], calls)
                self.assertEqual([33, 66, 100], progress)
                self.assertEqual(3, result.total_chunks)

    def test_cloud_uploads_are_normalized_bounded_and_keep_the_tail(self):
        # A real recording just beyond the actual upload boundary: two requests.
        duration_ms = audio_policy.chunk_duration_ms("groq") + 100
        self.write_wav(self.source, duration_ms=duration_ms)
        for engine in ("groq", "openai"):
            uploads, progress, timeouts = [], [], []

            @contextmanager
            def session(recognizer, options):
                timeouts.append(recognizer.operation_timeout)
                def transcribe(audio):
                    uploads.append(audio.get_wav_data(convert_rate=16000, convert_width=2))
                    return "metin"
                yield transcribe

            with self.subTest(engine=engine), patch("backend.recognition_session", session):
                result = backend.convert_audio(str(self.source), progress.append, recognition_options=RecognitionOptions(
                    engine=engine, api_key="key"))
                self.assertEqual(2, len(uploads))
                frames = []
                for data in uploads:
                    self.assertLessEqual(len(data), audio_policy.MAX_UPLOAD_BYTES)
                    with wave.open(io.BytesIO(data), "rb") as audio:
                        self.assertEqual((1, 2, 16000), (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()))
                        frames.append(audio.getnframes())
                # Resampling can omit the final interpolated sample, never a block.
                self.assertLessEqual(abs(sum(frames) - duration_ms * 16), 1)
                self.assertGreater(frames[-1], 0)
                self.assertEqual([50, 100], progress)
                self.assertEqual([180], timeouts)
                self.assertEqual("success", result.status)

    def test_cloud_recording_below_upload_limit_is_not_split_at_50_seconds(self):
        self.write_wav(self.source, duration_ms=50100)
        for engine in ("groq", "openai"):
            transcribe = MagicMock(return_value="metin")

            @contextmanager
            def session(*args, **kwargs):
                yield transcribe

            with self.subTest(engine=engine), patch("backend.recognition_session", session):
                result = backend.convert_audio(str(self.source), recognition_options=RecognitionOptions(
                    engine=engine, api_key="key"))
                transcribe.assert_called_once()
                self.assertEqual(1, result.total_chunks)

    def test_local_whole_file_is_preserved_and_progress_never_reaches_100_early(self):
        original = self.source.read_bytes()
        events = []

        @contextmanager
        def session(recognizer, options, *, progress_callback):
            def transcribe(path):
                self.assertEqual(self.source, Path(path))
                for value in (0, 50, 40, 100):
                    progress_callback(value)
                self.assertEqual([0, 50, 99], events)
                return "tam kayıt"
            yield transcribe

        with patch("backend.recognition_session", session), patch("backend.AudioSegment.export") as export:
            result = backend.convert_audio(str(self.source), events.append, recognition_options=RecognitionOptions(
                engine="faster_whisper"))
        self.assertEqual([0, 50, 99, 100], events)
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(1, result.successful_chunks)
        export.assert_not_called()

    def test_empty_local_file_does_not_load_a_model(self):
        self.write_wav(self.source, duration_ms=0)
        with patch("backend.recognition_session") as session:
            result = backend.convert_audio(str(self.source), recognition_options=RecognitionOptions(engine="faster_whisper"))
        session.assert_not_called()
        self.assertEqual("failed", result.status)
        self.assertEqual(0, result.total_chunks)

    def test_long_transcript_keeps_sentences_and_existing_paragraphs(self):
        sentences = ["Türkçe bir cümle."] * 40
        text = " ".join(sentences) + "\n\nSon paragraf."
        formatted = format_paragraphs(text)
        self.assertGreater(formatted.count("\n\n"), 1)
        self.assertEqual(text.split(), formatted.split())
        self.assertTrue(all(part.endswith(".") for part in formatted.split("\n\n")))
        self.assertTrue(formatted.endswith("\n\nSon paragraf."))
