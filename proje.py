"""Start the WebView2 desktop application; pyqt_app.py launches the old UI."""

import sys
from multiprocessing import freeze_support


def main():
    from webview_app import main as start_webview
    return start_webview()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
