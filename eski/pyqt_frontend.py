"""Qt widgets and user interactions for the desktop application."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QStyleFactory

from eski.worker import AudioToTextThread
from core.engines import ENGINES, EngineConfigurationError, RecognitionOptions, validate_options


class Ui_Dialog(QtCore.QObject):
    def setupUi(self, Dialog):
        self.dialog = Dialog
        self.path = ""
        Dialog.setObjectName("Dialog")
        Dialog.resize(580, 470)
        layout = QtWidgets.QVBoxLayout(Dialog)
        layout.setSpacing(12)
        file_row = QtWidgets.QHBoxLayout()
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        file_row.addWidget(self.label, 1)
        self.pushButton = QtWidgets.QPushButton(Dialog)
        self.pushButton.setObjectName("pushButton")
        file_row.addWidget(self.pushButton)
        layout.addLayout(file_row)

        self.engineGroup = QtWidgets.QGroupBox("Tanıma motoru", Dialog)
        form = QtWidgets.QFormLayout(self.engineGroup)
        self.engineCombo = QtWidgets.QComboBox()
        for engine_id, spec in ENGINES.items():
            self.engineCombo.addItem(spec.name, engine_id)
        form.addRow("Servis / motor", self.engineCombo)
        self.engineHelp = QtWidgets.QLabel()
        self.engineHelp.setWordWrap(True)
        form.addRow(self.engineHelp)
        self.modelCombo = QtWidgets.QComboBox()
        self.deviceCombo = QtWidgets.QComboBox()
        self.deviceCombo.addItem("CPU (işlemci)", "cpu")
        self.deviceCombo.addItem("NVIDIA GPU (CUDA kurulumu gerekir)", "cuda")
        self.apiKeyEdit = QtWidgets.QLineEdit()
        self.apiKeyEdit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.regionEdit = QtWidgets.QLineEdit()
        self.regionEdit.setPlaceholderText("Örn. westeurope veya AZURE_SPEECH_REGION")
        self.modelPathEdit = QtWidgets.QLineEdit()
        self.modelPathEdit.setPlaceholderText("Açılmış Türkçe model klasörü veya VOSK_MODEL_PATH")
        model_path_row = QtWidgets.QWidget()
        path_layout = QtWidgets.QHBoxLayout(model_path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.modelPathEdit)
        self.modelBrowseButton = QtWidgets.QPushButton("Klasör seç")
        self.modelBrowseButton.clicked.connect(self.select_model_directory)
        path_layout.addWidget(self.modelBrowseButton)
        self.settingRows = {}
        for name, title, widget in (
            ("model", "Model", self.modelCombo),
            ("device", "Çalışacağı aygıt", self.deviceCombo),
            ("key", "API anahtarı", self.apiKeyEdit),
            ("region", "Azure bölgesi", self.regionEdit),
            ("path", "Vosk modeli", model_path_row),
        ):
            label = QtWidgets.QLabel(title)
            form.addRow(label, widget)
            self.settingRows[name] = (label, widget)
        layout.addWidget(self.engineGroup)
        self.engineCombo.currentIndexChanged.connect(self.on_engine_changed)
        self.on_engine_changed(0)

        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setWordWrap(True)
        self.label_2.setAlignment(QtCore.Qt.AlignCenter)
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setAlignment(QtCore.Qt.AlignCenter)
        self.label_3.setObjectName("label_3")
        self.pushButton_2 = QtWidgets.QPushButton(Dialog)
        self.pushButton_2.setMinimumHeight(44)
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.progressBar = QtWidgets.QProgressBar(Dialog)
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        layout.addWidget(self.pushButton_2)
        layout.addWidget(self.progressBar)
        layout.addWidget(self.label_2)
        layout.addWidget(self.label_3)
        layout.addStretch()
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

    @QtCore.pyqtSlot(int)
    def on_engine_changed(self, index):
        engine = self.engineCombo.currentData()
        spec = ENGINES[engine]
        self.engineHelp.setText(spec.description)
        self.modelCombo.clear()
        self.modelCombo.addItems(spec.models)
        # A key entered for one provider must not be sent to a different provider.
        self.apiKeyEdit.clear()
        self.apiKeyEdit.setPlaceholderText("Anahtar veya {0} ortam değişkeni".format(spec.key_env))
        visible = {
            "model": bool(spec.models),
            "device": engine in ("faster_whisper", "whisper"),
            "key": bool(spec.key_env),
            "region": engine == "azure",
            "path": engine == "vosk",
        }
        for name, widgets in self.settingRows.items():
            for widget in widgets:
                widget.setVisible(visible[name])

    def select_model_directory(self):
        directory = QFileDialog.getExistingDirectory(self.dialog, "Türkçe Vosk model klasörü")
        if directory:
            self.modelPathEdit.setText(directory)

    def selected_options(self):
        engine = self.engineCombo.currentData()
        return RecognitionOptions(
            engine=engine,
            model=self.modelCombo.currentText(),
            device=self.deviceCombo.currentData() if engine in ("faster_whisper", "whisper") else "cpu",
            api_key=self.apiKeyEdit.text() if ENGINES[engine].key_env else "",
            region=self.regionEdit.text() if engine == "azure" else "",
            model_path=self.modelPathEdit.text() if engine == "vosk" else "",
        )

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
            options = self.selected_options()
            try:
                validate_options(options)
            except EngineConfigurationError as exc:
                QMessageBox.critical(self.dialog, "Motor Ayarları", str(exc))
                return
            self.progressBar.setValue(0)
            self.label_2.setHidden(True)
            self.label_3.setHidden(True)
            self.pushButton.setEnabled(False)
            self.pushButton_2.setEnabled(False)
            self.engineGroup.setEnabled(False)
            self.thread = AudioToTextThread(self.path, options)
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
        self.engineGroup.setEnabled(True)
        self.pushButton.setEnabled(True)
        self.pushButton_2.setEnabled(bool(self.path))

    @QtCore.pyqtSlot(int)
    def on_thread_progress(self, value):
        self.progressBar.setValue(value)

    @QtCore.pyqtSlot(str)
    def on_thread_status(self, message):
        self.label_2.setText(message)
        self.label_2.setHidden(False)
