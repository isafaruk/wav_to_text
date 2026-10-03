"""Launch the preserved PyQt interface."""

from multiprocessing import freeze_support
import sys


def main():
    from PyQt5 import QtWidgets
    from eski.pyqt_frontend import Ui_Dialog

    app = QtWidgets.QApplication(sys.argv)
    dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(dialog)
    dialog.show()
    return app.exec_()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
