# This Python file uses the following encoding: utf-8
import sys
import datetime
import pathlib
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PySide6.QtCore import QProcess
from PySide6.QtGui import QCloseEvent, QFont

from highlighter import LatexHighLighter

# Important:
# You need to run the following command to generate the ui_form.py file
#     pyside6-uic form.ui -o ui_form.py, or
#     pyside2-uic form.ui -o ui_form.py
from ui_form import Ui_MainWindow
from templates import TEMPLATES, DEFAULT_TEMPLATE

APP_TITLE = "LaTeX App"
TEX_FILTER = "LaTeX Documents (*.tex)"

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.actionOpen.triggered.connect(self.action_open_triggered)
        self.ui.actionSave.triggered.connect(self.action_save_triggered)
        self.ui.actionNew.triggered.connect(self.action_new_triggered)
        self.ui.actionSaveAs.triggered.connect(self.action_saveas_triggered)
        self.ui.editor.document().modificationChanged.connect(self.setWindowModified)
        self.ui.actionCompile.triggered.connect(self.action_compile_triggered)
        self.ui.actionDark_Theme.toggled.connect(self.apply_theme)

        self.opened_file = None
        self.compiler = QProcess(self)
        self.compiler.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.compiler.readyReadStandardOutput.connect(self.on_compile_output)
        self.compiler.finished.connect(self.on_compile_finished)

        self.highlighter = LatexHighLighter(self.ui.editor.document())
        self.ui.editor.setFont(QFont("Monospace",11))

        self.update_title()
        self.apply_theme(True)

    def action_open_triggered(self):
        try:
            if not self.maybe_save():
                return
            file_name, _ = QFileDialog.getOpenFileName(self, "Open File", self.dialog_dir(), TEX_FILTER)
            if file_name == "":
                return
            # Leer primero; el estado solo se actualiza si la lectura ha ido bien
            with open(file_name, "rt", encoding="utf-8") as file:
                content = file.read()
            self.ui.editor.setPlainText(content)
            self.opened_file = pathlib.Path(file_name)
            self.ui.logView.appendPlainText(f"Archivo {file_name} abierto. \t {datetime.datetime.now()}")
            self.update_title()
            pdf_path = self.opened_file.with_suffix(".pdf")
            if pdf_path.exists():
                self.ui.pdfView.load_pdf(pdf_path)
            else:
                self.ui.pdfView.clear_pages()
                self.ui.pdfView.current_pdf = None
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.critical(self, "Error al abrir", f"No se pudo abrir el archivo:\n{e}")


    def action_save_triggered(self):
        if self.opened_file is None:
            return self.action_saveas_triggered()
        else:
            return self.save_to(self.opened_file)


    def action_new_triggered(self):
        if not self.maybe_save():
            return
        self.ui.editor.setPlainText(TEMPLATES[DEFAULT_TEMPLATE])
        self.opened_file = None
        self.update_title()
        self.ui.pdfView.clear_pages()
        self.ui.pdfView.current_pdf = None

    def action_saveas_triggered(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save File", self.dialog_dir(), TEX_FILTER)
        if file_name == "":
            return False
        path = pathlib.Path(file_name)
        if path.suffix != ".tex":
            path = path.with_suffix(".tex")
        return self.save_to(path)

    def update_title(self):
        if self.opened_file is None:
            name = "Sin título"
        else:
            name = self.opened_file.name
        self.setWindowTitle(f"{name}[*] - {APP_TITLE}")

    def maybe_save(self):
        if self.ui.editor.document().isModified():
            msgbox = QMessageBox.question(
                self,
                "Documento no guardado",
                "El documento tiene cambios sin guardar.\n¿Quiere guardarlos?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            match msgbox:
                case QMessageBox.StandardButton.Save:
                    return self.action_save_triggered()
                case QMessageBox.StandardButton.Discard:
                    return True
                case _:
                    return False
        else:
            return True

    def save_to(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.ui.editor.toPlainText())
            self.opened_file = path
            self.ui.editor.document().setModified(False)
            self.update_title()
            self.ui.logView.appendPlainText(f"Archivo guardado en {self.opened_file} \t {datetime.datetime.now()}")
            return True
        except OSError as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar el archivo:\n{e}")
            return False

    def dialog_dir(self):
        if self.opened_file is None:
            return str(pathlib.Path.home())
        else:
            return str(self.opened_file.parent)

    def action_compile_triggered(self):
        if self.compiler.state() != QProcess.ProcessState.NotRunning:
            self.ui.logView.appendPlainText("Compilación en Ejecución. Espere un momento\n")
            return
        if self.opened_file is None or self.ui.editor.document().isModified():
            if not self.action_save_triggered():
                return

        self.compiler.setWorkingDirectory(str(self.opened_file.parent))
        self.ui.actionCompile.setEnabled(False)
        self.statusBar().showMessage("Compilando...")

        args = [
            "-lualatex",
            "-synctex=1",
            "-interaction=nonstopmode",
            "-file-line-error",
            self.opened_file.name,
        ]
        self.compiler.start("latexmk",args)

    def on_compile_output(self):
        data = self.compiler.readAllStandardOutput().data().decode("utf-8", errors = "replace")
        self.ui.logView.appendPlainText(data.rstrip())

    def on_compile_finished(self,exit_code,exit_status):
        self.ui.actionCompile.setEnabled(True)
        if exit_code == 0:
            pdf_path = self.opened_file.with_suffix(".pdf")
            self.ui.logView.appendPlainText("\nCompilación Exitosa\n")
            self.statusBar().showMessage("Compilación Terminada")
            self.ui.pdfView.load_pdf(pdf_path)
        else:
            self.ui.logView.appendPlainText("\nError en la compilacion\n")
            self.statusBar().showMessage("Error en Compilacion")
            if self.opened_file.with_suffix(".pdf").exists():
                self.ui.pdfView.load_pdf(self.opened_file.with_suffix(".pdf"))

    def apply_theme(self, dark:bool):
        self.highlighter.set_theme("dark" if dark else "light")
        if dark:
            self.ui.editor.setStyleSheet("QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }")
            self.ui.logView.setStyleSheet("QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }")
            self.ui.editor.set_dark_mode(dark)
        else:
            self.ui.editor.setStyleSheet("QPlainTextEdit { background-color: #ffffff; color: #24292e; }")
            self.ui.logView.setStyleSheet("QPlainTextEdit { background-color: #ffffff; color: #24292e; }")
            self.ui.editor.set_dark_mode(dark)


    def closeEvent(self, event: QCloseEvent):
        if not self.maybe_save():
            event.ignore()
        else:
            event.accept()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MainWindow()
    widget.show()
    sys.exit(app.exec())
