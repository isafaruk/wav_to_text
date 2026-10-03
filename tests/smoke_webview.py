"""Opt-in Windows integration test: real WebView2, JS bridge and local model.

Run from the project root: python tests/smoke_webview.py
No cloud calls. Requires an already cached Faster Whisper tiny model.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import os
    import tempfile
    import time
    import traceback
    import wave
    from threading import Event
    from unittest.mock import patch

    import webview
    from desktop.webview_app import DesktopApi

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["PYWEBVIEW_LOG"] = "debug"
    os.environ.pop("GROQ_API_KEY", None)
    folder = tempfile.TemporaryDirectory(prefix="webview_smoke_")
    source = Path(folder.name) / "test.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 16000)
    api = DesktopApi()
    root = Path(__file__).resolve().parents[1]
    window = webview.create_window("WebView integration test", str(root / "desktop/web_ui/index.html"),
                                   js_api=api, width=1120, height=790, focus=False)
    api._window = window
    failures = []

    def wait_for(expression, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if window.evaluate_js(expression):
                return
            time.sleep(0.1)
        raise AssertionError("Timed out: " + expression)

    def screenshot(name):
        from webview.platforms.winforms import BrowserView
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
        from System import Action
        from System.IO import FileMode, FileStream

        form = BrowserView.instances[window.uid]
        path = root / ".venv" / name
        stream = FileStream(str(path), FileMode.Create)
        tasks = []
        try:
            form.Invoke(Action(lambda: tasks.append(form.webview.CoreWebView2.CapturePreviewAsync(
                CoreWebView2CapturePreviewImageFormat.Png, stream))))
            deadline = time.monotonic() + 10
            while not tasks[0].IsCompleted and time.monotonic() < deadline:
                time.sleep(0.05)
            assert tasks[0].IsCompleted, "Screenshot timed out"
            tasks[0].GetAwaiter().GetResult()
        finally:
            stream.Close()
        print("Screenshot:", path, flush=True)

    def exercise():
        try:
            wait_for("document.querySelector('#engine').options.length === 7 && !document.querySelector('#choose-file').disabled")
            assert window.evaluate_js("document.querySelector('#engine').value") == "google"
            from webview.platforms import winforms
            assert winforms.renderer == "edgechromium"
            assert "PyQt5.QtCore" not in sys.modules
            assert window.evaluate_js("document.querySelector('#progress').getBoundingClientRect().bottom <= window.innerHeight")
            screenshot("webview-idle.png")
            with patch.object(window, "create_file_dialog", return_value=(str(source),)):
                window.evaluate_js("document.querySelector('#choose-file').click()")
                wait_for("!document.querySelector('#start').disabled")
            with patch("speech_recognition.Recognizer.recognize_google", return_value="Merhaba dünya.\n\n<script>window.injected = true</script>"):
                window.evaluate_js("document.querySelector('#start').click()")
                wait_for("document.querySelector('#status-badge').textContent === 'TAMAMLANDI'")
            assert window.evaluate_js("document.querySelector('#transcript').value").startswith("Merhaba dünya.")
            assert not window.evaluate_js("window.injected === true")
            assert window.evaluate_js("document.querySelector('#progress').value") == 100
            assert source.with_suffix(".txt").exists()
            screenshot("webview-result.png")
            window.evaluate_js("document.querySelector('#engine').value='groq';document.querySelector('#engine').dispatchEvent(new Event('change'))")
            window.evaluate_js("document.querySelector('#start').click()")
            wait_for("document.querySelector('#notice').textContent.includes('API anahtarını')")
            assert not window.evaluate_js("document.querySelector('#start').disabled")
            window.evaluate_js("document.querySelector('#engine').value='faster_whisper';document.querySelector('#engine').dispatchEvent(new Event('change'))")
            assert not window.evaluate_js("document.querySelector('#device-row').hidden")
            assert window.evaluate_js("Array.from(document.querySelector('#model').options).some(option => option.value === 'turbo')")
            assert window.evaluate_js("document.querySelector('#cpu-threads').options.length") > 1
            assert not window.evaluate_js("document.querySelector('#performance-settings').hidden")
            window.evaluate_js("document.querySelector('#model').value='turbo'; document.querySelector('#cpu-threads').value='2'")
            release = Event()

            def live_conversion(path, progress, *, control, recognition_options, **kwargs):
                assert recognition_options.model == "turbo"
                assert recognition_options.cpu_threads == "2"
                control.emit(phase="transcribing", duration_seconds=120)
                control.emit(append_text="İlk bölüm. <script>window.injected = true</script>", processed_seconds=30)
                progress(25)
                release.wait(15)
                control.check()
                raise AssertionError("UI should request cancellation")

            with patch("services.conversion_service.convert_audio", side_effect=live_conversion):
                try:
                    window.evaluate_js("document.querySelector('#start').click()")
                    wait_for("!document.querySelector('#cancel').disabled && document.querySelector('#transcript').value.includes('İlk bölüm.')")
                    assert not window.evaluate_js("window.injected === true")
                    wait_for("document.querySelector('#output-path').textContent.includes('partial.txt')")
                    wait_for("document.querySelector('#remaining').textContent.includes('≈')")
                    assert not window.evaluate_js("document.querySelector('#copy').disabled")
                    assert not window.evaluate_js("document.querySelector('#open-folder').disabled")
                    assert window.evaluate_js("document.querySelector('#settings').disabled")
                    assert api.get_state()["processed_seconds"] == 30
                    checkpoint = Path(api.get_state()["checkpoint_path"])
                    assert "İlk bölüm." in checkpoint.read_text(encoding="utf-8")
                    window.evaluate_js("document.querySelector('.status-panel').scrollIntoView({block:'end'})")
                    screenshot("webview-live.png")
                    window.evaluate_js("document.querySelector('#cancel').click()")
                    wait_for("document.querySelector('#status-badge').textContent === 'DURDURULUYOR'")
                    assert window.evaluate_js("document.querySelector('#start').disabled")
                finally:
                    release.set()
                wait_for("document.querySelector('#status-badge').textContent === 'İPTAL EDİLDİ'")
                assert checkpoint.exists()
                assert not window.evaluate_js("document.querySelector('#start').disabled")
                assert window.evaluate_js("document.querySelector('#cancel').hidden")
                screenshot("webview-cancelled.png")

            window.evaluate_js("document.querySelector('#device').value='cuda';document.querySelector('#device').dispatchEvent(new Event('change'))")
            assert not window.evaluate_js("document.querySelector('#gpu-compute-row').hidden")
            assert window.evaluate_js("document.querySelector('#threads-row').hidden")
            assert window.evaluate_js("document.querySelector('#gpu-compute').value") == "int8_float16"
            window.evaluate_js("document.querySelector('#device').value='cpu';document.querySelector('#device').dispatchEvent(new Event('change'));document.querySelector('#model').value='tiny'")
            window.evaluate_js("document.querySelector('#start').click()")
            wait_for("document.querySelector('#status-badge').textContent === 'SONUÇ YOK'", 60)
            assert window.evaluate_js("document.querySelector('#progress').value") == 100
            assert not window.evaluate_js("document.querySelector('#start').disabled")
            window.resize(780, 620)
            wait_for("window.innerWidth < 800")
            window.evaluate_js("document.querySelector('#performance-settings').open=true; document.querySelector('#cpu-threads').scrollIntoView({block:'center'})")
            assert window.evaluate_js("document.querySelector('#progress').getBoundingClientRect().bottom <= window.innerHeight")
            assert window.evaluate_js("document.querySelector('#start').getBoundingClientRect().bottom <= window.innerHeight")
            screenshot("webview-compact.png")
            print("PASS: WebView2, live text/ETA/checkpoint, cancellation/retry, speed controls, output, cached tiny model", flush=True)
        except Exception:
            failures.append(traceback.format_exc())
            print(failures[-1], flush=True)
            print("Service state:", ascii(api.get_state()), flush=True)
        finally:
            window.destroy()

    try:
        webview.start(exercise, gui="edgechromium", debug=False)
    finally:
        folder.cleanup()
    return bool(failures)


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
