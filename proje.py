"""Start the desktop WAV-to-text application."""

import sys
from multiprocessing import freeze_support


def main():
    from PyQt5 import QtWidgets
    from frontend import Ui_Dialog

    app = QtWidgets.QApplication(sys.argv)
    dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(dialog)
    dialog.show()
    return app.exec_()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
