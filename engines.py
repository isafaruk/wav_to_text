"""Selectable Turkish speech engines; optional dependencies load on demand."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import import_module
import json
import os
from pathlib import Path
import re
import time

import speech_recognition as sr

from local_engine_process import local_session


@dataclass(frozen=True)
class EngineSpec:
    name: str
    description: str
    models: tuple[str, ...] = ()
    key_env: str = ""


LOCAL_MODELS = ("tiny", "base", "small", "medium", "large-v3")
ENGINES = {
    "google": EngineSpec("Google", "Mevcut servis. İnternet gerekir; ayrıca API anahtarı istemez."),
    "faster_whisper": EngineSpec(
        "Faster Whisper (yerel)",
        "Ses bilgisayarda işlenir. İlk kullanımda model indirilir. "
        "Eski bilgisayarlarda tiny/base ve CPU ile başlayın.", LOCAL_MODELS),
    "whisper": EngineSpec(
        "Whisper (yerel)",
        "Ses bilgisayarda işlenir. İlk kullanımda model indirilir. "
        "Büyük modeller daha fazla bellek ve işlem gücü ister.", LOCAL_MODELS),
    "vosk": EngineSpec(
        "Vosk (yerel, hafif)",
        "Çevrimdışı çalışır. İndirilip açılmış Türkçe Vosk modelinin klasörünü seçin."),
    "groq": EngineSpec(
        "Groq Whisper (bulut)",
        "Ses Groq'a gönderilir. Ücretsiz kotalı planı vardır; hesabınızın limitleri geçerlidir.",
        ("whisper-large-v3-turbo", "whisper-large-v3"), "GROQ_API_KEY"),
    "azure": EngineSpec(
        "Azure Speech (bulut)",
        "Ses Azure'a gönderilir. F0 planında ücretsiz kota vardır; anahtar ve bölge gerekir.",
        key_env="AZURE_SPEECH_KEY"),
    "openai": EngineSpec(
        "OpenAI (bulut, ücretli)",
        "Ses OpenAI'a gönderilir. API kullanımı ücretlidir; API anahtarı gerekir.",
        ("whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"), "OPENAI_API_KEY"),
}


@dataclass(frozen=True)
class RecognitionOptions:
    engine: str = "google"
    model: str = ""
    device: str = "cpu"
    api_key: str = field(default="", repr=False)
    region: str = ""
    model_path: str = ""


class EngineConfigurationError(ValueError):
    """A selected engine needs a package, model or configuration."""


def _api_key(options):
    return options.api_key.strip() or os.environ.get(ENGINES[options.engine].key_env, "").strip()


def _region(options):
    return options.region.strip() or os.environ.get("AZURE_SPEECH_REGION", "").strip()


def _model_path(options):
    return options.model_path.strip() or os.environ.get("VOSK_MODEL_PATH", "").strip()


def validate_options(options):
    """Check settings without importing heavy models or sending requests."""
    if options.engine not in ENGINES:
        raise EngineConfigurationError("Bilinmeyen tanıma motoru.")
    spec = ENGINES[options.engine]
    if options.model and options.model not in spec.models:
        raise EngineConfigurationError("Seçilen model bu tanıma motoru için desteklenmiyor.")
    if options.device not in ("cpu", "cuda"):
        raise EngineConfigurationError("İşlem aygıtı CPU veya NVIDIA GPU olmalıdır.")
    if spec.key_env and not _api_key(options):
        raise EngineConfigurationError(
            "API anahtarını girin veya {0} ortam değişkenini tanımlayın.".format(spec.key_env))
    if options.engine == "azure" and not re.fullmatch(r"[a-z0-9-]+", _region(options)):
        raise EngineConfigurationError(
            "Azure bölgesini girin (örn. westeurope) veya AZURE_SPEECH_REGION tanımlayın.")
    if options.engine == "vosk" and (
        not _model_path(options) or not Path(_model_path(options)).is_dir()
    ):
        raise EngineConfigurationError(
            "Türkçe Vosk modelinin açılmış klasörünü seçin veya VOSK_MODEL_PATH tanımlayın.")


def _load(module, requirements):
    try:
        return import_module(module)
    except (ImportError, OSError) as exc:
        raise EngineConfigurationError(
            "Bu motorun bağımlılıkları eksik veya uyumsuz. Kurulum: "
            "python -m pip install -r {0}".format(requirements)
        ) from exc


def _audio_array(audio, np):
    # AudioData is mono PCM; normalize signed 16-bit samples for Whisper.
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def _local_whisper(options):
    requirements = "requirements-{0}.txt".format(options.engine.replace("_", "-"))
    np = _load("numpy", requirements)
    module = _load("faster_whisper" if options.engine == "faster_whisper" else "whisper", requirements)
    model_name = options.model or LOCAL_MODELS[0]
    try:
        if options.engine == "faster_whisper":
            model = module.WhisperModel(
                model_name, device=options.device,
                compute_type="int8" if options.device == "cpu" else "float16",
                cpu_threads=min(4, os.cpu_count() or 1),
            )
        else:
            model = module.load_model(model_name, device=options.device)
    except Exception as exc:
        raise EngineConfigurationError(
            "Yerel model yüklenemedi. İlk indirme için interneti, boş alanı ve "
            "aygıt desteğini kontrol edin; CPU ve daha küçük bir model deneyin."
        ) from exc

    def transcribe(audio):
        samples = _audio_array(audio, np)
        if options.engine == "faster_whisper":
            segments, _ = model.transcribe(samples, language="tr", task="transcribe", beam_size=5)
            return " ".join(segment.text.strip() for segment in segments).strip()
        return model.transcribe(
            samples, language="tr", task="transcribe", fp16=options.device == "cuda"
        )["text"]

    return transcribe


def _vosk(options):
    module = _load("vosk", "requirements-vosk.txt")
    try:
        model = module.Model(_model_path(options))
    except Exception as exc:
        raise EngineConfigurationError("Vosk modeli yüklenemedi. Açılmış Türkçe model klasörünü seçin.") from exc

    def transcribe(audio):
        recognizer = module.KaldiRecognizer(model, 16000)
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        parts = []
        for offset in range(0, len(raw), 4000):
            if recognizer.AcceptWaveform(raw[offset:offset + 4000]):
                parts.append(json.loads(recognizer.Result()).get("text", ""))
        parts.append(json.loads(recognizer.FinalResult()).get("text", ""))
        return " ".join(part for part in parts if part).strip()

    return transcribe


@contextmanager
def recognition_session(recognizer, options):
    """Load one model/client per conversion, reused for all its audio chunks."""
    validate_options(options)
    if options.engine == "google":
        yield lambda audio: recognizer.recognize_google(audio, language="tr-tr")
    elif options.engine in ("faster_whisper", "whisper", "vosk"):
        with local_session(options) as transcribe:
            yield transcribe
    elif options.engine == "azure":
        yield lambda audio: recognizer.recognize_azure(
            audio, key=_api_key(options), location=_region(options), language="tr-TR")
    else:
        sdk = _load(options.engine, "requirements-cloud.txt")
        client_type = sdk.Groq if options.engine == "groq" else sdk.OpenAI
        base_url = "https://api.groq.com/openai/v1" if options.engine == "groq" else "https://api.openai.com/v1"
        with client_type(
            api_key=_api_key(options), base_url=base_url,
            timeout=recognizer.operation_timeout, max_retries=0,
        ) as client:
            last_request = None

            def transcribe(audio):
                nonlocal last_request
                # Space Groq calls for the documented Free plan's 20 requests/minute.
                if options.engine == "groq" and last_request is not None:
                    time.sleep(max(0, 3.1 - (time.monotonic() - last_request)))
                last_request = time.monotonic()
                try:
                    result = client.audio.transcriptions.create(
                        file=("audio.wav", audio.get_wav_data(convert_rate=16000, convert_width=2), "audio/wav"),
                        model=options.model or ENGINES[options.engine].models[0],
                        language="tr", response_format="json",
                    )
                except sdk.APITimeoutError as exc:
                    raise TimeoutError("Tanıma isteği zaman aşımına uğradı.") from exc
                except sdk.APIError as exc:
                    code = getattr(exc, "status_code", None)
                    if code in (401, 403):
                        message = "API anahtarı veya servis erişim izni geçersiz."
                    elif code == 429:
                        message = "Servis kotası ya da istek sınırı aşıldı."
                    else:
                        message = "Tanıma servisine ulaşılamadı."
                    # Do not expose raw SDK errors, which may contain request details.
                    raise sr.RequestError(message) from exc
                return result.text

            yield transcribe
