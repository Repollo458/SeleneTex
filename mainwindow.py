# This Python file uses the following encoding: utf-8
import sys
import datetime
import pathlib
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PySide6.QtGui import QCloseEvent

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
        self.opened_file = None

        self.update_title()

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
