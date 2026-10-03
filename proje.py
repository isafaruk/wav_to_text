"""Start the desktop WAV-to-text application."""

import sys

from PyQt5 import QtWidgets

from frontend import Ui_Dialog


def main():
    app = QtWidgets.QApplication(sys.argv)
    dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(dialog)
    dialog.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
