import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

import backend
import frontend
from helpers import ConversionTestCase
from worker import AudioToTextThread


class FrontendTests(ConversionTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        self.messages = self.enterContext(patch("frontend.QMessageBox"))

    def test_worker_does_not_create_a_message_box(self):
        AudioToTextThread(str(self.source)).run()
        self.assertEqual([], self.messages.mock_calls)

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
