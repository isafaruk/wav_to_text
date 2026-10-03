"""Qt widgets and user interactions for the desktop application."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QStyleFactory

from worker import AudioToTextThread


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
        self.pushButton_2.setEnabled(bool(self.path))

    def open_dialog_box(self):
        filename = QFileDialog.getOpenFileName(
            self.dialog, "Ses veya video dosyası seçiniz", "",
            "Ses ve video dosyaları (*.wav *.mp3 *.mp4 *.m4a *.aac *.flac "
            "*.ogg *.opus *.wma *.aiff *.aif *.mkv *.mov *.avi *.webm *.m4v);;"
            "Tüm dosyalar (*)",
        )
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
            self.thread.status.connect(self.on_thread_status, QtCore.Qt.QueuedConnection)
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

    @QtCore.pyqtSlot(str)
    def on_thread_status(self, message):
        self.label_2.setText(message)
        self.label_2.setHidden(False)
