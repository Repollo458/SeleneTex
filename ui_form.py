# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'form.ui'
##
## Created by: Qt User Interface Compiler version 6.12.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QMainWindow, QMenu, QMenuBar,
    QPlainTextEdit, QSizePolicy, QSplitter, QStatusBar,
    QVBoxLayout, QWidget)

from code_editor import CodeEditor
from pdf_viewer import PdfViewer

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 600)
        self.actionSave = QAction(MainWindow)
        self.actionSave.setObjectName(u"actionSave")
        self.actionSave.setMenuRole(QAction.MenuRole.NoRole)
        self.actionNew = QAction(MainWindow)
        self.actionNew.setObjectName(u"actionNew")
        self.actionNew.setMenuRole(QAction.MenuRole.NoRole)
        self.actionOpen = QAction(MainWindow)
        self.actionOpen.setObjectName(u"actionOpen")
        self.actionOpen.setMenuRole(QAction.MenuRole.NoRole)
        self.actionCompile = QAction(MainWindow)
        self.actionCompile.setObjectName(u"actionCompile")
        self.actionCompile.setMenuRole(QAction.MenuRole.NoRole)
        self.actionSaveAs = QAction(MainWindow)
        self.actionSaveAs.setObjectName(u"actionSaveAs")
        self.actionSaveAs.setMenuRole(QAction.MenuRole.NoRole)
        self.actionDark_Theme = QAction(MainWindow)
        self.actionDark_Theme.setObjectName(u"actionDark_Theme")
        self.actionDark_Theme.setCheckable(True)
        self.actionDark_Theme.setChecked(True)
        self.actionDark_Theme.setMenuRole(QAction.MenuRole.NoRole)
        self.actionAuto_Compile = QAction(MainWindow)
        self.actionAuto_Compile.setObjectName(u"actionAuto_Compile")
        self.actionAuto_Compile.setCheckable(True)
        self.actionAuto_Compile.setChecked(True)
        self.actionAuto_Compile.setMenuRole(QAction.MenuRole.NoRole)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_3 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.main_splitter = QSplitter(self.centralwidget)
        self.main_splitter.setObjectName(u"main_splitter")
        self.main_splitter.setOrientation(Qt.Orientation.Vertical)
        self.top_splitter = QSplitter(self.main_splitter)
        self.top_splitter.setObjectName(u"top_splitter")
        self.top_splitter.setOrientation(Qt.Orientation.Horizontal)
        self.editor = CodeEditor(self.top_splitter)
        self.editor.setObjectName(u"editor")
        self.top_splitter.addWidget(self.editor)
        self.pdfView = PdfViewer(self.top_splitter)
        self.pdfView.setObjectName(u"pdfView")
        self.top_splitter.addWidget(self.pdfView)
        self.main_splitter.addWidget(self.top_splitter)
        self.logView = QPlainTextEdit(self.main_splitter)
        self.logView.setObjectName(u"logView")
        self.logView.setReadOnly(True)
        self.main_splitter.addWidget(self.logView)

        self.verticalLayout_3.addWidget(self.main_splitter)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 23))
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName(u"menuFile")
        self.menuBuild = QMenu(self.menubar)
        self.menuBuild.setObjectName(u"menuBuild")
        self.menuView = QMenu(self.menubar)
        self.menuView.setObjectName(u"menuView")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuBuild.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menuFile.addAction(self.actionNew)
        self.menuFile.addAction(self.actionOpen)
        self.menuFile.addAction(self.actionSave)
        self.menuFile.addAction(self.actionSaveAs)
        self.menuBuild.addAction(self.actionCompile)
        self.menuBuild.addAction(self.actionAuto_Compile)
        self.menuView.addAction(self.actionDark_Theme)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"SeleneTeX", None))
        self.actionSave.setText(QCoreApplication.translate("MainWindow", u"Save", None))
#if QT_CONFIG(shortcut)
        self.actionSave.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+S", None))
#endif // QT_CONFIG(shortcut)
        self.actionNew.setText(QCoreApplication.translate("MainWindow", u"New", None))
#if QT_CONFIG(shortcut)
        self.actionNew.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+N", None))
#endif // QT_CONFIG(shortcut)
        self.actionOpen.setText(QCoreApplication.translate("MainWindow", u"Open", None))
#if QT_CONFIG(shortcut)
        self.actionOpen.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.actionCompile.setText(QCoreApplication.translate("MainWindow", u"Compile", None))
#if QT_CONFIG(shortcut)
        self.actionCompile.setShortcut(QCoreApplication.translate("MainWindow", u"F5", None))
#endif // QT_CONFIG(shortcut)
        self.actionSaveAs.setText(QCoreApplication.translate("MainWindow", u"Save As", None))
#if QT_CONFIG(shortcut)
        self.actionSaveAs.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+Shift+S", None))
#endif // QT_CONFIG(shortcut)
        self.actionDark_Theme.setText(QCoreApplication.translate("MainWindow", u"Dark Theme", None))
        self.actionAuto_Compile.setText(QCoreApplication.translate("MainWindow", u"Auto-Compile", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", u"File", None))
        self.menuBuild.setTitle(QCoreApplication.translate("MainWindow", u"Build", None))
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", u"View", None))
    # retranslateUi

