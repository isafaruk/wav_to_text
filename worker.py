"""Run the conversion service in a Qt thread and forward its notifications."""

from PyQt5 import QtCore

import backend


class AudioToTextThread(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            result = backend.convert_audio(self.file_path, self.progress.emit)
        except Exception as exc:
            self.error.emit("Dönüştürme tamamlanamadı: {0}".format(exc))
        else:
            self.done.emit(result)
