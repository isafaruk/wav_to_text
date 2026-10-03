"""Conversion jobs and plain-data results, independent of any frontend."""

from copy import deepcopy
from dataclasses import asdict
from math import ceil
import os
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import Any

from core.backend import convert_audio
from core.engines import ENGINES, RecognitionOptions, validate_options
from core.job_control import ConversionCancelled, JobControl
from core.media_converter import prepare_wav
from core.transcript_checkpoint import TranscriptCheckpoint


ACTIVE_STATUSES = ("running", "cancelling")
STAGES = {
    "preparing": "Ses WAV biçimine hazırlanıyor…",
    "loading": "Tanıma motoru yükleniyor. İlk kullanımda model indirilebilir…",
    "transcribing": "Konuşma metne dönüştürülüyor…",
    "saving": "Metin dosyası kaydediliyor…",
}


def _initial_state() -> dict[str, Any]:
    return {
        "status": "idle", "phase": "idle", "stage": "Bir kayıt seçerek başlayın.", "progress": 0,
        "text": "", "output_path": None, "checkpoint_path": None, "errors": [], "warnings": [],
        "elapsed_seconds": 0, "successful_chunks": 0, "total_chunks": 0, "source": "",
        "processed_seconds": 0, "duration_seconds": 0, "remaining_seconds": None,
        "speed": None, "last_update_seconds": None, "progress_available": True,
        "can_cancel": False, "engine": "", "model": "", "device": "",
    }


class ConversionService:
    def __init__(self):
        self._lock = Lock()
        self._closed = False
        self._thread = None
        self._started = None
        self._transcribing_started = None
        self._last_update = None
        self._control = None
        self._checkpoint = None
        self._checkpoint_failed = False
        self._state = _initial_state()

    @staticmethod
    def configuration():
        return {"engines": [{"id": key, **asdict(spec)} for key, spec in ENGINES.items()],
                "cpu_count": os.cpu_count() or 1, "auto_cpu_threads": min(8, os.cpu_count() or 1)}

    def snapshot(self):
        with self._lock:
            state = deepcopy(self._state)
            if state["status"] in ACTIVE_STATUSES:
                now = monotonic()
                state["elapsed_seconds"] = int(now - self._started)
                if self._last_update is not None:
                    state["last_update_seconds"] = int(now - self._last_update)
                if (state["status"] == "running" and state["phase"] == "transcribing"
                        and state["progress_available"] and self._transcribing_started is not None):
                    seconds = now - self._transcribing_started
                    processed = state["processed_seconds"]
                    if seconds >= 2 and processed > 0:
                        state["speed"] = processed / seconds
                        state["remaining_seconds"] = ceil(
                            max(0, state["duration_seconds"] - processed) / state["speed"])
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
            if self._state["status"] in ACTIVE_STATUSES:
                raise ValueError("Devam eden işlemin tamamlanmasını bekleyin.")
            self._started = monotonic()
            self._transcribing_started = None
            self._last_update = None
            self._control = JobControl(self._event)
            self._checkpoint = TranscriptCheckpoint(file_path)
            self._checkpoint_failed = False
            self._state = _initial_state()
            self._state.update(
                status="running", phase="preparing", stage=STAGES["preparing"], source=str(file_path),
                can_cancel=True, progress_available=options.engine != "whisper",
                engine=options.engine, model=options.model or next(iter(ENGINES[options.engine].models), ""),
                device=options.device if options.engine in ("faster_whisper", "whisper", "vosk") else "cloud",
            )
            self._thread = Thread(target=self._run, args=(str(file_path), options), daemon=True)
            try:
                self._thread.start()
            except Exception:
                self._state.update(status="error", stage="İşlem başlatılamadı.", can_cancel=False)
                raise
        return self.snapshot()

    def cancel(self):
        with self._lock:
            if self._state["status"] == "running" and self._state["can_cancel"]:
                self._control.cancelled.set()
                stage = ("İptal ediliyor… Devam eden bulut isteğinin yanıtı bekleniyor."
                         if self._state["device"] == "cloud" and self._state["phase"] == "transcribing"
                         else "İptal ediliyor…")
                self._state.update(status="cancelling", can_cancel=False, stage=stage)
        return self.snapshot()

    def try_close(self):
        """Keep the UI alive until cancellation has reaped workers and temporary files."""
        with self._lock:
            if self._state["status"] in ACTIVE_STATUSES:
                return False
            self._closed = True
            return True

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def _progress(self, value):
        self._update(progress=max(0, min(99, int(value))))

    def _event(self, event):
        # Disk writes happen outside the state lock so the UI stays responsive.
        with self._lock:
            phase = event.get("phase")
            if phase and self._state["status"] != "cancelling":
                if phase == "transcribing" and self._transcribing_started is None:
                    self._transcribing_started = monotonic()
                self._state.update(phase=phase, stage=STAGES[phase], can_cancel=phase != "saving")
            elif phase == "saving":
                raise ConversionCancelled()
            if "duration_seconds" in event:
                self._state["duration_seconds"] = event["duration_seconds"]
            if "processed_seconds" in event:
                self._state["processed_seconds"] = max(self._state["processed_seconds"],
                    min(self._state["duration_seconds"], event["processed_seconds"]))
                self._last_update = monotonic()
            addition = event.get("append_text", "")
            self._state["text"] += addition
        if addition and not self._checkpoint_failed:
            try:
                self._checkpoint.append(addition)
                self._update(checkpoint_path=str(self._checkpoint.path))
            except OSError:
                self._checkpoint_failed = True
                self._update(warnings=["Ara kayıt yazılamadı. Canlı metni kopyalayabilirsiniz."],
                             checkpoint_path=str(self._checkpoint.path) if self._checkpoint.created else None)

    def _run(self, file_path, options):
        try:
            with prepare_wav(file_path, control=self._control) as wav_path:
                result = convert_audio(wav_path, self._progress, output_source_path=file_path,
                                       recognition_options=options, control=self._control)
            if not result.output_path:
                self._control.check()
            stages = {
                "success": "Dönüştürme tamamlandı.",
                "partial": "Bazı bölümler dönüştürülemedi; kısmi metin kaydedildi.",
                "failed": "Ses çözümlenemedi. Metin dosyası oluşturulmadı.",
            }
            if result.output_path and Path(result.output_path).is_file():
                try:
                    self._checkpoint.discard()
                    self._update(checkpoint_path=None)
                except OSError:
                    self._update(warnings=["Sonuç kaydedildi; ara kayıt dosyası da korunuyor."])
            result_data = asdict(result)
            result_data["errors"] = list(result.errors)
            self._update(**result_data, stage=stages[result.status], phase="done", progress=100,
                         can_cancel=False, elapsed_seconds=int(monotonic() - self._started))
        except ConversionCancelled:
            self._update(status="cancelled", phase="done", can_cancel=False,
                         stage="İşlem iptal edildi. Varsa ara kayıt dosyası korundu.",
                         elapsed_seconds=int(monotonic() - self._started))
        except Exception as exc:
            self._update(status="error", phase="done", can_cancel=False,
                         stage="Dönüştürme tamamlanamadı. Varsa ara kayıt dosyası korundu.", errors=[str(exc)],
                         elapsed_seconds=int(monotonic() - self._started))
