# This Python file uses the following encoding: utf-8
import sys
import datetime
import pathlib
import re
import subprocess
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeView,
    QWidget,
)
from PySide6.QtCore import QProcess, QTimer, QDir, Qt, QSettings
from PySide6.QtGui import QCloseEvent, QFont, QIcon, QKeySequence, QShortcut, QTextCursor, QTextDocument

from highlighter import DARK_STYLESHEET, LIGHT_STYLESHEET, LatexHighLighter

# Important:
# You need to run the following command to generate the ui_form.py file
#     pyside6-uic form.ui -o ui_form.py, or
#     pyside2-uic form.ui -o ui_form.py
from ui_form import Ui_MainWindow
from templates import TEMPLATES, DEFAULT_TEMPLATE

APP_TITLE = "SeleneTeX"
TEX_FILTER = "LaTeX Documents (*.tex)"
ICON_PATH = pathlib.Path(__file__).resolve().parent / "logo.png"

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1300,850)

        self.ui.top_splitter.setSizes([650, 650])
        self.ui.top_splitter.setStretchFactor(0, 1)
        self.ui.top_splitter.setStretchFactor(1, 1)

        self.ui.main_splitter.setSizes([680, 150])
        self.ui.main_splitter.setStretchFactor(0, 4)
        self.ui.main_splitter.setStretchFactor(1, 1)

        self.ui.actionOpen.triggered.connect(self.action_open_triggered)
        self.ui.actionSave.triggered.connect(self.action_save_triggered)
        self.ui.actionNew.triggered.connect(self.action_new_triggered)
        self.ui.actionSaveAs.triggered.connect(self.action_saveas_triggered)
        self.ui.editor.document().modificationChanged.connect(self.setWindowModified)
        self.ui.actionCompile.triggered.connect(self.action_compile_triggered)
        self.ui.actionDark_Theme.toggled.connect(self.apply_theme)
        self.ui.pdfView.page_clicked.connect(self.sync_pdf_to_code)

        self.action_sync_to_pdf = self.ui.menuBuild.addAction("Ir al PDF (SyncTeX)")
        self.action_sync_to_pdf.setShortcut("Ctrl+Shift+J")
        self.action_sync_to_pdf.triggered.connect(self.sync_code_to_pdf)

        self.auto_compiler_timer = QTimer(self)
        self.auto_compiler_timer.setSingleShot(True)
        self.auto_compiler_timer.setInterval(1500)
        self.auto_compiler_timer.timeout.connect(self.action_compile_triggered)

        self.ui.editor.textChanged.connect(self.on_text_changed)

        self.opened_file = None
        self.master_file = None
        self.compiler = QProcess(self)
        self.compiler.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.compiler.readyReadStandardOutput.connect(self.on_compile_output)
        self.compiler.finished.connect(self.on_compile_finished)
        self.ui.logView.cursorPositionChanged.connect(self.on_log_cursor_changed)

        self.highlighter = LatexHighLighter(self.ui.editor.document())
        self.ui.editor.setFont(QFont("Monospace",11))

        self.setup_project_tree()
        self.setup_find_bar()
        self.update_title()
        self.apply_theme(True)
        self.update_project_root(pathlib.Path.home())

        self.settings = QSettings("LaTeXApp", "LaTeXApp")
        self.recent_menu = self.ui.menuFile.addMenu("Recent Files")
        self.update_recent_files_menu()

    def action_open_triggered(self):
        if not self.maybe_save():
            return
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", self.dialog_dir(), TEX_FILTER)
        if file_name == "":
            return
        self.load_file(pathlib.Path(file_name))

    def load_file(self, path: pathlib.Path):
        try:
            with open(path, "rt", encoding="utf-8") as file:
                content = file.read()
            self.ui.editor.setPlainText(content)
            self.opened_file = path
            if r"\documentclass" in content:
                self.master_file = path
            self.ui.logView.appendPlainText(f"Archivo {path} abierto. \t {datetime.datetime.now()}")
            self.update_title()
            self.update_project_root(path.parent)
            self.add_recent_file(path)
            self.add_recent_file(path)

            target_tex = self.master_file if self.master_file is not None else self.opened_file
            pdf_path = target_tex.with_suffix(".pdf")
            if pdf_path.exists():
                self.ui.pdfView.load_pdf(pdf_path)
            else:
                self.ui.pdfView.clear_pages()
                self.ui.pdfView.current_pdf = None
            self.auto_compiler_timer.stop()
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
            content = self.ui.editor.toPlainText()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.opened_file = path
            if r"\documentclass" in content:
                self.master_file = path
            self.ui.editor.document().setModified(False)
            self.update_title()
            self.update_project_root(path.parent)
            self.add_recent_file(path)
            self.add_recent_file(path)
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

        target_tex = self.master_file if self.master_file is not None else self.opened_file
        self.compiling_file = target_tex

        self.compiler.setWorkingDirectory(str(target_tex.parent))
        self.ui.actionCompile.setEnabled(False)
        self.statusBar().showMessage(f"Compilando {target_tex.name}...")
        build_dir = f".tex_builds/{target_tex.stem}"

        args = [
            "-lualatex",
            "-synctex=1",
            "-emulate-aux-dir",
            f"-auxdir={build_dir}",
            "-interaction=nonstopmode",
            "-file-line-error",
            target_tex.name,
        ]
        self.ui.logView.clear()
        self.compiler.start("latexmk",args)

    def on_compile_output(self):
        data = self.compiler.readAllStandardOutput().data().decode("utf-8", errors = "replace")
        self.ui.logView.appendPlainText(data.rstrip())

    def on_compile_finished(self,exit_code,exit_status):
        self.ui.actionCompile.setEnabled(True)
        target_tex = getattr(self, "compiling_file", None) or self.master_file or self.opened_file
        pdf_path = target_tex.with_suffix(".pdf")
        if exit_code == 0:
            self.ui.logView.appendPlainText("\nCompilación Exitosa\n")
            self.statusBar().showMessage("Compilación Terminada")
            self.ui.pdfView.load_pdf(pdf_path)
        else:
            self.ui.logView.appendPlainText("\nError en la compilacion\n")
            self.statusBar().showMessage("Error en Compilacion")
            if pdf_path.exists():
                self.ui.pdfView.load_pdf(pdf_path)

        synctex_file = target_tex.with_suffix(".synctex.gz")
        if synctex_file.exists():
            target_dir = target_tex.parent / ".tex_builds" / target_tex.stem
            target_dir.mkdir(parents = True, exist_ok = True)
            synctex_file.replace(target_dir / synctex_file.name)

    def apply_theme(self, dark:bool):
        self.highlighter.set_theme("dark" if dark else "light")
        self.setStyleSheet(DARK_STYLESHEET if dark else LIGHT_STYLESHEET)
        self.ui.editor.set_dark_mode(dark)

    def on_text_changed(self):
        if self.ui.actionAuto_Compile.isChecked() and self.opened_file is not None:
            self.auto_compiler_timer.start()

    def on_log_cursor_changed(self):
        if not self.ui.logView.hasFocus():
            return
        line_text = self.ui.logView.textCursor().block().text()
        match = re.search(r"(?:\.tex:|^l\.)(\d+)", line_text)
        if match:
            line_num = int(match.group(1))
            self.ui.editor.go_to_line(line_num)
            self.statusBar().showMessage(f"Saltando a la línea {line_num}", 3000)

    def setup_project_tree(self):
        self.file_model = QFileSystemModel(self)
        self.file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs | QDir.Filter.Files)
        self.file_model.setNameFilterDisables(False)

        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.file_model)
        self.tree_view.setHeaderHidden(True)

        for col in (1,2,3):
            self.tree_view.setColumnHidden(col, True)

        self.tree_view.doubleClicked.connect(self.on_tree_double_clicked)

        self.project_dock = QDockWidget("Proyecto", self)
        self.project_dock.setWidget(self.tree_view)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.project_dock)
        self.ui.menuView.addAction(self.project_dock.toggleViewAction())

    def update_project_root(self, folder_path: pathlib.Path):
        root_index = self.file_model.setRootPath(str(folder_path))
        self.tree_view.setRootIndex(root_index)

    def on_tree_double_clicked(self, index):
        if self.file_model.isDir(index):
            return

        path = pathlib.Path(self.file_model.filePath(index))

        if path == self.opened_file:
            return

        if path.suffix.lower() == ".pdf":
            self.ui.pdfView.load_pdf(path)
            return

        if path.suffix.lower() in (".tex", ".bib", ".sty", ".cls", ".txt"):
            if not self.maybe_save():
                return
            self.load_file(path)

    def sync_pdf_to_code(self, page_num: int, x_pt: float, y_pt: float):
        target_tex = self.master_file or self.opened_file
        if target_tex is None:
            return
        pdf_path = target_tex.with_suffix(".pdf")
        build_dir = target_tex.parent / ".tex_builds" / target_tex.stem
        try:
            result = subprocess.run(
                [
                    "synctex",
                    "edit",
                    "-o",
                    f"{page_num}:{x_pt}:{y_pt}:{pdf_path}",
                    "-d",
                    str(build_dir),
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            file_match = re.search(r"^Input:(.+)$", result.stdout, re.MULTILINE)
            line_match = re.search(r"^Line:(\d+)$", result.stdout, re.MULTILINE)
            if file_match and line_match:
                input_path = pathlib.Path(file_match.group(1).strip()).resolve()
                line_num = int(line_match.group(1))
                if input_path.exists() and input_path != self.opened_file:
                    if not self.maybe_save():
                        return
                    self.load_file(input_path)
                self.ui.editor.go_to_line(line_num)
                self.statusBar().showMessage(f"SyncTeX → línea {line_num}", 3000)
        except OSError:
            pass

    def sync_code_to_pdf(self):
        if self.opened_file is None:
            return
        target_tex = self.master_file or self.opened_file
        pdf_path = target_tex.with_suffix(".pdf")
        build_dir = target_tex.parent / ".tex_builds" / target_tex.stem
        line_num = self.ui.editor.textCursor().blockNumber() + 1
        try:
            result = subprocess.run(
                [
                    "synctex",
                    "view",
                    "-i",
                    f"{line_num}:1:{self.opened_file}",
                    "-o",
                    str(pdf_path),
                    "-d",
                    str(build_dir),
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            page_match = re.search(r"^Page:(\d+)$", result.stdout, re.MULTILINE)
            y_match = re.search(r"^y:([0-9.]+)$", result.stdout, re.MULTILINE)
            if page_match and y_match:
                page_num = int(page_match.group(1))
                y_pt = float(y_match.group(1))
                self.ui.pdfView.scroll_to_position(page_num, y_pt)
                self.statusBar().showMessage(f"SyncTeX → página {page_num}", 3000)
        except OSError:
            pass

    def add_recent_file(self, path: pathlib.Path):
        path_str = str(path.resolve())
        recent = self.settings.value("recent_files", [], type=list)
        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0,path_str)
        recent = recent[:10]
        self.settings.setValue("recent_files", recent)
        self.update_recent_files_menu()

    def update_recent_files_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("recent_files", [], type=list)
        valid_files = [p for p in recent if pathlib.Path(p).exists()]

        if not valid_files:
            empty_action = self.recent_menu.addAction("(Sin Archivos Recientes)")
            empty_action.setEnabled(False)
            return

        for path_str in valid_files:
            p = pathlib.Path(path_str)
            action = self.recent_menu.addAction(f"{p.name} - {p.parent}")
            action.triggered.connect(lambda checked = False, target = p: self.open_recent_file(target))
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Limpiar Historial")
        clear_action.triggered.connect(self.clear_recent_files)

    def open_recent_file(self, path: pathlib.Path):
        if not self.maybe_save():
            return
        self.load_file(path)

    def clear_recent_files(self):
        self.settings.setValue("recent_files", [])
        self.update_recent_files_menu()

    def setup_find_bar(self):
        self.find_bar = QWidget(self)
        layout = QHBoxLayout(self.find_bar)
        layout.setContentsMargins(6, 4, 6, 4)

        self.find_input = QLineEdit(self.find_bar)
        self.find_input.setPlaceholderText("Buscar...")
        self.find_input.returnPressed.connect(self.find_next)

        btn_next = QPushButton("↓", self.find_bar)
        btn_next.setToolTip("Siguiente")
        btn_next.clicked.connect(self.find_next)

        btn_prev = QPushButton("↑", self.find_bar)
        btn_prev.setToolTip("Anterior")
        btn_prev.clicked.connect(self.find_prev)

        self.replace_input = QLineEdit(self.find_bar)
        self.replace_input.setPlaceholderText("Reemplazar con...")

        btn_replace = QPushButton("Reemplazar", self.find_bar)
        btn_replace.clicked.connect(self.replace_one)

        btn_replace_all = QPushButton("Reemplazar todo", self.find_bar)
        btn_replace_all.clicked.connect(self.replace_all)

        btn_close = QPushButton("✕", self.find_bar)
        btn_close.setFixedWidth(28)
        btn_close.clicked.connect(self.hide_find_bar)

        layout.addWidget(QLabel("Buscar:"))
        layout.addWidget(self.find_input)
        layout.addWidget(btn_prev)
        layout.addWidget(btn_next)
        layout.addWidget(QLabel("Reemplazar:"))
        layout.addWidget(self.replace_input)
        layout.addWidget(btn_replace)
        layout.addWidget(btn_replace_all)
        layout.addWidget(btn_close)

        self.ui.verticalLayout_3.insertWidget(0, self.find_bar)
        self.find_bar.hide()

        self.action_find = self.ui.menuView.addAction("Buscar / Reemplazar")
        self.action_find.setShortcut(QKeySequence.StandardKey.Find)
        self.action_find.triggered.connect(self.show_find_bar)

        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.find_bar)
        self.esc_shortcut.activated.connect(self.hide_find_bar)

    def show_find_bar(self):
        self.find_bar.show()
        selected = self.ui.editor.textCursor().selectedText()
        if selected:
            self.find_input.setText(selected)
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find_bar(self):
        self.find_bar.hide()
        self.ui.editor.setFocus()

    def find_next(self):
        query = self.find_input.text()
        if not query:
            return
        if not self.ui.editor.find(query):
            # Si llega al final del documento, vuelve a buscar desde el principio
            cursor = self.ui.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.ui.editor.setTextCursor(cursor)
            if not self.ui.editor.find(query):
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)

    def find_prev(self):
        query = self.find_input.text()
        if not query:
            return
        if not self.ui.editor.find(query, QTextDocument.FindFlag.FindBackward):
            cursor = self.ui.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.ui.editor.setTextCursor(cursor)
            if not self.ui.editor.find(query, QTextDocument.FindFlag.FindBackward):
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)

    def replace_one(self):
        query = self.find_input.text()
        if not query:
            return
        cursor = self.ui.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText().lower() == query.lower():
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        query = self.find_input.text()
        if not query:
            return
        replacement = self.replace_input.text()
        cursor = self.ui.editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.ui.editor.setTextCursor(cursor)
        count = 0
        while self.ui.editor.find(query):
            self.ui.editor.textCursor().insertText(replacement)
            count += 1
        cursor.endEditBlock()
        self.statusBar().showMessage(f"{count} reemplazos realizados", 3000)



    def closeEvent(self, event: QCloseEvent):
        if not self.maybe_save():
            event.ignore()
        else:
            event.accept()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setDesktopFileName("selenetex")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    widget = MainWindow()
    widget.show()
    sys.exit(app.exec())
