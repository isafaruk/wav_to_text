import json
from contextlib import contextmanager
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import speech_recognition as sr

import backend
import engines
from engines import EngineConfigurationError, RecognitionOptions, recognition_session, validate_options
from helpers import ConversionTestCase


class EngineTests(ConversionTestCase):
    def setUp(self):
        super().setUp()
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 30
        self.audio = sr.AudioData(b"\x00\x00" * 8000, 8000, 2)
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        # Model adapters are unit-tested in-process with fake native libraries.
        # Real process isolation is covered separately in test_local_engine_process.
        @contextmanager
        def model_session(options):
            yield engines._vosk(options) if options.engine == "vosk" else engines._local_whisper(options)

        self.enterContext(patch("engines.local_session", model_session))

    def test_google_stays_default_without_optional_imports(self):
        with patch("engines.import_module") as load:
            result = backend.convert_audio(str(self.source))
        self.assertEqual("success", result.status)
        self.recognize.assert_called_once()
        self.assertEqual("tr-tr", self.recognize.call_args.kwargs["language"])
        load.assert_not_called()

    def test_missing_optional_package_explains_installation(self):
        with patch("engines.import_module", side_effect=ImportError), self.assertRaisesRegex(
            EngineConfigurationError, "requirements-faster-whisper.txt"
        ), recognition_session(self.recognizer, RecognitionOptions(engine="faster_whisper")):
            self.fail("An unavailable engine must not start recognition")

    def test_invalid_options_are_rejected_without_network(self):
        cases = [
            RecognitionOptions(engine="missing"),
            RecognitionOptions(model="tiny"),
            RecognitionOptions(engine="faster_whisper", model="tiny.en"),
            RecognitionOptions(device="unsupported"),
            RecognitionOptions(engine="groq"),
            RecognitionOptions(engine="azure", api_key="key", region="../other-host"),
            RecognitionOptions(engine="vosk", model_path=str(self.root / "missing")),
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(EngineConfigurationError):
                validate_options(options)

    def test_api_key_is_not_in_configuration_repr(self):
        self.assertNotIn("secret-key", repr(RecognitionOptions(api_key="secret-key")))

    def test_azure_uses_turkish_and_explicit_settings_override_environment(self):
        with patch.dict(os.environ, {"AZURE_SPEECH_KEY": "env-key", "AZURE_SPEECH_REGION": "eastus"}), patch.object(
            self.recognizer, "recognize_azure", return_value="merhaba"
        ) as azure:
            for options, key, region in [
                (RecognitionOptions(engine="azure"), "env-key", "eastus"),
                (RecognitionOptions(engine="azure", api_key="ui-key", region="westeurope"), "ui-key", "westeurope"),
            ]:
                with recognition_session(self.recognizer, options) as transcribe:
                    self.assertEqual("merhaba", transcribe(self.audio))
                azure.assert_called_with(self.audio, key=key, location=region, language="tr-TR")

    def test_faster_whisper_loads_once_for_multiple_chunks_on_cpu(self):
        self.write_wav(self.source, duration_ms=50100)
        module = MagicMock()
        module.WhisperModel.return_value.transcribe.side_effect = [
            (iter([SimpleNamespace(text=" ilk "), SimpleNamespace(text=" parça ")]), None),
            (iter([SimpleNamespace(text=" ikinci ")]), None),
        ]
        with patch("engines.import_module", return_value=module), patch(
            "engines._audio_array", return_value="samples"
        ), patch("engines.os.cpu_count", return_value=8):
            result = backend.convert_audio(str(self.source), recognition_options=RecognitionOptions(
                engine="faster_whisper", model="base"))
        module.WhisperModel.assert_called_once_with("base", device="cpu", compute_type="int8", cpu_threads=4)
        self.assertEqual(2, module.WhisperModel.return_value.transcribe.call_count)
        module.WhisperModel.return_value.transcribe.assert_called_with(
            "samples", language="tr", task="transcribe", beam_size=5)
        self.assertEqual("ilk parça\n\nikinci", result.text)
        self.recognize.assert_not_called()

    def test_original_whisper_is_loaded_once_and_uses_float32_on_cpu(self):
        module = MagicMock()
        module.load_model.return_value.transcribe.return_value = {"text": "merhaba"}
        with patch("engines.import_module", return_value=module), patch(
            "engines._audio_array", return_value="samples"
        ), recognition_session(self.recognizer, RecognitionOptions(engine="whisper")) as transcribe:
            self.assertEqual("merhaba", transcribe(self.audio))
            transcribe(self.audio)
        module.load_model.assert_called_once_with("tiny", device="cpu")
        module.load_model.return_value.transcribe.assert_called_with(
            "samples", language="tr", task="transcribe", fp16=False)

    def test_model_load_error_is_actionable(self):
        module = MagicMock()
        module.WhisperModel.side_effect = RuntimeError("incompatible CPU")
        with patch("engines.import_module", return_value=module), self.assertRaisesRegex(
            EngineConfigurationError, "daha küçük bir model"
        ), recognition_session(self.recognizer, RecognitionOptions(engine="faster_whisper")):
            self.fail("The model did not load")

    def test_vosk_keeps_intermediate_utterances_and_reuses_model(self):
        module = MagicMock()
        kaldi = module.KaldiRecognizer.return_value
        kaldi.AcceptWaveform.return_value = True
        kaldi.Result.return_value = json.dumps({"text": "ilk"})
        kaldi.FinalResult.return_value = json.dumps({"text": "son"})
        audio = sr.AudioData(b"\x00\x00" * 3000, 16000, 2)
        options = RecognitionOptions(engine="vosk", model_path=str(self.root))
        with patch("engines.import_module", return_value=module), recognition_session(
            self.recognizer, options
        ) as transcribe:
            self.assertEqual("ilk ilk son", transcribe(audio))
            transcribe(audio)
        module.Model.assert_called_once_with(str(self.root))
        self.assertEqual(2, module.KaldiRecognizer.call_count)
        module.KaldiRecognizer.assert_called_with(module.Model.return_value, 16000)

    def cloud_sdk(self):
        class APIError(Exception):
            status_code = None

        class APITimeoutError(APIError):
            pass

        sdk = MagicMock(APIError=APIError, APITimeoutError=APITimeoutError)
        return sdk

    def test_cloud_clients_reuse_connection_select_model_and_close(self):
        for engine, client_name, base_url in [
            ("groq", "Groq", "https://api.groq.com/openai/v1"),
            ("openai", "OpenAI", "https://api.openai.com/v1"),
        ]:
            with self.subTest(engine=engine):
                sdk = self.cloud_sdk()
                factory = getattr(sdk, client_name)
                client = factory.return_value.__enter__.return_value
                client.audio.transcriptions.create.return_value = SimpleNamespace(text="merhaba")
                options = RecognitionOptions(engine=engine, model=engines.ENGINES[engine].models[-1])
                with patch.dict(os.environ, {engines.ENGINES[engine].key_env: "env-key"}), patch(
                    "engines.import_module", return_value=sdk
                ), patch("engines.time.sleep") as sleep, patch("engines.time.monotonic", return_value=1), recognition_session(
                    self.recognizer, options
                ) as transcribe:
                    self.assertEqual("merhaba", transcribe(self.audio))
                    transcribe(self.audio)
                factory.assert_called_once_with(api_key="env-key", base_url=base_url, timeout=30, max_retries=0)
                call = client.audio.transcriptions.create.call_args.kwargs
                self.assertEqual(options.model, call["model"])
                self.assertEqual("tr", call["language"])
                self.assertEqual("json", call["response_format"])
                self.assertTrue(call["file"][1].startswith(b"RIFF"))
                factory.return_value.__exit__.assert_called_once()
                if engine == "groq":
                    sleep.assert_called_once_with(3.1)
                else:
                    sleep.assert_not_called()

    def test_cloud_errors_preserve_partial_results_without_exposing_request_details(self):
        self.write_wav(self.source, duration_ms=50100)
        for engine, client_name in [("groq", "Groq"), ("openai", "OpenAI")]:
            for code, expected in [(401, "API anahtarı"), (429, "kota"), (500, "ulaşılamadı"), (None, "zaman aşımı")]:
                with self.subTest(engine=engine, code=code):
                    sdk = self.cloud_sdk()
                    error = (sdk.APIError if code else sdk.APITimeoutError)("secret-key")
                    error.status_code = code
                    client = getattr(sdk, client_name).return_value.__enter__.return_value
                    client.audio.transcriptions.create.side_effect = [SimpleNamespace(text="ilk"), error]
                    with patch("engines.import_module", return_value=sdk), patch("engines.time.sleep"):
                        result = backend.convert_audio(str(self.source), recognition_options=RecognitionOptions(
                            engine=engine, api_key="secret-key"))
                    self.assertEqual("partial", result.status)
                    self.assertIn(expected, result.errors[0])
                    self.assertNotIn("secret-key", result.text)
                    getattr(sdk, client_name).return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
