"""Conversion jobs and plain-data results, independent of any frontend."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from threading import Lock, Thread
from time import monotonic

from core.backend import convert_audio
from core.engines import ENGINES, RecognitionOptions, validate_options
from core.media_converter import prepare_wav


class ConversionService:
    def __init__(self):
        self._lock = Lock()
        self._closed = False
        self._thread = None
        self._started = None
        self._state = {
            "status": "idle", "stage": "Bir kayıt seçerek başlayın.", "progress": 0,
            "text": "", "output_path": None, "errors": [], "elapsed_seconds": 0,
            "successful_chunks": 0, "total_chunks": 0, "source": "",
        }

    @staticmethod
    def configuration():
        return {"engines": [{"id": key, **asdict(spec)} for key, spec in ENGINES.items()]}

    def snapshot(self):
        with self._lock:
            state = deepcopy(self._state)
            if state["status"] == "running":
                state["elapsed_seconds"] = int(monotonic() - self._started)
            return state

    def start(self, file_path, settings):
        if not isinstance(settings, dict) or any(not isinstance(value, str) for value in settings.values()):
            raise ValueError("Motor ayarları geçersiz.")
        try:
            options = RecognitionOptions(**settings)
        except TypeError as exc:
            raise ValueError("Bilinmeyen motor ayarı.") from exc
        validate_options(options)
        if not file_path or not Path(file_path).is_file():
            raise ValueError("Önce geçerli bir ses veya video dosyası seçin.")
        with self._lock:
            if self._closed:
                raise ValueError("Uygulama kapanıyor.")
            if self._state["status"] == "running":
                raise ValueError("Devam eden işlemin tamamlanmasını bekleyin.")
            self._started = monotonic()
            self._state = {
                "status": "running", "stage": "Ses WAV biçimine hazırlanıyor…", "progress": 0,
                "text": "", "output_path": None, "errors": [], "elapsed_seconds": 0,
                "successful_chunks": 0, "total_chunks": 0, "source": str(file_path),
            }
            self._thread = Thread(target=self._run, args=(str(file_path), options), daemon=True)
            try:
                self._thread.start()
            except Exception:
                self._state.update(status="error", stage="İşlem başlatılamadı.")
                raise
        return self.snapshot()

    def try_close(self):
        """Don't abandon a job's temporary files or race a new job at shutdown."""
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._closed = True
            return True

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def _progress(self, value):
        self._update(progress=value, stage="Konuşma metne dönüştürülüyor…")

    def _run(self, file_path, options):
        try:
            with prepare_wav(file_path) as wav_path:
                self._update(stage="Tanıma motoru hazırlanıyor. İlk kullanımda model indirilebilir…")
                result = convert_audio(wav_path, self._progress, output_source_path=file_path,
                                       recognition_options=options)
            stages = {
                "success": "Dönüştürme tamamlandı.",
                "partial": "Bazı bölümler dönüştürülemedi; kısmi metin kaydedildi.",
                "failed": "Ses çözümlenemedi. Metin dosyası oluşturulmadı.",
            }
            result_data = asdict(result)
            result_data["errors"] = list(result.errors)
            self._update(**result_data, stage=stages[result.status],
                         elapsed_seconds=int(monotonic() - self._started))
        except Exception as exc:
            self._update(status="error", stage="Dönüştürme tamamlanamadı.", errors=[str(exc)],
                         elapsed_seconds=int(monotonic() - self._started))
