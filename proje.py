from pydub import AudioSegment 
from pydub.utils import make_chunks 
import speech_recognition as sr
import os
from PyQt5.QtWidgets import QApplication, QErrorMessage, QWidget, QInputDialog, QLineEdit, QFileDialog
from PyQt5.QtGui import QIcon
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox

#pip install SpeechRecognition
#pip install PyQt5

#python -m PyQt5.uic.pyuic -x untitled.ui -o untitlied.py

os.getcwd()

class Ui_Dialog(object):
    path = ""
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(400, 300)
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(20, 20, 265, 25))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setGeometry(QtCore.QRect(20, 200, 355, 25))
        self.label_2.setAlignment(QtCore.Qt.AlignCenter)
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setGeometry(QtCore.QRect(20, 240, 355, 25))
        self.label_3.setAlignment(QtCore.Qt.AlignCenter)
        self.label_3.setObjectName("label_3")
        self.pushButton = QtWidgets.QPushButton(Dialog)
        self.pushButton.setGeometry(QtCore.QRect(300, 20, 75, 25))
        self.pushButton.setObjectName("pushButton")
        self.pushButton_2 = QtWidgets.QPushButton(Dialog)
        self.pushButton_2.setGeometry(QtCore.QRect(140, 70, 121, 61))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.progressBar = QtWidgets.QProgressBar(Dialog)
        self.progressBar.setGeometry(QtCore.QRect(20, 150, 355, 25))
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "Audio to Text"))
        self.pushButton.setText(_translate("Dialog", "Gözat"))
        self.label.setText(_translate("Dialog", "Dosya Yolu..."))
        self.label_2.setText(_translate("Dialog", "Dönüştürme işlemi tamamlanmıştır."))
        self.label_3.setText(_translate("Dialog", "Metin Seçilen Dosya Konumuna 'text.txt' Olarak Eklenmiştir."))
        self.pushButton_2.setText(_translate("Dialog", "Dönüştür"))
        self.pushButton.clicked.connect(self.pushButton_handler)
        self.pushButton_2.clicked.connect(self.pushButton_2_handler)
        self.label_2.setHidden(True)
        self.label_3.setHidden(True)
        self.pushButton_2.setEnabled(False)
        
    def pushButton_handler(self):
        print("1. Butona Basıldı.")
        self.progressBar.setValue(0)
        self.label.setText("Dosya Yolu...")
        self.open_dialog_box()
        self.label_2.setHidden(True)
        self.label_3.setHidden(True)
        self.pushButton_2.setEnabled(True)
        
    def open_dialog_box(self):
        global path
        filename = QFileDialog.getOpenFileName()
        path = filename[0]
        print(path)
        self.label.setText(path)
            
    def pushButton_2_handler(self):
        print("2. Butona Basıldı.")
        self.donustur()
    
    def donustur(self):
        global path
        if path == "" or path == "Dosya Yolu..." :
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Hata")
            msg.setInformativeText('Dosya Yolu Giriniz.')
            msg.setWindowTitle("Hata")
            msg.exec_()

        else:
            
            dosya = open("text.txt", "w")
            
            r = sr.Recognizer()
            myaudio = AudioSegment.from_file(path , 'wav')
            chunk_length_ms = 50000 # pydub calculates in millisec 
            chunks = make_chunks(myaudio, chunk_length_ms)
            adet = int(len(myaudio) / chunk_length_ms) +1
            yuzde = (100/adet)
            print(adet, "parca mevcut")
            text = ""
            for i, chunk in enumerate(chunks):
                chunk_name = 'chunk{0}.wav'.format(i+1)
                yuzdelik = int(yuzde*(i+1))
                print ('dönüştürülüyor', chunk_name,",", "%" ,yuzdelik) 
                chunk.export(chunk_name, format='wav') 
                self.progressBar.setValue(yuzdelik)
                with sr.AudioFile(chunk_name) as source:
                    audio = r.record(source)  # read the entire audio file                  
                    text = text + str(r.recognize_google(audio,language='tr-tr', show_all=True))
        
            print("Transcription: " + text)
            dosya.writelines(text)
            dosya.close()
            for i, chunk in enumerate(chunks):
                os.remove('chunk{0}.wav'.format(i+1) )
            
            
            self.label_2.setHidden(False)
            self.label_3.setHidden(False)
            
            
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(Dialog)
    Dialog.show()
    sys.exit(app.exec_())
