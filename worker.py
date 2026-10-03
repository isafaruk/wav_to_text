"""Run the conversion service in a Qt thread and forward its notifications."""

from PyQt5 import QtCore

import backend
from media_converter import prepare_wav


class AudioToTextThread(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)
    status = QtCore.pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.status.emit("Ses WAV biçimine hazırlanıyor...")
            with prepare_wav(self.file_path) as wav_path:
                self.status.emit("Konuşma metne dönüştürülüyor...")
                result = backend.convert_audio(
                    wav_path, self.progress.emit, output_source_path=self.file_path
                )
        except Exception as exc:
            self.error.emit("Dönüştürme tamamlanamadı: {0}".format(exc))
        else:
            self.done.emit(result)
