import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

import backend
import pyqt_frontend as frontend
from helpers import ConversionTestCase
from worker import AudioToTextThread
from engines import ENGINES


class FrontendTests(ConversionTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        self.messages = self.enterContext(patch("pyqt_frontend.QMessageBox"))

    def test_worker_does_not_create_a_message_box(self):
        AudioToTextThread(str(self.source)).run()
        self.assertEqual([], self.messages.mock_calls)

    def test_engine_fields_follow_selection_and_keys_are_cleared_on_switch(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        self.assertEqual("google", ui.selected_options().engine)
        self.assertEqual(len(ENGINES), ui.engineCombo.count())
        self.assertEqual(QtWidgets.QLineEdit.Password, ui.apiKeyEdit.echoMode())
        for engine, visible in [
            ("faster_whisper", {"model", "device"}),
            ("vosk", {"path"}),
            ("azure", {"key", "region"}),
            ("groq", {"model", "key"}),
            ("openai", {"model", "key"}),
            ("google", set()),
        ]:
            ui.apiKeyEdit.setText("previous-provider-key")
            ui.engineCombo.setCurrentIndex(ui.engineCombo.findData(engine))
            self.assertEqual("", ui.apiKeyEdit.text())
            for name, (label, field) in ui.settingRows.items():
                self.assertEqual(name not in visible, field.isHidden(), (engine, name))
                self.assertEqual(field.isHidden(), label.isHidden())
        dialog.close()

    def test_missing_key_does_not_start_worker_or_disable_settings(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        ui.engineCombo.setCurrentIndex(ui.engineCombo.findData("groq"))
        with patch.dict(os.environ, {}, clear=True), patch("pyqt_frontend.AudioToTextThread") as worker:
            ui.donustur()
        worker.assert_not_called()
        self.messages.critical.assert_called_once()
        self.assertTrue(ui.engineGroup.isEnabled())
        dialog.close()

    def test_selected_settings_are_frozen_during_conversion_and_restored(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        ui.engineCombo.setCurrentIndex(ui.engineCombo.findData("faster_whisper"))
        ui.modelCombo.setCurrentText("base")
        with patch("worker.backend.convert_audio", side_effect=RuntimeError("model unavailable")):
            ui.donustur()
            self.assertFalse(ui.engineGroup.isEnabled())
            self.assertEqual("faster_whisper", ui.thread.recognition_options.engine)
            self.assertEqual("base", ui.thread.recognition_options.model)
            self.assertTrue(ui.thread.wait(5000))
            self.app.processEvents()
        self.messages.critical.assert_called_once()
        self.assertTrue(ui.engineGroup.isEnabled())
        self.assertTrue(ui.pushButton_2.isEnabled())
        dialog.close()

    def test_non_wav_input_reaches_preparation_and_recognition(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.root / "video.MP4")
        with patch("worker.prepare_wav", return_value=nullcontext(str(self.source))) as prepare:
            ui.donustur()
            self.assertTrue(ui.thread.wait(5000))
            self.app.processEvents()
        prepare.assert_called_once_with(ui.path)
        self.messages.information.assert_called_once()
        self.messages.critical.assert_not_called()
        self.assertTrue((self.root / "video.txt").exists())
        self.assertTrue(ui.pushButton_2.isEnabled())
        dialog.close()

    def test_cancel_file_selection_disables_conversion(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        with patch("pyqt_frontend.QFileDialog.getOpenFileName", return_value=("", "")):
            ui.pushButton_handler()
        self.assertFalse(ui.pushButton_2.isEnabled())
        dialog.close()

    def test_completion_message_runs_on_gui_thread(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        message_threads = []
        self.messages.information.side_effect = lambda *args: message_threads.append(
            QtCore.QThread.currentThread()
        )
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.assertEqual([self.app.thread()], message_threads)
        self.assertFalse(ui.label_2.isHidden())
        self.assertTrue(ui.pushButton.isEnabled())
        self.assertTrue(ui.pushButton_2.isEnabled())
        dialog.close()

    def test_file_error_restores_buttons_and_allows_retry(self):
        dialog = QtWidgets.QDialog()
        ui = frontend.Ui_Dialog()
        ui.setupUi(dialog)
        ui.path = str(self.source)
        self.source.unlink()
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.messages.critical.assert_called_once()
        self.messages.information.assert_not_called()
        self.assertTrue(ui.pushButton.isEnabled())
        self.assertTrue(ui.pushButton_2.isEnabled())
        self.assertTrue(ui.label_2.isHidden())
        self.assertTrue(ui.label_3.isHidden())
        self.write_wav(self.source)
        ui.donustur()
        self.assertTrue(ui.thread.wait(5000))
        self.app.processEvents()
        self.messages.information.assert_called_once()
        dialog.close()

    def test_partial_and_failed_results_show_the_correct_message(self):
        self.write_wav(self.source, duration_ms=50100)
        for responses, message in [
            (["first", backend.sr.RequestError("offline")], "warning"),
            ([backend.sr.RequestError("offline")] * 2, "critical"),
        ]:
            with self.subTest(message=message):
                self.messages.reset_mock()
                self.recognize.side_effect = responses
                dialog = QtWidgets.QDialog()
                ui = frontend.Ui_Dialog()
                ui.setupUi(dialog)
                ui.path = str(self.source)
                ui.donustur()
                self.assertTrue(ui.thread.wait(5000))
                self.app.processEvents()
                getattr(self.messages, message).assert_called_once()
                self.messages.information.assert_not_called()
                self.assertEqual(message == "critical", ui.label_3.isHidden())
                self.assertTrue(ui.pushButton.isEnabled())
                self.assertTrue(ui.pushButton_2.isEnabled())
                dialog.close()


if __name__ == "__main__":
    unittest.main()
