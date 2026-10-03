"""Run the conversion service in a Qt thread and forward its notifications."""

from PyQt5 import QtCore

import backend
from media_converter import prepare_wav
from engines import RecognitionOptions, validate_options


class AudioToTextThread(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)
    status = QtCore.pyqtSignal(str)

    def __init__(self, file_path, recognition_options=None):
        super().__init__()
        self.file_path = file_path
        self.recognition_options = recognition_options or RecognitionOptions()

    def run(self):
        try:
            validate_options(self.recognition_options)
            self.status.emit("Ses WAV biçimine hazırlanıyor...")
            with prepare_wav(self.file_path) as wav_path:
                self.status.emit("Tanıma motoru hazırlanıyor ve ses işleniyor...")
                result = backend.convert_audio(
                    wav_path, self.progress.emit, output_source_path=self.file_path,
                    recognition_options=self.recognition_options,
                )
        except Exception as exc:
            self.error.emit("Dönüştürme tamamlanamadı: {0}".format(exc))
        else:
            self.done.emit(result)
