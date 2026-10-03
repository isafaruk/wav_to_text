"""Exercise real optional SDK serialization with an in-memory HTTP transport."""

from importlib import import_module
from importlib.util import find_spec
import unittest
from unittest.mock import patch

import speech_recognition as sr

from engines import RecognitionOptions, recognition_session


@unittest.skipUnless(all(find_spec(name) for name in ("openai", "groq", "httpx")),
                     "Optional cloud SDKs are not installed")
class CloudSDKTests(unittest.TestCase):
    def test_real_sdk_audio_upload_and_response_parsing_without_network(self):
        import httpx

        audio = sr.AudioData(b"\x00\x00" * 800, 8000, 2)
        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 30
        for engine, class_name, host in [
            ("groq", "Groq", "api.groq.com"),
            ("openai", "OpenAI", "api.openai.com"),
        ]:
            for status in (200, 429):
                with self.subTest(engine=engine, status=status):
                    requests = []

                    def respond(request):
                        requests.append(request)
                        if status == 200:
                            return httpx.Response(200, json={"text": "Merhaba dünya."})
                        return httpx.Response(429, json={"error": {"message": "quota exhausted"}})

                    sdk = import_module(engine)
                    original_client = getattr(sdk, class_name)

                    def client_factory(**kwargs):
                        return original_client(**kwargs, http_client=httpx.Client(
                            transport=httpx.MockTransport(respond)))

                    with patch.object(sdk, class_name, side_effect=client_factory), recognition_session(
                        recognizer, RecognitionOptions(engine=engine, api_key="test-key")
                    ) as transcribe:
                        if status == 200:
                            self.assertEqual("Merhaba dünya.", transcribe(audio))
                        else:
                            with self.assertRaisesRegex(sr.RequestError, "kota"):
                                transcribe(audio)
                    self.assertEqual(1, len(requests))  # No automatic retries on billed requests.
                    request = requests[0]
                    self.assertEqual(host, request.url.host)
                    self.assertTrue(request.url.path.endswith("/audio/transcriptions"))
                    self.assertEqual("Bearer test-key", request.headers["Authorization"])
                    body = request.read()
                    self.assertIn(b'filename="audio.wav"', body)
                    self.assertIn(b'RIFF', body)
                    self.assertIn(b'name="language"\r\n\r\ntr', body)
                    self.assertTrue(all(value == 30 for value in request.extensions["timeout"].values()))


if __name__ == "__main__":
    unittest.main()
