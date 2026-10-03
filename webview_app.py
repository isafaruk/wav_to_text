"""Desktop-only adapter between the web UI and the Python conversion service."""

import os
import sys
from pathlib import Path
from threading import Lock, Thread

from conversion_service import ConversionService


class DesktopApi:
    def __init__(self, service=None):
        self._service = service or ConversionService()
        self._window = None
        self._selected_path = ""
        self._startup_error = ""
        self._selection_lock = Lock()

    def get_config(self):
        return self._service.configuration()

    def get_state(self):
        return self._service.snapshot()

    def choose_file(self):
        import webview

        with self._selection_lock:
            if self._service.snapshot()["status"] == "running":
                return {"ok": False, "error": "İşlem devam ederken dosya değiştirilemez."}
            paths = self._window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("Ses ve video (*.wav;*.mp3;*.mp4;*.m4a;*.aac;*.flac;*.ogg;*.opus;*.wma;*.mkv;*.mov;*.avi;*.webm)",
                            "Tüm dosyalar (*.*)"),
            )
            if not paths:
                return {"ok": True, "file": None}
            path = Path(paths[0])
            try:
                size = path.stat().st_size
            except OSError:
                return {"ok": False, "error": "Seçilen dosya okunamıyor."}
            self._selected_path = str(path)
            return {"ok": True, "file": {"path": str(path), "name": path.name, "size": size}}

    def choose_model_folder(self):
        import webview

        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return paths[0] if paths else None

    def start_conversion(self, settings):
        with self._selection_lock:
            try:
                return {"ok": True, "state": self._service.start(self._selected_path, settings)}
            except (ValueError, OSError) as exc:
                return {"ok": False, "error": str(exc)}

    def open_output_folder(self):
        output = self._service.snapshot().get("output_path")
        if not output or not Path(output).is_file():
            return {"ok": False, "error": "Kaydedilmiş bir metin dosyası bulunamadı."}
        try:
            os.startfile(str(Path(output).parent))
        except OSError:
            return {"ok": False, "error": "Çıktı klasörü açılamadı."}
        return {"ok": True}

    def _on_closing(self):
        if self._service.try_close():
            return True
        # Closing is synchronous; schedule UI feedback after returning to the event loop.
        Thread(target=self._window.run_js, args=(
            "window.showNotice('Kapatmadan önce devam eden işlemin tamamlanmasını bekleyin.');",
        ), daemon=True).start()
        return False

    def _on_initialized(self, renderer):
        if renderer != "edgechromium":
            self._startup_error = (
                "Microsoft Edge WebView2 Runtime bulunamadı. WebView2 Runtime kurulumunu tamamlayın: "
                "https://developer.microsoft.com/microsoft-edge/webview2/"
            )
            return False
        return True


def main():
    import webview

    api = DesktopApi()
    entry = Path(__file__).resolve().parent / "web_ui" / "index.html"
    window = webview.create_window(
        "Ses / Metin", str(entry), js_api=api, width=1120, height=790,
        min_size=(780, 620), background_color="#f5f5f2", text_select=True,
    )
    api._window = window
    window.events.closing += api._on_closing
    window.events.initialized += api._on_initialized
    # Explicitly require WebView2; never fall back to Qt or Internet Explorer.
    webview.start(gui="edgechromium", debug=False)
    if api._startup_error:
        print(api._startup_error, file=sys.stderr)
        return 1
    return 0
