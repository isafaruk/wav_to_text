from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from tempfile import TemporaryDirectory
import speech_recognition as sr
from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QFileDialog, QStyleFactory
from PyQt5.QtWidgets import QMessageBox
from pydub import AudioSegment
from pydub.utils import make_chunks

# pip install SpeechRecognition
# pip install PyQt5

# pyinstaller --noconsole python_dosyam.py
# python -m PyQt5.uic.pyuic -x untitled.ui -o untitlied.py

REQUEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class ConversionResult:
    status: str
    text: str
    successful_chunks: int
    total_chunks: int
    output_path: str | None
    errors: tuple[str, ...] = ()


class AudioToTextThread(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)

    def __init__(self, file_path):
        QtCore.QThread.__init__(self)
        self.file_path = file_path

    def run(self):
        try:
            result = self._convert()
        except Exception as exc:
            self.error.emit("Dönüştürme tamamlanamadı: {0}".format(exc))
        else:
            self.done.emit(result)

    def _convert(self):
        r = sr.Recognizer()
        r.operation_timeout = REQUEST_TIMEOUT_SECONDS
        with open(self.file_path, "rb") as input_file:
            myaudio = AudioSegment.from_file(input_file, 'wav')
        chunk_length_ms = 50000  # pydub calculates in milliseconds
        chunks = make_chunks(myaudio, chunk_length_ms)
        if not chunks:
            return ConversionResult("failed", "", 0, 0, None,
                                    ("WAV dosyası ses verisi içermiyor.",))
        adet = int(len(myaudio) / chunk_length_ms) + 1
        yuzde = (100 / adet)
        text_parts = []
        successful_chunks = 0
        errors = []
        with TemporaryDirectory(prefix="wav_to_text_") as temp_dir:
            for i, chunk in enumerate(chunks):
                chunk_name = os.path.join(temp_dir, 'chunk{0}.wav'.format(i + 1))
                yuzdelik = int(yuzde * (i + 1))
                with open(chunk_name, "wb") as chunk_file:
                    chunk.export(chunk_file, format='wav')
                self.progress.emit(yuzdelik)
                with sr.AudioFile(chunk_name) as source:
                    audio = r.record(source)  # read the entire audio file
                    try:
                        transcript = r.recognize_google(audio, language='tr-tr').strip()
                        if not transcript:
                            raise sr.UnknownValueError()
                    except sr.UnknownValueError:
                        message = "{0}. parça: Ses algılanamadı.".format(i + 1)
                        errors.append(message)
                        text_parts.append("[{0}]".format(message))
                    except TimeoutError:
                        message = "{0}. parça: Tanıma isteği zaman aşımına uğradı.".format(i + 1)
                        errors.append(message)
                        text_parts.append("[{0}]".format(message))
                    except sr.RequestError as e:
                        message = "{0}. parça: Tanıma servisine ulaşılamadı; {1}".format(i + 1, e)
                        errors.append(message)
                        text_parts.append("[{0}]".format(message))
                    else:
                        text_parts.append(transcript)
                        successful_chunks += 1

        text = " ".join(text_parts)
        if not successful_chunks:
            return ConversionResult("failed", text, 0, len(chunks), None, tuple(errors))

        dosya_adi = os.path.splitext(self.file_path)[0] + ".txt"

        # Dosya ismi varsa farklı bir isim oluşturur
        i = 1
        while os.path.exists(dosya_adi):
            dosya_adi = os.path.splitext(self.file_path)[0] + "({0}).txt".format(i)
            i += 1

        with open(dosya_adi, "w") as dosya:
            dosya.write(text)
        status = "success" if successful_chunks == len(chunks) else "partial"
        return ConversionResult(status, text, successful_chunks, len(chunks),
                                dosya_adi, tuple(errors))


class Ui_Dialog(QtCore.QObject):
    path = ""
    def setupUi(self, Dialog):
        self.dialog = Dialog
        Dialog.setObjectName("Dialog")
        Dialog.resize(400, 300)
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(20, 20, 265, 25))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setGeometry(QtCore.QRect(20, 200, 355, 25))
        self.label_2.setAlignment(QtCore.Qt.AlignCenter)
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setGeometry(QtCore.QRect(20, 240, 355, 25))
        self.label_3.setAlignment(QtCore.Qt.AlignCenter)
        self.label_3.setObjectName("label_3")
        self.pushButton = QtWidgets.QPushButton(Dialog)
        self.pushButton.setGeometry(QtCore.QRect(300, 20, 75, 25))
        self.pushButton.setObjectName("pushButton")
        self.pushButton_2 = QtWidgets.QPushButton(Dialog)
        self.pushButton_2.setGeometry(QtCore.QRect(140, 70, 121, 61))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.progressBar = QtWidgets.QProgressBar(Dialog)
        self.progressBar.setGeometry(QtCore.QRect(20, 150, 355, 25))
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)
        QApplication.setStyle(QStyleFactory.create("Fusion"))
        Dialog.setWindowFlags(Dialog.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "Audio to Text"))
        Dialog.setWindowIcon(QtGui.QIcon('logo.png'))
        self.pushButton.setText(_translate("Dialog", "Gözat"))
        self.label.setText(_translate("Dialog", "Dosya Yolu..."))
        self.label_2.setText(_translate("Dialog", "Dönüştürme işlemi tamamlanmıştır."))
        self.label_3.setText(_translate("Dialog", "Metin Dosya Konumuna .txt Olarak Eklenmiştir."))
        self.pushButton_2.setText(_translate("Dialog", "Dönüştür"))
        self.pushButton.clicked.connect(self.pushButton_handler)
        self.pushButton_2.clicked.connect(self.pushButton_2_handler)
        self.label_2.setHidden(True)
        self.label_3.setHidden(True)
        self.pushButton_2.setEnabled(False)

    def pushButton_handler(self):
        self.progressBar.setValue(0)
        self.label.setText("Dosya Yolu...")
        self.open_dialog_box()
        self.label_2.setHidden(True)
        self.label_3.setHidden(True)
        self.pushButton_2.setEnabled(True)

    def open_dialog_box(self):
        filename = QFileDialog.getOpenFileName()
        self.path = filename[0]
        self.label.setText(self.path)

    def pushButton_2_handler(self):
        self.donustur()

    def donustur(self):
        if self.path == "" or self.path == "Dosya Yolu...":
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Hata")
            msg.setInformativeText('Dosya Seçiniz.')
            msg.setWindowTitle("Hata")
            msg.exec_()
        elif not self.path.endswith(".wav"):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Hata")
            msg.setInformativeText('Dosya Uzantısı Yanlış')
            msg.setWindowTitle("Hata")
            msg.exec_()
        else:
            self.progressBar.setValue(0)
            self.label_2.setHidden(True)
            self.label_3.setHidden(True)
            self.pushButton.setEnabled(False)
            self.pushButton_2.setEnabled(False)
            self.thread = AudioToTextThread(self.path)
            self.thread.done.connect(self.on_thread_done, QtCore.Qt.QueuedConnection)
            self.thread.error.connect(self.on_thread_error, QtCore.Qt.QueuedConnection)
            self.thread.finished.connect(self.on_thread_finished, QtCore.Qt.QueuedConnection)
            self.thread.progress.connect(self.on_thread_progress, QtCore.Qt.QueuedConnection)
            self.thread.start()

    @QtCore.pyqtSlot(object)
    def on_thread_done(self, result):
        self.label_2.setHidden(False)
        self.label_3.setHidden(result.output_path is None)
        self.label_3.setToolTip(result.output_path or "")
        details = "\n".join(result.errors)
        if result.status == "success":
            self.label_2.setText("Dönüştürme işlemi tamamlanmıştır.")
            self.label_3.setText("Metin dosyası kaydedildi.")
            QMessageBox.information(self.dialog, "İşlem Tamam",
                                    "İşlem Tamamlandı.\n{0}".format(result.output_path))
        elif result.status == "partial":
            self.label_2.setText("Dönüştürme kısmen tamamlandı ({0}/{1} parça).".format(
                result.successful_chunks, result.total_chunks))
            self.label_3.setText("Kısmi metin dosyası kaydedildi.")
            QMessageBox.warning(self.dialog, "Kısmi Dönüştürme",
                                "{0}\n{1}\n{2}".format(self.label_2.text(), result.output_path, details))
        else:
            self.label_2.setText("Dönüştürme başarısız. Metin kaydedilmedi.")
            QMessageBox.critical(self.dialog, "Dönüştürme Başarısız", details)

    @QtCore.pyqtSlot(str)
    def on_thread_error(self, message):
        self.label_2.setHidden(True)
        self.label_3.setHidden(True)
        QMessageBox.critical(self.dialog, "Dönüştürme Hatası", message)

    @QtCore.pyqtSlot()
    def on_thread_finished(self):
        self.pushButton.setEnabled(True)
        self.pushButton_2.setEnabled(bool(self.path))

    @QtCore.pyqtSlot(int)
    def on_thread_progress(self, value):
        self.progressBar.setValue(value)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(Dialog)
    Dialog.show()
    sys.exit(app.exec_())
