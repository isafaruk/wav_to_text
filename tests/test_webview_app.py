from unittest.mock import MagicMock, patch

from helpers import ConversionTestCase
from webview_app import DesktopApi


class DesktopApiTests(ConversionTestCase):
    def setUp(self):
        super().setUp()
        self.api = DesktopApi()
        self.api._window = MagicMock()

    def test_file_dialog_selection_reaches_conversion_and_cancel_preserves_selection(self):
        self.api._window.create_file_dialog.side_effect = [(str(self.source),), None]
        selected = self.api.choose_file()
        self.assertEqual(self.source.name, selected["file"]["name"])
        self.assertIsNone(self.api.choose_file()["file"])
        self.assertTrue(self.api.start_conversion({})["ok"])
        self.api._service._thread.join(5)
        self.assertEqual("success", self.api.get_state()["status"])

    def test_missing_selection_returns_readable_error(self):
        result = self.api.start_conversion({})
        self.assertFalse(result["ok"])
        self.assertIn("dosyası seçin", result["error"])

    def test_only_current_output_folder_can_be_opened(self):
        with patch("webview_app.os.startfile", create=True) as open_folder:
            self.assertFalse(self.api.open_output_folder()["ok"])
            open_folder.assert_not_called()
            self.api._selected_path = str(self.source)
            self.api.start_conversion({})
            self.api._service._thread.join(5)
            self.assertTrue(self.api.open_output_folder()["ok"])
            open_folder.assert_called_once_with(str(self.source.parent))

    def test_config_has_seven_engines_with_google_first(self):
        config = self.api.get_config()
        self.assertEqual(7, len(config["engines"]))
        self.assertEqual("google", config["engines"][0]["id"])

    def test_unsupported_browser_renderer_is_rejected(self):
        self.assertFalse(self.api._on_initialized("mshtml"))
        self.assertIn("WebView2 Runtime", self.api._startup_error)
        self.assertTrue(self.api._on_initialized("edgechromium"))

    def test_default_launcher_has_no_qt_import(self):
        # Child processes re-import the entrypoint before loading their target.
        import subprocess
        import sys

        result = subprocess.run([sys.executable, "-B", "-W", "error::RuntimeWarning", "-c",
                                 "import proje, webview_app, sys; assert 'PyQt5' not in sys.modules"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
