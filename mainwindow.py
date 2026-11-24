# This Python file uses the following encoding: utf-8
import os
import sys
import datetime
import pathlib
import re
import shutil
import subprocess
import zipfile
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDockWidget,
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QTabWidget,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtCore import QEvent, QProcess, QSize, QTimer, QDir, Qt, QSettings
from PySide6.QtGui import (
    QActionGroup,
    QCloseEvent,
    QFont,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
    QTextCursor,
    QTextDocument,
)

from highlighter import (
    DARK_STYLESHEET,
    LIGHT_STYLESHEET,
    SEMANTIC_TOKENS,
    LatexHighLighter,
    LogHighlighter,
)
from icons import SeleneFileIconProvider, svg_icon, svg_pixmap
from ai_client import (
    AIDiffDialog,
    AISettingsDialog,
    AIWorker,
    extract_recommended_packages,
    resolve_ai_config,
)
from code_editor import (
    CodeEditor,
    collect_project_citations,
    collect_project_labels,
    extract_document_packages,
)
from latex_tools import (
    BibliographyDockWidget,
    SymbolPaletteWidget,
    TableGeneratorDialog,
    parse_bib_entries_detailed,
)
from mascot_widget import DEFAULT_OCR_PROMPT, QuickAIBubble, SeleneMascot
from math_preview import (
    MathPreviewPopup,
    MathRenderWorker,
    build_standalone_tex,
    extract_math_at_cursor,
    extract_safe_math_preamble,
    get_cached_preview,
)
from help_dialogs import APP_VERSION, AboutDialog, EnvironmentCheckDialog
from preferences import (
    CommandPaletteDialog,
    PaletteCommand,
    PreferencesDialog,
    list_available_mono_fonts,
)

# Important:
# You need to run the following command to generate the ui_form.py file
#     pyside6-uic form.ui -o ui_form.py, or
#     pyside2-uic form.ui -o ui_form.py
from ui_form import Ui_MainWindow
from templates import TEMPLATES, DEFAULT_TEMPLATE

APP_TITLE = "SeleneTeX"
TEX_FILTER = "LaTeX Documents (*.tex)"


def _resource_path(filename: str) -> pathlib.Path:
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
    return base / filename


ICON_PATH = _resource_path("logo.png")

LATEX_ENGINES: dict[str, str] = {
    "LuaLaTeX": "-lualatex",
    "pdfLaTeX": "-pdf",
    "XeLaTeX": "-xelatex",
}

AUX_CLEAN_EXTENSIONS = {
    ".aux", ".log", ".fls", ".fdb_latexmk", ".out", ".toc", ".lof", ".lot",
    ".bbl", ".blg", ".bcf", ".nav", ".snm", ".vrb", ".xdv", ".idx", ".ilg", ".ind",
}

ZIP_EXCLUDE_DIRS = {".tex_builds", ".git", "__pycache__", ".venv", ".qtcreator", "node_modules"}


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.setMinimumSize(680, 500)
        self.resize(1320, 860)

        self.settings = QSettings("LaTeXApp", "LaTeXApp")
        self._layout_tier = None
        self._docks_auto_collapsed = False
        self._docks_state_before_collapse = (True, True)
        self._view_mode = "split"  # "editor", "split", "pdf"
        self._log_visible = True
        self._last_log_height = 160
        self._current_theme = "dark"
        self._project_root: pathlib.Path | None = None
        self.master_file: pathlib.Path | None = None
        saved_engine = self.settings.value("build/engine", "LuaLaTeX", type=str)
        self._compile_engine = saved_engine if saved_engine in LATEX_ENGINES else "LuaLaTeX"
        self._shell_escape = self.settings.value("build/shell_escape", False, type=bool)
        self._compile_aborted = False
        self._autocompile_ms = max(500, min(5000, self.settings.value("build/autocompile_ms", 1500, type=int)))
        self._tab_width = self.settings.value("editor/tab_width", 4, type=int)
        if self._tab_width not in (2, 4, 8):
            self._tab_width = 4
        self._word_wrap = self.settings.value("editor/word_wrap", True, type=bool)
        self._auto_close = self.settings.value("editor/auto_close", True, type=bool)
        self._restore_session = self.settings.value("session/restore_enabled", True, type=bool)
        self._autosave_on_blur = self.settings.value("session/autosave_on_blur", False, type=bool)

        mono_fonts = list_available_mono_fonts()
        default_mono = mono_fonts[0]
        saved_font_family = self.settings.value("editor/font_family", default_mono, type=str)
        if saved_font_family not in mono_fonts:
            saved_font_family = default_mono
        saved_font_size = max(8, min(28, self.settings.value("editor/font_size", 11, type=int)))
        self._editor_font = QFont(saved_font_family, saved_font_size)
        self._editor_font.setStyleHint(QFont.StyleHint.Monospace)

        self.setup_editor_tabs()

        self.ui.top_splitter.setChildrenCollapsible(False)
        self.ui.top_splitter.setSizes([650, 650])
        self.ui.top_splitter.setStretchFactor(0, 1)
        self.ui.top_splitter.setStretchFactor(1, 1)
        self.editor_tabs.setMinimumWidth(240)
        self.ui.pdfView.setMinimumWidth(240)

        self.ui.actionOpen.triggered.connect(self.action_open_triggered)
        self.ui.actionSave.triggered.connect(self.action_save_triggered)
        self.ui.actionNew.triggered.connect(self.action_new_triggered)
        self.ui.actionSaveAs.triggered.connect(self.action_saveas_triggered)
        self.ui.actionCompile.triggered.connect(self.action_compile_triggered)
        self.ui.actionDark_Theme.toggled.connect(self.apply_theme)
        self.ui.pdfView.page_clicked.connect(self.sync_pdf_to_code)
        self.ui.pdfView.compile_requested.connect(self.action_compile_triggered)
        self.ui.pdfView.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 3000))

        self.action_save_all = self.ui.menuFile.addAction("Guardar todo")
        self.action_save_all.setShortcut("Ctrl+Alt+S")
        self.action_save_all.triggered.connect(self.save_all_tabs)

        self.action_close_tab = self.ui.menuFile.addAction("Cerrar pestaña")
        self.action_close_tab.setShortcut("Ctrl+W")
        self.action_close_tab.triggered.connect(lambda: self.close_tab(self.editor_tabs.currentIndex()))

        self.ui.menuFile.addSeparator()
        act_open_folder = self.ui.menuFile.addAction("Abrir carpeta de proyecto...")
        act_open_folder.triggered.connect(self.open_project_folder)

        act_export_pdf = self.ui.menuFile.addAction("Exportar PDF como...")
        act_export_pdf.triggered.connect(self.export_pdf_as)

        act_export_zip = self.ui.menuFile.addAction("Exportar proyecto (.zip)...")
        act_export_zip.triggered.connect(self.export_project_zip)

        self.ui.menuFile.addSeparator()
        act_prefs = self.ui.menuFile.addAction("Preferencias...")
        act_prefs.setShortcut("Ctrl+,")
        act_prefs.triggered.connect(self.open_preferences)

        self.action_dark_pdf = self.ui.menuView.addAction("PDF en Modo Noche")
        self.action_dark_pdf.setCheckable(True)
        self.action_dark_pdf.setChecked(False)
        self.action_dark_pdf.setShortcut("Ctrl+Shift+D")
        self.action_dark_pdf.toggled.connect(self._on_dark_pdf_toggled)

        self.action_sync_to_pdf = self.ui.menuBuild.addAction("Ir al PDF (SyncTeX)")
        self.action_sync_to_pdf.setShortcut("Ctrl+Shift+J")
        self.action_sync_to_pdf.triggered.connect(self.sync_code_to_pdf)
        self.setup_build_menu_extras()

        self.auto_compiler_timer = QTimer(self)
        self.auto_compiler_timer.setSingleShot(True)
        self.auto_compiler_timer.setInterval(self._autocompile_ms)
        self.auto_compiler_timer.timeout.connect(self.action_compile_triggered)

        self.compiler = QProcess(self)
        self.compiler.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.compiler.readyReadStandardOutput.connect(self.on_compile_output)
        self.compiler.finished.connect(self.on_compile_finished)
        self.ui.logView.cursorPositionChanged.connect(self.on_log_cursor_changed)

        self.log_highlighter = LogHighlighter(self.ui.logView.document())
        self.ui.verticalLayout_3.setContentsMargins(8, 8, 8, 8)
        self.ui.verticalLayout_3.setSpacing(8)

        # Unificar etiquetas de menús al español
        self.ui.menuFile.setTitle("Archivo")
        self.ui.menuBuild.setTitle("Compilar")
        self.ui.menuView.setTitle("Ver")
        self.ui.actionNew.setText("Nueva pestaña")
        self.ui.actionOpen.setText("Abrir...")
        self.ui.actionSave.setText("Guardar")
        self.ui.actionSaveAs.setText("Guardar como...")
        self.ui.actionCompile.setText("Compilar")
        self.ui.actionAuto_Compile.setText("Autocompilar")
        self.ui.actionDark_Theme.setText("Tema oscuro")

        self.setup_log_panel()
        self.setup_project_tree()
        self.setup_outline_tree()
        self.setup_visual_tools()
        self.setup_toolbar()
        self.setup_find_bar()
        self.setup_status_bar()
        self.setup_view_menu_extras()
        self.update_title()

        # Restaurar preferencias guardadas
        saved_dark = self.settings.value("ui/dark_theme", True, type=bool)
        saved_dark_pdf = self.settings.value("ui/dark_pdf", False, type=bool)
        self.ui.actionDark_Theme.setChecked(saved_dark)
        self.apply_theme(saved_dark)
        self.action_dark_pdf.setChecked(saved_dark_pdf)

        self.update_project_root(pathlib.Path.home())
        self.update_outline()

        self.recent_menu = self.ui.menuFile.addMenu("Archivos recientes")
        self.update_recent_files_menu()

        self.template_menu = self.ui.menuFile.addMenu("Nuevo desde plantilla")
        for name in TEMPLATES:
            action = self.template_menu.addAction(name)
            action.triggered.connect(lambda checked=False, t=name: self.new_from_template(t))

        self.format_menu = self.menuBar().addMenu("Formato")
        act_bold = self.format_menu.addAction("Negrita (\\textbf)")
        act_bold.setShortcut("Ctrl+B")
        act_bold.triggered.connect(lambda: self.current_editor.wrap_selection(r"\textbf{", "}"))

        act_italic = self.format_menu.addAction("Cursiva (\\textit)")
        act_italic.setShortcut("Ctrl+I")
        act_italic.triggered.connect(lambda: self.current_editor.wrap_selection(r"\textit{", "}"))

        act_math = self.format_menu.addAction("Matemáticas ($...$)")
        act_math.setShortcut("Ctrl+M")
        act_math.triggered.connect(lambda: self.current_editor.wrap_selection("$", "$"))

        self.format_menu.addSeparator()
        act_comment = self.format_menu.addAction("Comentar / Descomentar (%)")
        act_comment.setShortcut("Ctrl+/")
        act_comment.triggered.connect(lambda: self.current_editor.toggle_comment())

        self.format_menu.addSeparator()
        act_table = self.format_menu.addAction("Generador visual de tablas...")
        act_table.setShortcut("Ctrl+Shift+T")
        act_table.triggered.connect(self.open_table_generator)

        act_sym_fmt = self.format_menu.addAction("Paleta de símbolos matemáticos")
        act_sym_fmt.setShortcut("Ctrl+Shift+Y")
        act_sym_fmt.triggered.connect(lambda: self.symbols_dock.setVisible(not self.symbols_dock.isVisible()))

        act_bib_fmt = self.format_menu.addAction("Gestor de bibliografía (.bib)")
        act_bib_fmt.setShortcut("Ctrl+Shift+B")
        act_bib_fmt.triggered.connect(self.toggle_bibliography_dock)

        self._shortcut_next_tab = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._shortcut_next_tab.activated.connect(lambda: self.cycle_tabs(1))
        self._shortcut_prev_tab = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._shortcut_prev_tab.activated.connect(lambda: self.cycle_tabs(-1))

        self.ui.menuView.addSeparator()
        act_palette = self.ui.menuView.addAction("Paleta de comandos...")
        act_palette.setShortcut("Ctrl+Shift+P")
        act_palette.triggered.connect(self.open_command_palette)

        self.help_menu = self.menuBar().addMenu("Ayuda")
        act_env_check = self.help_menu.addAction("Comprobar entorno LaTeX...")
        act_env_check.triggered.connect(self.open_environment_check)

        act_help_palette = self.help_menu.addAction("Paleta de comandos...")
        act_help_palette.triggered.connect(self.open_command_palette)

        self.help_menu.addSeparator()
        act_about = self.help_menu.addAction("Acerca de SeleneTeX...")
        act_about.triggered.connect(self.open_about_dialog)

        self.setup_ai_mascot()
        self.setup_math_preview()
        if self._restore_session:
            self.restore_session_state()
        self._apply_responsive_layout(self.width())

    # ------------------------------------------------------------------
    # Gestor de pestañas múltiples del editor
    # ------------------------------------------------------------------
    def setup_editor_tabs(self):
        self.editor_tabs = QTabWidget(self.ui.top_splitter)
        self.editor_tabs.setObjectName("editorTabs")
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.setMovable(True)
        self.editor_tabs.setUsesScrollButtons(True)
        self.editor_tabs.setElideMode(Qt.TextElideMode.ElideMiddle)

        self.btn_new_tab = QPushButton(self.editor_tabs)
        self.btn_new_tab.setObjectName("tabAddBtn")
        self.btn_new_tab.setIconSize(QSize(14, 14))
        self.btn_new_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_tab.setAccessibleName("Nueva pestaña")
        self.btn_new_tab.setToolTip("Nueva pestaña (Ctrl+N)")
        self.btn_new_tab.clicked.connect(self.action_new_triggered)
        self.editor_tabs.setCornerWidget(self.btn_new_tab, Qt.Corner.TopRightCorner)

        self.editor_tabs.tabBar().installEventFilter(self)

        # Sustituir el editor simple de form.ui por el contenedor con pestañas
        legacy_editor = self.ui.editor
        legacy_editor.hide()
        legacy_editor.setParent(None)
        legacy_editor.deleteLater()

        self.ui.top_splitter.insertWidget(0, self.editor_tabs)
        self._prev_active_editor: CodeEditor | None = None
        first_editor = self._create_editor_tab()
        self.ui.editor = first_editor
        self._prev_active_editor = first_editor
        self.editor_tabs.currentChanged.connect(self._on_tab_changed)

    def eventFilter(self, obj, event):
        if hasattr(self, "editor_tabs") and obj is self.editor_tabs.tabBar():
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton:
                idx = self.editor_tabs.tabBar().tabAt(event.pos())
                if idx >= 0:
                    self.close_tab(idx)
                    return True
        return super().eventFilter(obj, event)

    @property
    def current_editor(self) -> CodeEditor:
        widget = self.editor_tabs.currentWidget()
        if isinstance(widget, CodeEditor):
            return widget
        return self._create_editor_tab()

    @property
    def opened_file(self) -> pathlib.Path | None:
        return self.current_editor.file_path

    @opened_file.setter
    def opened_file(self, value: pathlib.Path | None):
        editor = self.current_editor
        editor.file_path = value
        self._update_tab_appearance(editor)

    def iter_editors(self) -> list[CodeEditor]:
        editors: list[CodeEditor] = []
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            if isinstance(w, CodeEditor):
                editors.append(w)
        return editors

    def _create_editor_tab(
        self,
        file_path: pathlib.Path | None = None,
        content: str = "",
        activate: bool = True,
    ) -> CodeEditor:
        editor = CodeEditor(self.editor_tabs)
        editor.file_path = file_path
        editor.set_tab_width(self._tab_width)
        editor.set_word_wrap(self._word_wrap)
        editor.set_auto_close_enabled(self._auto_close)
        editor.setFont(QFont(self._editor_font))
        editor.set_dark_mode(self._current_theme == "dark")
        editor.highlighter = LatexHighLighter(editor.document())
        editor.highlighter.set_theme(self._current_theme)
        editor.set_project_context_provider(self._get_editor_project_context)

        if content:
            editor.setPlainText(content)
            editor.document().setModified(False)

        editor.document().modificationChanged.connect(
            lambda mod, ed=editor: self._on_editor_modified_changed(ed, mod)
        )
        editor.textChanged.connect(lambda ed=editor: self._on_editor_text_changed(ed))
        editor.cursorPositionChanged.connect(
            lambda ed=editor: self._on_editor_cursor_moved(ed)
        )
        editor.selectionChanged.connect(
            lambda ed=editor: self._sync_ai_selection_state(ed)
        )
        editor.file_dropped.connect(self.on_file_dropped)
        editor.font_size_changed.connect(self._sync_editor_font_size)
        editor.ai_action_requested.connect(self.on_editor_ai_action)

        idx = self.editor_tabs.addTab(editor, "")
        self._attach_tab_close_button(idx, editor)
        self._update_tab_appearance(editor)

        if activate:
            self.editor_tabs.setCurrentIndex(idx)
            self.ui.editor = editor
        return editor

    def _attach_tab_close_button(self, index: int, editor: CodeEditor):
        t = SEMANTIC_TOKENS.get(self._current_theme, SEMANTIC_TOKENS["dark"])
        btn = QPushButton(self.editor_tabs.tabBar())
        btn.setObjectName("tabCloseBtn")
        btn.setIcon(svg_icon("close", t["text_muted"], 11, stroke_width=2.0))
        btn.setIconSize(QSize(11, 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAccessibleName("Cerrar pestaña")
        btn.setToolTip("Cerrar pestaña (Ctrl+W)")
        btn.clicked.connect(lambda checked=False, ed=editor: self.close_editor(ed))
        self.editor_tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)

    def _update_tab_appearance(self, editor: CodeEditor):
        idx = self.editor_tabs.indexOf(editor)
        if idx < 0:
            return
        name = editor.file_path.name if editor.file_path is not None else "Sin título"
        label = f"• {name}" if editor.document().isModified() else name
        self.editor_tabs.setTabText(idx, label)
        if editor.file_path is not None:
            tip = str(editor.file_path)
            if self.master_file is not None and editor.file_path == self.master_file:
                tip += " (Archivo maestro)"
        else:
            tip = "Documento sin guardar"
        self.editor_tabs.setTabToolTip(idx, tip)

    def _on_editor_modified_changed(self, editor: CodeEditor, modified: bool):
        self._update_tab_appearance(editor)
        if editor is self.current_editor:
            self.setWindowModified(modified)

    def _on_editor_text_changed(self, editor: CodeEditor):
        if editor is self.current_editor:
            self.on_text_changed()

    def _on_editor_cursor_moved(self, editor: CodeEditor):
        if editor is not self.current_editor:
            return
        self.update_cursor_status()
        if hasattr(self, "math_preview") and self._math_preview_auto:
            self._schedule_math_preview()

    def _sync_editor_font_size(self, point_size: int):
        self._editor_font.setPointSize(point_size)
        self.settings.setValue("editor/font_size", point_size)
        for ed in self.iter_editors():
            ed.set_font_point_size(point_size)

    def _on_tab_changed(self, index: int):
        if index < 0:
            return
        if self._prev_active_editor is not None and self._prev_active_editor is not self.editor_tabs.widget(index):
            try:
                self._prev_active_editor.set_search_highlights("")
            except RuntimeError:
                pass
        editor = self.editor_tabs.widget(index)
        if not isinstance(editor, CodeEditor):
            return
        self.ui.editor = editor
        self._prev_active_editor = editor
        self.setWindowModified(editor.document().isModified())
        self.update_title()
        if hasattr(self, "lbl_cursor"):
            self.update_cursor_status()
        if hasattr(self, "lbl_words"):
            self.update_word_count()
        if hasattr(self, "outline_tree"):
            self.update_outline()
        if hasattr(self, "find_bar") and self.find_bar.isVisible():
            self._refresh_find_matches()
        if hasattr(self, "ai_bubble"):
            self.ai_bubble.set_has_editor_selection(editor.textCursor().hasSelection())
        if hasattr(self, "math_preview"):
            self._math_preview_timer.stop()
            self._math_preview_last_key = None
            self.math_preview.hide()

    def _find_tab_by_path(self, path: pathlib.Path) -> int:
        try:
            target = path.resolve()
        except OSError:
            target = path
        for i in range(self.editor_tabs.count()):
            ed = self.editor_tabs.widget(i)
            if isinstance(ed, CodeEditor) and ed.file_path is not None:
                try:
                    if ed.file_path.resolve() == target:
                        return i
                except OSError:
                    if ed.file_path == path:
                        return i
        return -1

    def _is_reusable_empty_tab(self, editor: CodeEditor) -> bool:
        return (
            editor.file_path is None
            and not editor.document().isModified()
            and not editor.toPlainText().strip()
        )

    def close_editor(self, editor: CodeEditor):
        idx = self.editor_tabs.indexOf(editor)
        if idx >= 0:
            self.close_tab(idx)

    def close_tab(self, index: int):
        if index < 0 or index >= self.editor_tabs.count():
            return
        editor = self.editor_tabs.widget(index)
        if not isinstance(editor, CodeEditor):
            return
        if not self.maybe_save(editor):
            return

        if editor is self._prev_active_editor:
            self._prev_active_editor = None

        self.editor_tabs.removeTab(index)
        editor.deleteLater()

        if self.editor_tabs.count() == 0:
            fresh = self._create_editor_tab()
            self.ui.editor = fresh
            self.update_title()
            self.update_outline()
            self.update_word_count()
            self.update_cursor_status()

    def cycle_tabs(self, step: int):
        count = self.editor_tabs.count()
        if count <= 1:
            return
        nxt = (self.editor_tabs.currentIndex() + step) % count
        self.editor_tabs.setCurrentIndex(nxt)

    def _get_editor_project_context(self) -> dict:
        open_texts = [(ed.file_path, ed.toPlainText()) for ed in self.iter_editors()]
        anchor = self.master_file or self.opened_file
        base_dir = anchor.parent if anchor is not None else self._project_root
        return {"open_texts": open_texts, "base_dir": base_dir}

    # ------------------------------------------------------------------
    # Panel de salida (Log) con cabecera, progreso y resumen de errores
    # ------------------------------------------------------------------
    def setup_log_panel(self):
        self.log_container = QFrame(self.ui.main_splitter)
        self.log_container.setObjectName("logContainer")
        self.log_container.setMinimumHeight(96)

        container_layout = QVBoxLayout(self.log_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Cabecera del panel de registro
        log_header = QFrame(self.log_container)
        log_header.setObjectName("logHeader")
        header_layout = QHBoxLayout(log_header)
        header_layout.setContentsMargins(12, 4, 8, 4)
        header_layout.setSpacing(8)

        lbl_title = QLabel("Salida de compilación", log_header)
        lbl_title.setObjectName("logTitle")
        header_layout.addWidget(lbl_title)

        self.lbl_log_errors = QLabel("0 errores", log_header)
        self.lbl_log_errors.setObjectName("logBadgeError")
        self.lbl_log_errors.hide()
        header_layout.addWidget(self.lbl_log_errors)

        self.lbl_log_warnings = QLabel("0 avisos", log_header)
        self.lbl_log_warnings.setObjectName("logBadgeWarn")
        self.lbl_log_warnings.hide()
        header_layout.addWidget(self.lbl_log_warnings)

        header_layout.addStretch(1)

        self.btn_log_ai_fix = QPushButton(" Arreglar con IA", log_header)
        self.btn_log_ai_fix.setObjectName("aiActionBtn")
        self.btn_log_ai_fix.setIconSize(QSize(14, 14))
        self.btn_log_ai_fix.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log_ai_fix.setToolTip("Enviar el error de compilación a Selene IA")
        self.btn_log_ai_fix.clicked.connect(self._open_ai_and_fix_error)
        self.btn_log_ai_fix.hide()
        header_layout.addWidget(self.btn_log_ai_fix)

        self.btn_clear_log = QPushButton(" Limpiar", log_header)
        self.btn_clear_log.setObjectName("toolBtn")
        self.btn_clear_log.setIconSize(QSize(13, 13))
        self.btn_clear_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_log.setToolTip("Limpiar salida del registro")
        self.btn_clear_log.clicked.connect(self._clear_log)
        header_layout.addWidget(self.btn_clear_log)

        self.btn_hide_log = QPushButton(log_header)
        self.btn_hide_log.setObjectName("iconBtn")
        self.btn_hide_log.setIconSize(QSize(14, 14))
        self.btn_hide_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide_log.setAccessibleName("Ocultar panel de salida")
        self.btn_hide_log.setToolTip("Ocultar panel de salida (Ctrl+J)")
        self.btn_hide_log.clicked.connect(lambda: self.set_log_visible(False))
        header_layout.addWidget(self.btn_hide_log)

        container_layout.addWidget(log_header)

        # Barra de progreso fina durante compilación
        self.compile_progress = QProgressBar(self.log_container)
        self.compile_progress.setObjectName("compileProgress")
        self.compile_progress.setRange(0, 0)
        self.compile_progress.setTextVisible(False)
        self.compile_progress.hide()
        container_layout.addWidget(self.compile_progress)

        # Mover logView dentro de log_container conservando el widget original
        self.ui.logView.setParent(self.log_container)
        self.ui.logView.setAccessibleName("Registro de compilación de LuaLaTeX")
        self.ui.logView.setPlaceholderText(
            "La salida de LuaLaTeX aparecerá aquí. Haz clic en cualquier línea con error para saltar al código."
        )
        container_layout.addWidget(self.ui.logView, 1)

        self.ui.main_splitter.addWidget(self.log_container)
        self.ui.main_splitter.setChildrenCollapsible(False)
        self.ui.main_splitter.setSizes([660, 160])
        self.ui.main_splitter.setStretchFactor(0, 4)
        self.ui.main_splitter.setStretchFactor(1, 1)

    def _clear_log(self):
        self.ui.logView.clear()
        self._update_log_badges(0, 0)

    def _update_log_badges(self, errors: int, warnings: int):
        if errors > 0:
            self.lbl_log_errors.setText(f"{errors} {'error' if errors == 1 else 'errores'}")
            self.lbl_log_errors.show()
            self.btn_log_ai_fix.show()
        else:
            self.lbl_log_errors.hide()
            self.btn_log_ai_fix.hide()

        if warnings > 0:
            self.lbl_log_warnings.setText(f"{warnings} {'aviso' if warnings == 1 else 'avisos'}")
            self.lbl_log_warnings.show()
        else:
            self.lbl_log_warnings.hide()

    def _analyze_log_diagnostics(self):
        text = self.ui.logView.toPlainText()
        err_count = len(re.findall(r"(?:^! |\.tex:\d+: )", text, re.MULTILINE))
        warn_count = len(re.findall(r"(?:LaTeX Warning:|Package [^\n]+ Warning:|Overfull \\[hv]box)", text))
        self._update_log_badges(err_count, warn_count)

    def set_log_visible(self, visible: bool):
        if self._log_visible == visible:
            return
        if not visible:
            sizes = self.ui.main_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 40:
                self._last_log_height = sizes[1]
            self.log_container.hide()
        else:
            self.log_container.show()
            total = max(400, self.ui.main_splitter.height())
            log_h = min(self._last_log_height, max(120, total // 3))
            self.ui.main_splitter.setSizes([total - log_h, log_h])
        self._log_visible = visible
        if hasattr(self, "btn_status_log"):
            self.btn_status_log.blockSignals(True)
            self.btn_status_log.setChecked(visible)
            self.btn_status_log.blockSignals(False)
        if hasattr(self, "action_toggle_log"):
            self.action_toggle_log.blockSignals(True)
            self.action_toggle_log.setChecked(visible)
            self.action_toggle_log.blockSignals(False)
        if hasattr(self, "mascot"):
            QTimer.singleShot(0, self.position_mascot)

    def _open_ai_and_fix_error(self):
        if not self.ai_bubble.isVisible():
            self.toggle_ai_bubble()
        self.fix_log_error_with_ai()

    # ------------------------------------------------------------------
    # Barra de herramientas adaptativa (Regla 60-30-10 + Priority+)
    # ------------------------------------------------------------------
    def setup_toolbar(self):
        tb = QToolBar("Barra principal", self)
        tb.setObjectName("mainToolBar")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.main_toolbar = tb
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        def make_btn(text: str, tooltip: str, slot, obj_name: str = "toolBtn", checkable: bool = False):
            btn = QPushButton(text, tb)
            btn.setObjectName(obj_name)
            btn.setToolTip(tooltip)
            btn.setAccessibleName(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(checkable)
            if checkable:
                btn.toggled.connect(slot)
            else:
                btn.clicked.connect(slot)
            tb.addWidget(btn)
            return btn

        # Conmutador rápido de paneles laterales
        self.btn_sidebar = make_btn(
            "",
            "Mostrar u ocultar paneles laterales (Ctrl+\\)",
            self.toggle_sidebar_docks,
            obj_name="iconBtn",
            checkable=True,
        )
        self.btn_sidebar.setIconSize(QSize(16, 16))
        self.btn_sidebar.setChecked(True)
        tb.addSeparator()

        # Identidad visual SeleneTeX
        self._tb_logo_action = None
        if ICON_PATH.exists():
            logo_lbl = QLabel(tb)
            pm = QPixmap(str(ICON_PATH)).scaled(
                22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(pm)
            logo_lbl.setStyleSheet("padding: 0 4px 0 2px; background: transparent;")
            self._tb_logo_action = tb.addWidget(logo_lbl)

        self.brand_label = QLabel(APP_TITLE, tb)
        self.brand_label.setObjectName("brandTitle")
        self._tb_brand_action = tb.addWidget(self.brand_label)
        self._brand_sep = tb.addSeparator()

        # Grupo de archivo
        self.btn_new = make_btn("Nuevo", "Nuevo documento (Ctrl+N)", self.action_new_triggered)
        self.btn_open = make_btn("Abrir", "Abrir archivo .tex (Ctrl+O)", self.action_open_triggered)
        self.btn_save = make_btn("Guardar", "Guardar archivo (Ctrl+S)", self.action_save_triggered)
        self._tb_file_actions = [tb.actions()[-3], tb.actions()[-2], tb.actions()[-1]]
        self._tb_file_sep = tb.addSeparator()

        # Grupo de formato (sin setStyleSheet inline que anule :hover/:focus)
        btn_b = make_btn("B", "Negrita (Ctrl+B)", lambda: self.current_editor.wrap_selection(r"\textbf{", "}"), obj_name="formatBtn")
        b_font = btn_b.font()
        b_font.setBold(True)
        btn_b.setFont(b_font)

        btn_i = make_btn("I", "Cursiva (Ctrl+I)", lambda: self.current_editor.wrap_selection(r"\textit{", "}"), obj_name="formatBtn")
        i_font = btn_i.font()
        i_font.setItalic(True)
        i_font.setBold(True)
        btn_i.setFont(i_font)

        make_btn("$x$", "Modo matemático (Ctrl+M)", lambda: self.current_editor.wrap_selection("$", "$"), obj_name="formatBtn")

        self.btn_table_tool = make_btn(
            "",
            "Generador visual de tablas (Ctrl+Shift+T)",
            self.open_table_generator,
            obj_name="iconBtn",
        )
        self.btn_table_tool.setIconSize(QSize(15, 15))

        self.btn_symbols_tool = make_btn(
            "",
            "Paleta de símbolos matemáticos (Ctrl+Shift+Y)",
            lambda checked: self.symbols_dock.setVisible(checked),
            obj_name="iconBtn",
            checkable=True,
        )
        self.btn_symbols_tool.setIconSize(QSize(15, 15))
        self.symbols_dock.visibilityChanged.connect(self._sync_symbols_toggle)

        self._tb_format_actions = [tb.actions()[-5], tb.actions()[-4], tb.actions()[-3], tb.actions()[-2], tb.actions()[-1]]
        self._tb_format_sep = tb.addSeparator()

        # CTA primario único (10% acento visual) + botón Detener (solo visible al compilar)
        self.btn_compile = make_btn(
            " Compilar",
            f"Compilar con {self._compile_engine} (F5)",
            self.action_compile_triggered,
            obj_name="compileBtn",
        )
        self.btn_compile.setIconSize(QSize(13, 13))

        self.btn_stop_compile = make_btn(
            " Detener",
            "Detener la compilación en curso (Shift+F5)",
            self.stop_compilation,
            obj_name="stopBtn",
        )
        self.btn_stop_compile.setIconSize(QSize(12, 12))
        self._tb_stop_action = tb.actions()[-1]
        self._tb_stop_action.setVisible(False)

        # Espaciador flexible
        spacer = QWidget(tb)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        # Control segmentado de modo de vista (clave para ventanas compactas y enfoque)
        seg_frame = QFrame(tb)
        seg_frame.setObjectName("segmentedControl")
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)

        self.view_mode_group = QButtonGroup(self)
        self.view_mode_group.setExclusive(True)
        self._seg_buttons: dict[str, QPushButton] = {}
        for mode_id, label, tip in (
            ("editor", "Código", "Solo editor de código (Ctrl+1)"),
            ("split", "Dividido", "Vista dividida Editor + PDF (Ctrl+2)"),
            ("pdf", "PDF", "Solo visor PDF (Ctrl+3)"),
        ):
            sb = QPushButton(label, seg_frame)
            sb.setObjectName("segBtn")
            sb.setCheckable(True)
            sb.setCursor(Qt.CursorShape.PointingHandCursor)
            sb.setToolTip(tip)
            sb.setAccessibleName(tip)
            if mode_id == "split":
                sb.setChecked(True)
            sb.clicked.connect(lambda checked=False, m=mode_id: self.set_view_mode(m))
            self.view_mode_group.addButton(sb)
            seg_layout.addWidget(sb)
            self._seg_buttons[mode_id] = sb
        tb.addWidget(seg_frame)
        tb.addSeparator()

        # Controles PDF
        self.btn_zoom_out = make_btn("", "Alejar PDF (Ctrl+Rueda)", self.ui.pdfView.zoom_out, obj_name="iconBtn")
        self.btn_zoom_out.setIconSize(QSize(15, 15))
        self.btn_zoom_reset = make_btn(
            "100%", "Restablecer zoom al 100%", self.ui.pdfView.reset_zoom, obj_name="zoomBtn"
        )
        self.btn_zoom_in = make_btn("", "Acercar PDF (Ctrl+Rueda)", self.ui.pdfView.zoom_in, obj_name="iconBtn")
        self.btn_zoom_in.setIconSize(QSize(15, 15))
        self.ui.pdfView.zoom_changed.connect(
            lambda z: self.btn_zoom_reset.setText(f"{int(round(z * 100))}%")
        )
        self._tb_zoom_actions = [tb.actions()[-3], tb.actions()[-2], tb.actions()[-1]]
        self._tb_zoom_sep = tb.addSeparator()

        self.btn_sync = make_btn("", "Ir al PDF con SyncTeX (Ctrl+Shift+J)", self.sync_code_to_pdf, obj_name="iconBtn")
        self.btn_sync.setIconSize(QSize(15, 15))
        self._tb_sync_action = tb.actions()[-1]
        tb.addSeparator()

        # Botón de tema con icono vectorial limpio
        self.btn_theme = make_btn(
            "",
            "Cambiar entre Tema Oscuro y Tema Claro",
            self._toggle_theme_action,
            obj_name="iconBtn",
        )
        self.btn_theme.setIconSize(QSize(16, 16))

    def _toggle_theme_action(self):
        self.ui.actionDark_Theme.setChecked(not self.ui.actionDark_Theme.isChecked())

    def _on_dark_pdf_toggled(self, enabled: bool):
        self.ui.pdfView.set_dark_pdf(enabled)
        self.settings.setValue("ui/dark_pdf", enabled)

    # ------------------------------------------------------------------
    # Modos de vista y adaptación responsive por ancho de ventana
    # ------------------------------------------------------------------
    def set_view_mode(self, mode: str):
        if mode not in ("editor", "split", "pdf"):
            return
        self._view_mode = mode
        if mode == "editor":
            self.editor_tabs.show()
            self.ui.pdfView.hide()
        elif mode == "pdf":
            self.editor_tabs.hide()
            self.ui.pdfView.show()
        else:
            self.editor_tabs.show()
            self.ui.pdfView.show()
            total = max(480, self.ui.top_splitter.width())
            self.ui.top_splitter.setSizes([total // 2, total - total // 2])

        if hasattr(self, "_seg_buttons") and mode in self._seg_buttons:
            self._seg_buttons[mode].setChecked(True)
        if hasattr(self, "_view_mode_actions") and mode in self._view_mode_actions:
            self._view_mode_actions[mode].setChecked(True)
        if hasattr(self, "mascot"):
            QTimer.singleShot(0, self.position_mascot)

    def toggle_sidebar_docks(self, show: bool):
        self._docks_auto_collapsed = False
        self.project_dock.setVisible(show)
        self.outline_dock.setVisible(show)
        self._sync_sidebar_toggle()

    def _sync_sidebar_toggle(self):
        if hasattr(self, "btn_sidebar"):
            any_visible = self.project_dock.isVisible() or self.outline_dock.isVisible()
            self.btn_sidebar.blockSignals(True)
            self.btn_sidebar.setChecked(any_visible)
            self.btn_sidebar.blockSignals(False)

    def _apply_responsive_layout(self, width: int):
        """Adapta densidad de toolbar y paneles según el ancho disponible (sin overflow)."""
        if width >= 1140:
            tier = "wide"
        elif width >= 920:
            tier = "medium"
        else:
            tier = "compact"

        if tier == self._layout_tier:
            return
        prev_tier = self._layout_tier
        self._layout_tier = tier

        if tier == "wide":
            self._tb_brand_action.setVisible(True)
            self._brand_sep.setVisible(True)
            for act in self._tb_file_actions:
                act.setVisible(True)
            self._tb_file_sep.setVisible(True)
            for act in self._tb_format_actions:
                act.setVisible(True)
            self._tb_format_sep.setVisible(True)
            self._tb_sync_action.setVisible(True)
            self._tb_zoom_sep.setVisible(True)
            self.btn_compile.setText(" Compilar")
        elif tier == "medium":
            # Ocultar texto de marca (se mantiene logo) para evitar overflow
            self._tb_brand_action.setVisible(False)
            self._brand_sep.setVisible(True)
            for act in self._tb_file_actions:
                act.setVisible(True)
            self._tb_file_sep.setVisible(True)
            for act in self._tb_format_actions:
                act.setVisible(True)
            self._tb_format_sep.setVisible(True)
            self._tb_sync_action.setVisible(True)
            self._tb_zoom_sep.setVisible(True)
            self.btn_compile.setText(" Compilar")
        else:  # compact (< 920px): Priority+ oculta accesos ya presentes en menús Archivo/Formato
            self._tb_brand_action.setVisible(False)
            self._brand_sep.setVisible(False)
            for act in self._tb_file_actions:
                act.setVisible(False)
            self._tb_file_sep.setVisible(False)
            for act in self._tb_format_actions:
                act.setVisible(False)
            self._tb_format_sep.setVisible(False)
            self._tb_sync_action.setVisible(True)
            self._tb_zoom_sep.setVisible(True)
            self.btn_compile.setText(" Compilar")

        self._update_theme_button_label(self.ui.actionDark_Theme.isChecked())

        # Colapso automático de paneles laterales al estrechar ventana para proteger editor+PDF
        if tier == "compact" and prev_tier != "compact":
            if self.project_dock.isVisible() or self.outline_dock.isVisible():
                self._docks_state_before_collapse = (
                    self.project_dock.isVisible(),
                    self.outline_dock.isVisible(),
                )
                self._docks_auto_collapsed = True
                self.project_dock.hide()
                self.outline_dock.hide()
                self._sync_sidebar_toggle()
        elif tier != "compact" and self._docks_auto_collapsed:
            show_proj, show_out = self._docks_state_before_collapse
            self.project_dock.setVisible(show_proj)
            self.outline_dock.setVisible(show_out)
            self._docks_auto_collapsed = False
            self._sync_sidebar_toggle()

    def _update_theme_button_label(self, dark: bool):
        if not hasattr(self, "btn_theme"):
            return
        t = SEMANTIC_TOKENS["dark" if dark else "light"]
        self.btn_theme.setIcon(svg_icon("sun" if dark else "moon", t["text_secondary"], size=16))
        self.btn_theme.setToolTip(
            "Cambiar a Tema Claro" if dark else "Cambiar a Tema Oscuro"
        )

    def setup_view_menu_extras(self):
        self.ui.menuView.addSeparator()

        act_sidebar = self.ui.menuView.addAction("Mostrar / ocultar barra lateral")
        act_sidebar.setShortcut("Ctrl+\\")
        act_sidebar.triggered.connect(
            lambda: self.toggle_sidebar_docks(not (self.project_dock.isVisible() or self.outline_dock.isVisible()))
        )

        self.action_toggle_log = self.ui.menuView.addAction("Panel de salida (Log)")
        self.action_toggle_log.setCheckable(True)
        self.action_toggle_log.setChecked(True)
        self.action_toggle_log.setShortcut("Ctrl+J")
        self.action_toggle_log.toggled.connect(self.set_log_visible)

        self.ui.menuView.addSeparator()
        view_group = QActionGroup(self)
        view_group.setExclusive(True)
        self._view_mode_actions = {}
        for mode_id, label, shortcut in (
            ("editor", "Modo Solo Código", "Ctrl+1"),
            ("split", "Modo Vista Dividida", "Ctrl+2"),
            ("pdf", "Modo Solo PDF", "Ctrl+3"),
        ):
            act = self.ui.menuView.addAction(label)
            act.setCheckable(True)
            act.setShortcut(shortcut)
            if mode_id == "split":
                act.setChecked(True)
            act.triggered.connect(lambda checked=False, m=mode_id: self.set_view_mode(m))
            view_group.addAction(act)
            self._view_mode_actions[mode_id] = act

        self.ui.menuView.addSeparator()
        act_pdf_search = self.ui.menuView.addAction("Buscar en PDF")
        act_pdf_search.setShortcut("Ctrl+Shift+F")
        act_pdf_search.triggered.connect(self._open_pdf_search)

        act_fit = self.ui.menuView.addAction("Ajustar PDF al ancho")
        act_fit.setShortcut("Ctrl+0")
        act_fit.triggered.connect(self.ui.pdfView.fit_width)

        act_fit_page = self.ui.menuView.addAction("Ajustar PDF a página completa")
        act_fit_page.triggered.connect(self.ui.pdfView.fit_page)

        self.action_two_page_pdf = self.ui.menuView.addAction("Vista de doble página (PDF)")
        self.action_two_page_pdf.setCheckable(True)
        self.action_two_page_pdf.toggled.connect(self.ui.pdfView.set_two_page_mode)
        self.ui.pdfView.btn_two_page.toggled.connect(self._sync_two_page_action)

        act_rotate_pdf = self.ui.menuView.addAction("Rotar PDF 90°")
        act_rotate_pdf.triggered.connect(self.ui.pdfView.rotate_cw)

        act_zoom_in_ed = self.ui.menuView.addAction("Aumentar fuente del editor")
        act_zoom_in_ed.setShortcut("Ctrl++")
        act_zoom_in_ed.triggered.connect(lambda: self.current_editor.adjust_font_size(1))

        act_zoom_out_ed = self.ui.menuView.addAction("Reducir fuente del editor")
        act_zoom_out_ed.setShortcut("Ctrl+-")
        act_zoom_out_ed.triggered.connect(lambda: self.current_editor.adjust_font_size(-1))

    def _open_pdf_search(self):
        if self._view_mode == "editor":
            self.set_view_mode("split")
        self.ui.pdfView.show_search_bar()

    def _sync_two_page_action(self, checked: bool):
        self.action_two_page_pdf.blockSignals(True)
        self.action_two_page_pdf.setChecked(checked)
        self.action_two_page_pdf.blockSignals(False)

    # ------------------------------------------------------------------
    # Operaciones de archivo (con soporte de pestañas múltiples)
    # ------------------------------------------------------------------
    def action_open_triggered(self):
        file_filter = "Archivos LaTeX (*.tex *.bib *.sty *.cls);;Todos los archivos (*)"
        file_name, _ = QFileDialog.getOpenFileName(self, "Abrir documento LaTeX", self.dialog_dir(), file_filter)
        if file_name == "":
            return
        self.load_file(pathlib.Path(file_name))

    def load_file(self, path: pathlib.Path):
        existing_idx = self._find_tab_by_path(path)
        if existing_idx >= 0:
            self.editor_tabs.setCurrentIndex(existing_idx)
            self.current_editor.setFocus()
            return

        try:
            with open(path, "rt", encoding="utf-8") as file:
                content = file.read()

            cur = self.current_editor
            if self._is_reusable_empty_tab(cur):
                editor = cur
                editor.file_path = path
                editor.setPlainText(content)
                editor.document().setModified(False)
                editor.clear_diagnostics()
                self._update_tab_appearance(editor)
            else:
                editor = self._create_editor_tab(file_path=path, content=content, activate=True)

            if r"\documentclass" in content:
                self.master_file = path
                for ed in self.iter_editors():
                    self._update_tab_appearance(ed)

            self.ui.logView.appendPlainText(f"Archivo {path} abierto. \t {datetime.datetime.now()}")
            self.update_title()

            # Mantener la raíz del proyecto si el archivo pertenece a ella (p. ej. subcarpetas chapters/)
            keep_root = False
            if self._project_root is not None and self._project_root != pathlib.Path.home():
                try:
                    path.resolve().relative_to(self._project_root.resolve())
                    keep_root = True
                except ValueError:
                    keep_root = False
            if not keep_root:
                self.update_project_root(path.parent)

            self.add_recent_file(path)

            target_tex = self.master_file if self.master_file is not None else path
            pdf_path = target_tex.with_suffix(".pdf")
            if pdf_path.exists():
                self.ui.pdfView.load_pdf(pdf_path)
            elif target_tex == path:
                self.ui.pdfView.clear_pages()
                self.ui.pdfView.current_pdf = None

            self.auto_compiler_timer.stop()
            self.update_outline()
            self.update_page_count()
            self.update_word_count()
            self.update_cursor_status()
            if hasattr(self, "bib_dock") and self.bib_dock.isVisible():
                self.refresh_bibliography_panel()
            editor.setFocus()
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.critical(self, "Error al abrir", f"No se pudo abrir el archivo:\n{e}")

    def action_save_triggered(self):
        return self.save_editor(self.current_editor)

    def save_editor(self, editor: CodeEditor | None = None) -> bool:
        target = editor or self.current_editor
        if target.file_path is None:
            return self.save_editor_as(target)
        return self.save_to(target.file_path, editor=target)

    def action_new_triggered(self):
        self.new_from_template(DEFAULT_TEMPLATE)

    def action_saveas_triggered(self):
        return self.save_editor_as(self.current_editor)

    def save_editor_as(self, editor: CodeEditor | None = None) -> bool:
        target = editor or self.current_editor
        file_name, _ = QFileDialog.getSaveFileName(self, "Guardar documento LaTeX", self.dialog_dir(target), TEX_FILTER)
        if file_name == "":
            return False
        path = pathlib.Path(file_name)
        if path.suffix == "":
            path = path.with_suffix(".tex")
        return self.save_to(path, editor=target)

    def save_all_tabs(self) -> bool:
        saved_count = 0
        for editor in self.iter_editors():
            if editor.document().isModified():
                if editor.file_path is None:
                    self.editor_tabs.setCurrentWidget(editor)
                if not self.save_editor(editor):
                    return False
                saved_count += 1
        if saved_count > 0:
            self.statusBar().showMessage(
                f"{saved_count} {'archivo guardado' if saved_count == 1 else 'archivos guardados'}",
                3000,
            )
        return True

    def update_title(self):
        if self.opened_file is None:
            name = "Sin título"
        else:
            name = self.opened_file.name
        self.setWindowTitle(f"{name}[*] - {APP_TITLE}")

    def maybe_save(self, editor: CodeEditor | None = None) -> bool:
        target = editor or self.current_editor
        if target.document().isModified():
            doc_name = target.file_path.name if target.file_path is not None else "Sin título"
            msgbox = QMessageBox.question(
                self,
                "Documento no guardado",
                f"«{doc_name}» tiene cambios sin guardar.\n¿Quiere guardarlos?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            match msgbox:
                case QMessageBox.StandardButton.Save:
                    return self.save_editor(target)
                case QMessageBox.StandardButton.Discard:
                    return True
                case _:
                    return False
        return True

    def save_to(self, path: pathlib.Path, editor: CodeEditor | None = None) -> bool:
        target = editor or self.current_editor
        try:
            content = target.toPlainText()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            target.file_path = path
            if r"\documentclass" in content:
                self.master_file = path
                for ed in self.iter_editors():
                    self._update_tab_appearance(ed)
            target.document().setModified(False)
            self._update_tab_appearance(target)
            if target is self.current_editor:
                self.update_title()
                self.update_outline()
            if self._project_root is None or self._project_root == pathlib.Path.home():
                self.update_project_root(path.parent)
            self.add_recent_file(path)
            if hasattr(self, "bib_dock") and self.bib_dock.isVisible():
                self.refresh_bibliography_panel()
            self.ui.logView.appendPlainText(f"Archivo guardado en {path} \t {datetime.datetime.now()}")
            return True
        except OSError as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar el archivo:\n{e}")
            return False

    def dialog_dir(self, editor: CodeEditor | None = None):
        target = editor or self.current_editor
        if target.file_path is not None:
            return str(target.file_path.parent)
        if self._project_root is not None:
            return str(self._project_root)
        return str(pathlib.Path.home())

    # ------------------------------------------------------------------
    # Compilación (LuaLaTeX / pdfLaTeX / XeLaTeX) + detener + auxiliares
    # ------------------------------------------------------------------
    def setup_build_menu_extras(self):
        self.action_stop_compile = self.ui.menuBuild.addAction("Detener compilación")
        self.action_stop_compile.setShortcut("Shift+F5")
        self.action_stop_compile.setEnabled(False)
        self.action_stop_compile.triggered.connect(self.stop_compilation)

        self.ui.menuBuild.addSeparator()
        self.engine_menu = self.ui.menuBuild.addMenu("Motor de compilación")
        self._engine_action_group = QActionGroup(self)
        self._engine_action_group.setExclusive(True)
        self._engine_actions = {}
        for eng_name in LATEX_ENGINES:
            act = self.engine_menu.addAction(eng_name)
            act.setCheckable(True)
            act.setChecked(eng_name == self._compile_engine)
            act.triggered.connect(lambda checked=False, e=eng_name: self.set_compile_engine(e))
            self._engine_action_group.addAction(act)
            self._engine_actions[eng_name] = act

        self.action_shell_escape = self.ui.menuBuild.addAction("Habilitar --shell-escape (minted / svg)")
        self.action_shell_escape.setCheckable(True)
        self.action_shell_escape.setChecked(self._shell_escape)
        self.action_shell_escape.toggled.connect(self.set_shell_escape)

        self.ui.menuBuild.addSeparator()
        act_clean = self.ui.menuBuild.addAction("Limpiar archivos auxiliares (.tex_builds)")
        act_clean.triggered.connect(self.clean_auxiliary_files)

    def set_compile_engine(self, engine_name: str):
        if engine_name not in LATEX_ENGINES:
            return
        self._compile_engine = engine_name
        self.settings.setValue("build/engine", engine_name)
        if engine_name in getattr(self, "_engine_actions", {}):
            self._engine_actions[engine_name].setChecked(True)
        self._refresh_engine_indicators()
        self.statusBar().showMessage(f"Motor de compilación: {engine_name}", 3000)

    def set_shell_escape(self, enabled: bool):
        self._shell_escape = bool(enabled)
        self.settings.setValue("build/shell_escape", self._shell_escape)
        if hasattr(self, "action_shell_escape"):
            self.action_shell_escape.blockSignals(True)
            self.action_shell_escape.setChecked(self._shell_escape)
            self.action_shell_escape.blockSignals(False)
        self._refresh_engine_indicators()
        state_txt = "habilitado" if self._shell_escape else "deshabilitado"
        self.statusBar().showMessage(f"--shell-escape {state_txt}", 3000)

    def _refresh_engine_indicators(self):
        label = f"{self._compile_engine} • shell-escape" if self._shell_escape else self._compile_engine
        if hasattr(self, "btn_engine"):
            self.btn_engine.setText(label)
        if hasattr(self, "btn_compile"):
            self.btn_compile.setToolTip(f"Compilar con {self._compile_engine} (F5)")

    def _build_latexmk_args(self, target_tex: pathlib.Path) -> list[str]:
        engine_flag = LATEX_ENGINES.get(self._compile_engine, "-lualatex")
        build_dir = f".tex_builds/{target_tex.stem}"
        args = [
            engine_flag,
            "-synctex=1",
            "-emulate-aux-dir",
            f"-auxdir={build_dir}",
            "-interaction=nonstopmode",
            "-file-line-error",
        ]
        if self._shell_escape:
            args.append("-shell-escape")
        args.append(target_tex.name)
        return args

    def _set_compiling_ui(self, active: bool):
        self.ui.actionCompile.setEnabled(not active)
        if hasattr(self, "action_stop_compile"):
            self.action_stop_compile.setEnabled(active)
        if hasattr(self, "_tb_stop_action"):
            self._tb_stop_action.setVisible(active)
        if hasattr(self, "btn_compile"):
            self.btn_compile.setEnabled(not active)
            if active:
                self.btn_compile.setText(" Compilando...")
                self.btn_compile.setIcon(svg_icon("loader", "#94a3b8", size=13, stroke_width=2.0))
            else:
                self.btn_compile.setText(" Compilar")
                self.btn_compile.setIcon(svg_icon("play", "#ffffff", size=13, stroke_width=2.0))
        self.compile_progress.setVisible(active)

    def stop_compilation(self):
        if self.compiler.state() == QProcess.ProcessState.NotRunning:
            return
        self._compile_aborted = True
        self.ui.logView.appendPlainText("\nDeteniendo compilación...\n")
        self.statusBar().showMessage("Deteniendo compilación...", 3000)
        self.compiler.terminate()
        QTimer.singleShot(
            1500,
            lambda: self.compiler.kill()
            if self.compiler.state() != QProcess.ProcessState.NotRunning
            else None,
        )

    def action_compile_triggered(self):
        if self.compiler.state() != QProcess.ProcessState.NotRunning:
            self.ui.logView.appendPlainText("Compilación en ejecución. Espere un momento.\n")
            return
        if self.opened_file is None or self.current_editor.document().isModified():
            if not self.action_save_triggered():
                return

        # Guardar también otras pestañas modificadas que ya tengan ruta (subarchivos \input / .bib)
        for ed in self.iter_editors():
            if ed is not self.current_editor and ed.file_path is not None and ed.document().isModified():
                if not self.save_to(ed.file_path, editor=ed):
                    return

        target_tex = self.master_file if self.master_file is not None else self.opened_file
        if target_tex is None or target_tex.suffix.lower() != ".tex":
            # Si la pestaña activa es un .bib/.sty y hay un .tex abierto, compilar ese .tex
            for ed in self.iter_editors():
                if ed.file_path is not None and ed.file_path.suffix.lower() == ".tex":
                    target_tex = ed.file_path
                    break
        if target_tex is None:
            return

        self.compiling_file = target_tex
        self._compile_aborted = False
        for ed in self.iter_editors():
            ed.clear_diagnostics()

        self.compiler.setWorkingDirectory(str(target_tex.parent))
        self._set_compiling_ui(True)
        self._update_log_badges(0, 0)
        self._set_compile_status("compiling", f"Compilando ({self._compile_engine})...")
        self.statusBar().showMessage(f"Compilando {target_tex.name} con {self._compile_engine}...")
        self.ui.pdfView.show_loading_state(target_tex.name, engine_name=self._compile_engine)

        args = self._build_latexmk_args(target_tex)
        self.ui.logView.clear()
        self.compiler.start("latexmk", args)

    def on_compile_output(self):
        data = self.compiler.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.ui.logView.appendPlainText(data.rstrip())

    def _apply_inline_log_diagnostics(self, target_tex: pathlib.Path | None):
        """Extrae errores y avisos con línea del log de LaTeX y los marca en las pestañas abiertas."""
        log_text = self.ui.logView.toPlainText()
        base_dir = target_tex.parent if target_tex is not None else None
        parsed: list[tuple[pathlib.Path | None, int, str, str]] = []

        lines = log_text.splitlines()
        pending_bang_msg = ""
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Formato -file-line-error: ./archivo.tex:42: Mensaje de error
            m_fle = re.match(r"^(?:\./)?([^:\s][^:]*\.tex):(\d+):\s*(.+)$", line)
            if m_fle:
                fpath_str, lnum_str, msg = m_fle.group(1), m_fle.group(2), m_fle.group(3).strip()
                fpath = pathlib.Path(fpath_str)
                if not fpath.is_absolute() and base_dir is not None:
                    fpath = base_dir / fpath
                parsed.append((fpath, int(lnum_str), "error", msg))
                pending_bang_msg = ""
                continue

            # Formato clásico ! Error ... seguido de l.42 ...
            if line.startswith("! "):
                pending_bang_msg = line[2:].strip()
                continue
            m_lnum = re.match(r"^l\.(\d+)\s*(.*)$", line)
            if m_lnum and pending_bang_msg:
                parsed.append((target_tex, int(m_lnum.group(1)), "error", pending_bang_msg))
                pending_bang_msg = ""
                continue

            # Avisos de LaTeX / Paquetes / Overfull con número de línea
            m_warn = re.search(r"((?:LaTeX|Package [^\n]+|Class [^\n]+)\s+Warning:.*?)on input line (\d+)", line)
            if m_warn:
                parsed.append((target_tex, int(m_warn.group(2)), "warning", m_warn.group(1).strip()))
                continue

            m_overfull = re.search(r"(Overfull \\[hv]box[^\n]*?)at lines? (\d+)", line)
            if m_overfull:
                parsed.append((target_tex, int(m_overfull.group(2)), "warning", m_overfull.group(1).strip()))

        for editor in self.iter_editors():
            ed_diags: dict[int, list[tuple[str, str]]] = {}
            ed_path = editor.file_path
            ed_resolved = None
            if ed_path is not None:
                try:
                    ed_resolved = ed_path.resolve()
                except OSError:
                    ed_resolved = ed_path

            for d_path, line_num, sev, msg in parsed:
                matched = False
                if d_path is not None and ed_resolved is not None:
                    try:
                        matched = d_path.resolve() == ed_resolved or d_path.name == ed_path.name
                    except OSError:
                        matched = d_path.name == ed_path.name
                elif d_path is None and editor is self.current_editor:
                    matched = True

                if matched:
                    bucket = ed_diags.setdefault(line_num, [])
                    if (sev, msg) not in bucket:
                        bucket.append((sev, msg))

            editor.set_diagnostics(ed_diags)

    def on_compile_finished(self, exit_code, exit_status):
        self._set_compiling_ui(False)
        target_tex = getattr(self, "compiling_file", None) or self.master_file or self.opened_file
        if self._compile_aborted:
            self._compile_aborted = False
            self.ui.logView.appendPlainText("\nCompilación detenida por el usuario.\n")
            self.statusBar().showMessage("Compilación detenida", 4000)
            self._set_compile_status("stopped", "Detenido")
            if self.ui.pdfView.page_count() == 0:
                self.ui.pdfView.clear_pages(show_empty=True)
            return

        pdf_path = target_tex.with_suffix(".pdf")
        if exit_code == 0:
            self.ui.logView.appendPlainText("\nCompilación Exitosa\n")
            self.statusBar().showMessage(f"Compilación terminada ({self._compile_engine})", 4000)
            self._set_compile_status("ok", "Listo")
            self.ui.pdfView.load_pdf(pdf_path)
        else:
            self.ui.logView.appendPlainText("\nError en la compilación\n")
            self.statusBar().showMessage("Error en compilación — revisa el registro", 5000)
            self._set_compile_status("error", "Error")
            self.set_log_visible(True)
            if pdf_path.exists():
                self.ui.pdfView.load_pdf(pdf_path)
            else:
                self.ui.pdfView.show_error_state()

        self._analyze_log_diagnostics()
        self._apply_inline_log_diagnostics(target_tex)
        self.update_page_count()

        synctex_file = target_tex.with_suffix(".synctex.gz")
        if synctex_file.exists():
            target_dir = target_tex.parent / ".tex_builds" / target_tex.stem
            target_dir.mkdir(parents=True, exist_ok=True)
            synctex_file.replace(target_dir / synctex_file.name)

    def _active_project_dir(self) -> pathlib.Path | None:
        anchor = self.master_file or self.opened_file
        if anchor is not None:
            return anchor.parent
        if self._project_root is not None and self._project_root != pathlib.Path.home():
            return self._project_root
        return None

    def clean_auxiliary_files(self, target_dir: pathlib.Path | None = None) -> int:
        folder = target_dir if isinstance(target_dir, pathlib.Path) else self._active_project_dir()
        if folder is None or not folder.is_dir():
            self.statusBar().showMessage("Abre o guarda un proyecto para limpiar auxiliares", 3500)
            return 0

        removed = 0
        builds_dir = folder / ".tex_builds"
        if builds_dir.is_dir():
            try:
                shutil.rmtree(builds_dir)
                removed += 1
            except OSError as e:
                QMessageBox.warning(self, "Error al limpiar", f"No se pudo eliminar .tex_builds:\n{e}")
                return 0

        for item in folder.iterdir():
            if not item.is_file():
                continue
            name_lower = item.name.lower()
            if (
                item.suffix.lower() in AUX_CLEAN_EXTENSIONS
                or name_lower.endswith(".synctex.gz")
                or name_lower.endswith(".run.xml")
            ):
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    pass

        if removed > 0:
            msg = f"Limpieza completada: {removed} elemento(s) auxiliar(es) eliminado(s)"
            self.ui.logView.appendPlainText(msg)
            self.statusBar().showMessage(msg, 4000)
        else:
            self.statusBar().showMessage("No se encontraron archivos auxiliares para limpiar", 3500)
        return removed

    def export_pdf_as(self) -> bool:
        target_tex = self.master_file or self.opened_file
        pdf_path = target_tex.with_suffix(".pdf") if target_tex is not None else self.ui.pdfView.current_pdf
        if pdf_path is None or not pathlib.Path(pdf_path).is_file():
            QMessageBox.information(
                self,
                "Sin PDF compilado",
                "Compila primero tu documento con F5 para generar el PDF antes de exportarlo.",
            )
            return False

        src = pathlib.Path(pdf_path)
        default_dest = str(src.parent / src.name)
        dest_str, _ = QFileDialog.getSaveFileName(self, "Exportar PDF como...", default_dest, "Documento PDF (*.pdf)")
        if not dest_str:
            return False
        dest = pathlib.Path(dest_str)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        try:
            shutil.copy2(src, dest)
            self.statusBar().showMessage(f"PDF exportado a {dest}", 4000)
            return True
        except OSError as e:
            QMessageBox.critical(self, "Error al exportar PDF", f"No se pudo copiar el PDF:\n{e}")
            return False

    def export_project_zip(self, dest_path: pathlib.Path | None = None) -> bool:
        project_dir = self._active_project_dir()
        if project_dir is None or not project_dir.is_dir():
            QMessageBox.information(
                self,
                "Sin carpeta de proyecto",
                "Abre o guarda un archivo en una carpeta de proyecto antes de exportar a ZIP.",
            )
            return False

        if dest_path is None:
            default_zip = str(project_dir.parent / f"{project_dir.name}.zip")
            dest_str, _ = QFileDialog.getSaveFileName(
                self,
                "Exportar proyecto como ZIP",
                default_zip,
                "Archivo ZIP (*.zip)",
            )
            if not dest_str:
                return False
            dest_path = pathlib.Path(dest_str)
            if dest_path.suffix.lower() != ".zip":
                dest_path = dest_path.with_suffix(".zip")

        try:
            dest_resolved = dest_path.resolve()
            file_count = 0
            with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in sorted(project_dir.rglob("*")):
                    if not p.is_file():
                        continue
                    rel = p.relative_to(project_dir)
                    if any(part in ZIP_EXCLUDE_DIRS for part in rel.parts):
                        continue
                    if p.resolve() == dest_resolved:
                        continue
                    zf.write(p, arcname=rel.as_posix())
                    file_count += 1
            self.statusBar().showMessage(f"Proyecto exportado ({file_count} archivos) → {dest_path.name}", 4500)
            return True
        except OSError as e:
            QMessageBox.critical(self, "Error al exportar ZIP", f"No se pudo crear el archivo ZIP:\n{e}")
            return False

    def apply_theme(self, dark: bool):
        theme_name = "dark" if dark else "light"
        self._current_theme = theme_name
        self.log_highlighter.set_theme(theme_name)
        self.setStyleSheet(DARK_STYLESHEET if dark else LIGHT_STYLESHEET)
        for editor in self.iter_editors():
            if editor.highlighter is not None:
                editor.highlighter.set_theme(theme_name)
            editor.set_dark_mode(dark)
        self.ui.pdfView.set_theme(theme_name)
        if hasattr(self, "ai_bubble"):
            self.ai_bubble.set_theme(theme_name)
        if hasattr(self, "bib_widget"):
            self.bib_widget.set_theme(theme_name)
        if hasattr(self, "math_preview"):
            self.math_preview.set_theme(theme_name)
            if self.math_preview.isVisible():
                self._math_preview_last_key = None
                self.trigger_math_preview(force=True)
        self._refresh_theme_icons(theme_name)
        self._update_theme_button_label(dark)
        self.settings.setValue("ui/dark_theme", dark)

    def _refresh_theme_icons(self, theme_name: str):
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        fg = t["text_secondary"]
        muted = t["text_muted"]
        accent = t["accent_text"]

        if hasattr(self, "btn_table_tool"):
            self.btn_table_tool.setIcon(svg_icon("table", fg, 15))
        if hasattr(self, "btn_symbols_tool"):
            self.btn_symbols_tool.setIcon(svg_icon("sigma", fg, 15, active_color=accent))

        if hasattr(self, "btn_new_tab"):
            self.btn_new_tab.setIcon(svg_icon("plus", muted, 14, stroke_width=2.0))
        if hasattr(self, "editor_tabs"):
            tb = self.editor_tabs.tabBar()
            for i in range(self.editor_tabs.count()):
                close_btn = tb.tabButton(i, QTabBar.ButtonPosition.RightSide)
                if isinstance(close_btn, QPushButton):
                    close_btn.setIcon(svg_icon("close", muted, 11, stroke_width=2.0))

        if hasattr(self, "btn_sidebar"):
            self.btn_sidebar.setIcon(svg_icon("sidebar", muted, 16, active_color=accent))
        if hasattr(self, "btn_compile") and self.btn_compile.isEnabled():
            self.btn_compile.setIcon(svg_icon("play", "#ffffff", 13, stroke_width=2.0))
        if hasattr(self, "btn_stop_compile"):
            self.btn_stop_compile.setIcon(svg_icon("stop", t["danger_text"], 11))
        if hasattr(self, "btn_zoom_out"):
            self.btn_zoom_out.setIcon(svg_icon("minus", fg, 15))
        if hasattr(self, "btn_zoom_in"):
            self.btn_zoom_in.setIcon(svg_icon("plus", fg, 15))
        if hasattr(self, "btn_sync"):
            self.btn_sync.setIcon(svg_icon("sync", fg, 15))

        if hasattr(self, "btn_log_ai_fix"):
            self.btn_log_ai_fix.setIcon(svg_icon("sparkles", accent, 14))
        if hasattr(self, "btn_clear_log"):
            self.btn_clear_log.setIcon(svg_icon("trash", muted, 13))
        if hasattr(self, "btn_hide_log"):
            self.btn_hide_log.setIcon(svg_icon("close", muted, 14))

        if hasattr(self, "btn_status_log"):
            self.btn_status_log.setIcon(svg_icon("terminal", muted, 13, active_color=accent))

        if hasattr(self, "btn_toggle_replace"):
            is_open = self.btn_toggle_replace.isChecked()
            self.btn_toggle_replace.setIcon(
                svg_icon("chevron_down" if is_open else "chevron_right", fg, 15)
            )
        if hasattr(self, "btn_find_prev"):
            self.btn_find_prev.setIcon(svg_icon("arrow_up", fg, 14))
        if hasattr(self, "btn_find_next"):
            self.btn_find_next.setIcon(svg_icon("arrow_down", fg, 14))
        if hasattr(self, "btn_find_close"):
            self.btn_find_close.setIcon(svg_icon("close", muted, 14))

        for icon_lbl, icon_name, close_btn in getattr(self, "_dock_header_refs", []):
            icon_lbl.setPixmap(svg_pixmap(icon_name, muted, 13))
            close_btn.setIcon(svg_icon("close", muted, 13))

        if hasattr(self, "file_icon_provider"):
            self.file_icon_provider.set_theme(theme_name)
            self.tree_view.viewport().update()

    def on_text_changed(self):
        self.update_word_count()
        self.update_outline()
        if hasattr(self, "find_bar") and self.find_bar.isVisible():
            self._refresh_find_matches()
        if hasattr(self, "math_preview") and self._math_preview_auto:
            self._schedule_math_preview()
        if self.ui.actionAuto_Compile.isChecked() and self.opened_file is not None:
            self.auto_compiler_timer.start()

    def on_log_cursor_changed(self):
        if not self.ui.logView.hasFocus():
            return
        line_text = self.ui.logView.textCursor().block().text().strip()
        m_file = re.match(r"^(?:\./)?([^:\s][^:]*\.tex):(\d+)", line_text)
        if m_file:
            rel_str, line_num = m_file.group(1), int(m_file.group(2))
            anchor = getattr(self, "compiling_file", None) or self.master_file or self.opened_file
            target = pathlib.Path(rel_str)
            if not target.is_absolute() and anchor is not None:
                target = anchor.parent / target
            if target.exists():
                self.load_file(target)
            self.current_editor.go_to_line(line_num)
            self.statusBar().showMessage(f"Saltando a {target.name}:{line_num}", 3000)
            return

        match = re.search(r"(?:\.tex:|^l\.)(\d+)", line_text)
        if match:
            line_num = int(match.group(1))
            self.current_editor.go_to_line(line_num)
            self.statusBar().showMessage(f"Saltando a la línea {line_num}", 3000)

    # ------------------------------------------------------------------
    # Paneles laterales: Proyecto y Esquema (cabecera limpia + iconos SVG)
    # ------------------------------------------------------------------
    def _make_dock_header(self, dock: QDockWidget, title_text: str, icon_name: str, subtitle_text: str = ""):
        header = QFrame(dock)
        header.setObjectName("dockHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(6)

        icon_lbl = QLabel(header)
        title_lbl = QLabel(title_text.upper(), header)
        title_lbl.setObjectName("dockTitle")

        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)

        subtitle_lbl = None
        if subtitle_text is not None:
            subtitle_lbl = QLabel(subtitle_text, header)
            subtitle_lbl.setObjectName("dockSubtitle")
            if not subtitle_text:
                subtitle_lbl.hide()
            layout.addWidget(subtitle_lbl)

        layout.addStretch(1)

        close_btn = QPushButton(header)
        close_btn.setObjectName("dockCloseBtn")
        close_btn.setIconSize(QSize(13, 13))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setAccessibleName(f"Ocultar panel {title_text}")
        close_btn.setToolTip(f"Ocultar {title_text}")
        close_btn.clicked.connect(dock.hide)
        layout.addWidget(close_btn)

        if not hasattr(self, "_dock_header_refs"):
            self._dock_header_refs = []
        self._dock_header_refs.append((icon_lbl, icon_name, close_btn))
        return header, subtitle_lbl

    def setup_project_tree(self):
        self.file_icon_provider = SeleneFileIconProvider("dark")
        self.file_model = QFileSystemModel(self)
        self.file_model.setIconProvider(self.file_icon_provider)
        self.file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs | QDir.Filter.Files)
        self.file_model.setNameFilterDisables(False)

        self.tree_view = QTreeView(self)
        self.tree_view.setAccessibleName("Explorador de archivos del proyecto")
        self.tree_view.setModel(self.file_model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIconSize(QSize(15, 15))
        self.tree_view.setIndentation(16)

        for col in (1, 2, 3):
            self.tree_view.setColumnHidden(col, True)

        self.tree_view.doubleClicked.connect(self.on_tree_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.on_project_tree_context_menu)

        self.project_dock = QDockWidget("Proyecto", self)
        self.project_dock.setMinimumWidth(190)
        self.project_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        proj_header, self.lbl_project_folder = self._make_dock_header(
            self.project_dock, "Proyecto", "folder_open", ""
        )
        self.project_dock.setTitleBarWidget(proj_header)
        self.project_dock.setWidget(self.tree_view)
        self.project_dock.visibilityChanged.connect(lambda *_: self._sync_sidebar_toggle())
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.project_dock)
        self.ui.menuView.addAction(self.project_dock.toggleViewAction())

    def setup_outline_tree(self):
        self.outline_tree = QTreeWidget(self)
        self.outline_tree.setAccessibleName("Esquema de secciones del documento")
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.setIndentation(14)
        self.outline_tree.itemClicked.connect(self.on_outline_item_clicked)

        self.outline_dock = QDockWidget("Esquema", self)
        self.outline_dock.setMinimumWidth(190)
        self.outline_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        outline_header, _ = self._make_dock_header(
            self.outline_dock, "Esquema", "outline", None
        )
        self.outline_dock.setTitleBarWidget(outline_header)
        self.outline_dock.setWidget(self.outline_tree)
        self.outline_dock.visibilityChanged.connect(lambda *_: self._sync_sidebar_toggle())
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.outline_dock)
        self.ui.menuView.addAction(self.outline_dock.toggleViewAction())

    # ------------------------------------------------------------------
    # Herramientas visuales: Paleta de símbolos, Tablas y Bibliografía (.bib)
    # ------------------------------------------------------------------
    def setup_visual_tools(self):
        # 1. Dock de Paleta de símbolos matemáticos y griegos
        self.symbols_widget = SymbolPaletteWidget(self)
        self.symbols_widget.symbol_selected.connect(self.insert_symbol_snippet)

        self.symbols_dock = QDockWidget("Símbolos", self)
        self.symbols_dock.setMinimumWidth(220)
        self.symbols_dock.setMaximumWidth(320)
        self.symbols_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        sym_header, _ = self._make_dock_header(self.symbols_dock, "Símbolos", "sigma", None)
        self.symbols_dock.setTitleBarWidget(sym_header)
        self.symbols_dock.setWidget(self.symbols_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.symbols_dock)
        self.symbols_dock.hide()
        self.ui.menuView.addAction(self.symbols_dock.toggleViewAction())

        # 2. Dock de Gestor de bibliografía (.bib)
        self.bib_widget = BibliographyDockWidget(self)
        self.bib_widget.cite_requested.connect(self.insert_citation_key)
        self.bib_widget.bibtex_entry_added.connect(self.append_bibtex_entry)
        self.bib_widget.refresh_requested.connect(self.refresh_bibliography_panel)

        self.bib_dock = QDockWidget("Bibliografía", self)
        self.bib_dock.setMinimumWidth(235)
        self.bib_dock.setMaximumWidth(340)
        self.bib_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        bib_header, _ = self._make_dock_header(self.bib_dock, "Bibliografía", "book", ".bib")
        self.bib_dock.setTitleBarWidget(bib_header)
        self.bib_dock.setWidget(self.bib_widget)
        self.bib_dock.visibilityChanged.connect(
            lambda vis: self.refresh_bibliography_panel() if vis else None
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.bib_dock)
        self.bib_dock.hide()
        self.ui.menuView.addAction(self.bib_dock.toggleViewAction())

    def _sync_symbols_toggle(self, visible: bool):
        if hasattr(self, "btn_symbols_tool"):
            self.btn_symbols_tool.blockSignals(True)
            self.btn_symbols_tool.setChecked(visible)
            self.btn_symbols_tool.blockSignals(False)

    def toggle_bibliography_dock(self):
        show = not self.bib_dock.isVisible()
        self.bib_dock.setVisible(show)
        if show:
            self.refresh_bibliography_panel()

    def open_table_generator(self):
        dlg = TableGeneratorDialog(self._current_theme, self)
        if dlg.exec() != TableGeneratorDialog.DialogCode.Accepted or not dlg.generated_code:
            return
        editor = self.current_editor
        insert_cursor = editor.textCursor()
        if dlg.needs_booktabs:
            existing = extract_document_packages(editor.toPlainText())
            if "booktabs" not in existing:
                self.add_packages_to_preamble(["booktabs"])
        insert_cursor.beginEditBlock()
        insert_cursor.insertText(dlg.generated_code)
        insert_cursor.endEditBlock()
        editor.setTextCursor(insert_cursor)
        editor.setFocus()
        self.statusBar().showMessage("Tabla LaTeX insertada", 3000)

    def insert_symbol_snippet(self, snippet: str):
        editor = self.current_editor
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(snippet)
        empty_brace = snippet.find("{}")
        if empty_brace != -1:
            offset = len(snippet) - empty_brace - 1
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, offset)
        elif snippet.endswith("  \\right)"):
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(" \\right)"))
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        editor.setFocus()

    def insert_citation_key(self, key: str):
        editor = self.current_editor
        cursor = editor.textCursor()
        line_before = cursor.block().text()[: cursor.positionInBlock()]
        # Si el cursor ya está dentro de \cite{...}, añadir la clave directamente (con coma si procede)
        m_cite = re.search(
            r"\\(?:paren|text|auto|foot|super|no|full|smart)?cite(?:author|year|title|[pt])?\*?(?:\[[^\]]*\])*\{([^}]*)$",
            line_before,
        )
        cursor.beginEditBlock()
        if m_cite:
            inner = m_cite.group(1).strip()
            prefix = ", " if inner and not inner.endswith(",") else ""
            cursor.insertText(f"{prefix}{key}")
        else:
            cursor.insertText(f"\\cite{{{key}}}")
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        editor.setFocus()
        self.statusBar().showMessage(f"Cita insertada: {key}", 2500)

    def _find_project_bib_files(self) -> list[pathlib.Path]:
        candidates: list[pathlib.Path] = []
        seen: set[pathlib.Path] = set()

        def add_path(p: pathlib.Path):
            try:
                resolved = p.resolve()
            except OSError:
                return
            if resolved not in seen and resolved.is_file():
                seen.add(resolved)
                candidates.append(resolved)

        # 1. Pestañas .bib abiertas
        for ed in self.iter_editors():
            if ed.file_path is not None and ed.file_path.suffix.lower() == ".bib":
                add_path(ed.file_path)

        # 2. Referenciados en el documento o presentes en la carpeta del proyecto
        base_dir = self._active_project_dir()
        if base_dir is not None and base_dir.is_dir():
            bib_res_re = re.compile(r"\\(?:addbibresource|bibliography)(?:\[[^\]]*\])?\{([^}]+)\}")
            for ed in self.iter_editors():
                for m in bib_res_re.finditer(ed.toPlainText()):
                    for raw in m.group(1).split(","):
                        name = raw.strip()
                        if not name:
                            continue
                        p = base_dir / name
                        if p.suffix == "":
                            p = p.with_suffix(".bib")
                        add_path(p)
            for folder in (base_dir, base_dir / "bib", base_dir / "bibliography"):
                if folder.is_dir():
                    for p in sorted(folder.glob("*.bib"))[:12]:
                        add_path(p)
        return candidates

    def refresh_bibliography_panel(self):
        if not hasattr(self, "bib_widget"):
            return
        entries: list[dict] = []
        seen_keys: set[str] = set()
        open_bib_resolved: set[pathlib.Path] = set()

        # Leer primero pestañas .bib abiertas (pueden tener cambios sin guardar)
        for ed in self.iter_editors():
            if ed.file_path is not None and ed.file_path.suffix.lower() == ".bib":
                try:
                    open_bib_resolved.add(ed.file_path.resolve())
                except OSError:
                    pass
                for item in parse_bib_entries_detailed(ed.toPlainText(), ed.file_path.name):
                    if item["key"] not in seen_keys:
                        seen_keys.add(item["key"])
                        entries.append(item)

        # Leer archivos .bib en disco
        for bib_path in self._find_project_bib_files():
            if bib_path in open_bib_resolved:
                continue
            try:
                content = bib_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for item in parse_bib_entries_detailed(content, bib_path.name):
                if item["key"] not in seen_keys:
                    seen_keys.add(item["key"])
                    entries.append(item)

        self.bib_widget.set_entries(entries)

    def append_bibtex_entry(self, bibtex_text: str) -> pathlib.Path | None:
        entry = bibtex_text.strip()
        if not entry:
            return None

        bib_files = self._find_project_bib_files()
        target_bib: pathlib.Path | None = bib_files[0] if bib_files else None
        if target_bib is None:
            proj_dir = self._active_project_dir()
            if proj_dir is None:
                QMessageBox.information(
                    self,
                    "Guarda tu documento primero",
                    "Guarda el documento en una carpeta de proyecto para crear automáticamente referencias.bib.",
                )
                return None
            target_bib = proj_dir / "referencias.bib"

        try:
            existing = target_bib.read_text(encoding="utf-8") if target_bib.exists() else ""
            sep = "\n\n" if existing.strip() else ""
            new_content = existing.rstrip() + sep + entry + "\n"
            target_bib.write_text(new_content, encoding="utf-8")

            # Si el .bib está abierto en una pestaña, actualizar su contenido también
            tab_idx = self._find_tab_by_path(target_bib)
            if tab_idx >= 0:
                bib_ed = self.editor_tabs.widget(tab_idx)
                if isinstance(bib_ed, CodeEditor):
                    bib_ed.setPlainText(new_content)
                    bib_ed.document().setModified(False)

            self.refresh_bibliography_panel()
            self.statusBar().showMessage(f"Referencia añadida a {target_bib.name}", 3500)
            return target_bib
        except OSError as e:
            QMessageBox.critical(self, "Error al guardar .bib", f"No se pudo escribir en {target_bib.name}:\n{e}")
            return None

    def update_outline(self):
        self.outline_tree.clear()
        LEVELS = {
            "part": 0,
            "chapter": 1,
            "section": 2,
            "subsection": 3,
            "subsubsection": 4,
        }
        sec_pattern = re.compile(r"(?<!\{)\\(part|chapter|section|subsection|subsubsection)\*?\{([^}]*)\}")
        input_pattern = re.compile(r"\\(?:input|include)\{([^}]+)\}")

        stack = []
        anchor = self.master_file or self.opened_file
        base_dir = anchor.parent if anchor is not None else None

        def add_outline_node(title, level, target_path, line_num):
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, (target_path, line_num))
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.outline_tree.addTopLevelItem(item)
            stack.append((level, item))

        def scan_lines(lines, file_path):
            for line_num, line in enumerate(lines, start=1):
                if line.lstrip().startswith("%"):
                    continue
                match = sec_pattern.search(line)
                if match:
                    cmd = match.group(1)
                    title = match.group(2).strip()
                    add_outline_node(title, LEVELS[cmd], file_path, line_num)
                    continue

                in_match = input_pattern.search(line)
                if in_match and base_dir is not None:
                    rel_name = in_match.group(1).strip()
                    sub_path = base_dir / rel_name
                    if sub_path.suffix == "":
                        sub_path = sub_path.with_suffix(".tex")
                    if sub_path.exists():
                        try:
                            sub_lines = sub_path.read_text(encoding="utf-8").splitlines()
                            scan_lines(sub_lines, sub_path)
                        except (OSError, UnicodeDecodeError):
                            add_outline_node(f"📄 {rel_name}", 1, file_path, line_num)
                    else:
                        add_outline_node(f"📄 {rel_name}", 1, file_path, line_num)

        scan_lines(self.ui.editor.toPlainText().splitlines(), self.opened_file)
        if self.outline_tree.topLevelItemCount() == 0:
            empty_item = QTreeWidgetItem(["Sin secciones (\\section{...})"])
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            f = empty_item.font(0)
            f.setItalic(True)
            empty_item.setFont(0, f)
            self.outline_tree.addTopLevelItem(empty_item)
        else:
            self.outline_tree.expandAll()

    def on_outline_item_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        target_path, line_num = data
        if target_path is not None and target_path != self.opened_file and target_path.exists():
            self.load_file(target_path)
        self.current_editor.go_to_line(line_num)

    def update_project_root(self, folder_path: pathlib.Path):
        self._project_root = folder_path
        root_index = self.file_model.setRootPath(str(folder_path))
        self.tree_view.setRootIndex(root_index)
        if hasattr(self, "lbl_project_folder") and self.lbl_project_folder is not None:
            label = "~" if folder_path == pathlib.Path.home() else folder_path.name
            self.lbl_project_folder.setText(label)
            self.lbl_project_folder.setToolTip(str(folder_path))
            self.lbl_project_folder.show()

    def on_tree_double_clicked(self, index):
        if self.file_model.isDir(index):
            return

        path = pathlib.Path(self.file_model.filePath(index))

        if path.suffix.lower() == ".pdf":
            self.ui.pdfView.load_pdf(path)
            self.update_page_count()
            return

        if path.suffix.lower() in (".tex", ".bib", ".sty", ".cls", ".txt"):
            self.load_file(path)

    def open_project_folder(self):
        start_dir = str(self._project_root) if self._project_root is not None else str(pathlib.Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Abrir carpeta de proyecto", start_dir)
        if folder:
            self.update_project_root(pathlib.Path(folder))
            self.statusBar().showMessage(f"Proyecto: {folder}", 3500)

    def set_master_file(self, path: pathlib.Path | None):
        self.master_file = path
        for ed in self.iter_editors():
            self._update_tab_appearance(ed)
        self.update_outline()
        if path is not None:
            self.statusBar().showMessage(f"Archivo maestro establecido: {path.name}", 3500)
        else:
            self.statusBar().showMessage("Archivo maestro restablecido (automático)", 3500)

    def on_project_tree_context_menu(self, pos):
        index = self.tree_view.indexAt(pos)
        clicked_path: pathlib.Path | None = None
        if index.isValid():
            clicked_path = pathlib.Path(self.file_model.filePath(index))

        if clicked_path is not None and clicked_path.is_dir():
            target_dir = clicked_path
        elif clicked_path is not None:
            target_dir = clicked_path.parent
        else:
            target_dir = self._project_root or pathlib.Path.home()

        menu = QMenu(self)

        if clicked_path is not None and clicked_path.is_file():
            ext = clicked_path.suffix.lower()
            if ext in (".tex", ".bib", ".sty", ".cls", ".txt"):
                act_open = menu.addAction("Abrir en pestaña")
                act_open.triggered.connect(lambda checked=False, p=clicked_path: self.load_file(p))
            elif ext == ".pdf":
                act_pdf = menu.addAction("Ver en el visor PDF")
                act_pdf.triggered.connect(lambda checked=False, p=clicked_path: self.ui.pdfView.load_pdf(p))

            if ext == ".tex":
                is_master = (
                    self.master_file is not None
                    and self.master_file.resolve() == clicked_path.resolve()
                )
                if is_master:
                    act_master = menu.addAction("Quitar como archivo maestro")
                    act_master.triggered.connect(lambda checked=False: self.set_master_file(None))
                else:
                    act_master = menu.addAction("Establecer como archivo maestro")
                    act_master.triggered.connect(lambda checked=False, p=clicked_path: self.set_master_file(p))
            menu.addSeparator()

        act_new_file = menu.addAction("Nuevo archivo...")
        act_new_file.triggered.connect(lambda checked=False, d=target_dir: self.create_project_file(d))

        act_new_folder = menu.addAction("Nueva carpeta...")
        act_new_folder.triggered.connect(lambda checked=False, d=target_dir: self.create_project_folder(d))

        if clicked_path is not None:
            menu.addSeparator()
            act_rename = menu.addAction("Renombrar...")
            act_rename.triggered.connect(lambda checked=False, p=clicked_path: self.rename_project_item(p))

            act_delete = menu.addAction("Eliminar...")
            act_delete.triggered.connect(lambda checked=False, p=clicked_path: self.delete_project_item(p))

        menu.addSeparator()
        act_folder = menu.addAction("Abrir carpeta de proyecto...")
        act_folder.triggered.connect(self.open_project_folder)

        act_clean = menu.addAction("Limpiar archivos auxiliares (.tex_builds)")
        act_clean.triggered.connect(lambda checked=False, d=target_dir: self.clean_auxiliary_files(d))

        menu.exec(self.tree_view.viewport().mapToGlobal(pos))

    def create_project_file(self, folder: pathlib.Path, filename: str | None = None) -> pathlib.Path | None:
        if filename is None:
            name, ok = QInputDialog.getText(self, "Nuevo archivo", "Nombre del archivo (p. ej. capitulo1.tex):")
            if not ok or not name.strip():
                return None
            filename = name.strip()
        path = folder / filename
        if path.suffix == "":
            path = path.with_suffix(".tex")
        if path.exists():
            QMessageBox.warning(self, "El archivo ya existe", f"Ya existe «{path.name}» en esta carpeta.")
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            self.load_file(path)
            self.statusBar().showMessage(f"Archivo creado: {path.name}", 3000)
            return path
        except OSError as e:
            QMessageBox.critical(self, "Error al crear archivo", f"No se pudo crear el archivo:\n{e}")
            return None

    def create_project_folder(self, folder: pathlib.Path, dirname: str | None = None) -> pathlib.Path | None:
        if dirname is None:
            name, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
            if not ok or not name.strip():
                return None
            dirname = name.strip()
        target = folder / dirname
        try:
            target.mkdir(parents=True, exist_ok=False)
            self.statusBar().showMessage(f"Carpeta creada: {target.name}", 3000)
            return target
        except OSError as e:
            QMessageBox.critical(self, "Error al crear carpeta", f"No se pudo crear la carpeta:\n{e}")
            return None

    def rename_project_item(self, path: pathlib.Path, new_name: str | None = None) -> pathlib.Path | None:
        if new_name is None:
            name, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=path.name)
            if not ok or not name.strip() or name.strip() == path.name:
                return None
            new_name = name.strip()
        target = path.parent / new_name
        if target.exists():
            QMessageBox.warning(self, "Ya existe", f"Ya existe «{target.name}» en esta carpeta.")
            return None
        try:
            old_resolved = path.resolve()
            path.rename(target)
            # Actualizar pestañas abiertas y master_file si apuntaban al archivo renombrado
            for ed in self.iter_editors():
                if ed.file_path is not None:
                    try:
                        if ed.file_path.resolve() == old_resolved:
                            ed.file_path = target
                            self._update_tab_appearance(ed)
                    except OSError:
                        pass
            if self.master_file is not None:
                try:
                    if self.master_file.resolve() == old_resolved:
                        self.master_file = target
                except OSError:
                    pass
            self.update_title()
            self.statusBar().showMessage(f"Renombrado a {target.name}", 3000)
            return target
        except OSError as e:
            QMessageBox.critical(self, "Error al renombrar", f"No se pudo renombrar:\n{e}")
            return None

    def delete_project_item(self, path: pathlib.Path, confirm: bool = True) -> bool:
        if confirm:
            kind = "la carpeta y todo su contenido" if path.is_dir() else "el archivo"
            ans = QMessageBox.question(
                self,
                "Confirmar eliminación",
                f"¿Seguro que quieres eliminar {kind} «{path.name}»?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False
        try:
            old_resolved = path.resolve()
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            # Cerrar pestaña si estaba abierta (sin preguntar guardar)
            for ed in list(self.iter_editors()):
                if ed.file_path is not None:
                    try:
                        if ed.file_path.resolve() == old_resolved:
                            ed.document().setModified(False)
                            self.close_editor(ed)
                    except OSError:
                        pass
            if self.master_file is not None:
                try:
                    if self.master_file.resolve() == old_resolved:
                        self.master_file = None
                except OSError:
                    pass
            self.statusBar().showMessage(f"Eliminado: {path.name}", 3000)
            return True
        except OSError as e:
            QMessageBox.critical(self, "Error al eliminar", f"No se pudo eliminar:\n{e}")
            return False

    # ------------------------------------------------------------------
    # SyncTeX bidireccional
    # ------------------------------------------------------------------
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
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            file_match = re.search(r"^Input:(.+)$", result.stdout, re.MULTILINE)
            line_match = re.search(r"^Line:(\d+)$", result.stdout, re.MULTILINE)
            if file_match and line_match:
                input_path = pathlib.Path(file_match.group(1).strip()).resolve()
                line_num = int(line_match.group(1))
                if input_path.exists() and input_path != self.opened_file:
                    self.load_file(input_path)
                self.current_editor.go_to_line(line_num)
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
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            page_match = re.search(r"^Page:(\d+)$", result.stdout, re.MULTILINE)
            y_match = re.search(r"^y:([0-9.]+)$", result.stdout, re.MULTILINE)
            h_match = re.search(r"^h:([0-9.]+)$", result.stdout, re.MULTILINE)
            v_match = re.search(r"^v:([0-9.]+)$", result.stdout, re.MULTILINE)
            w_match = re.search(r"^W:([0-9.]+)$", result.stdout, re.MULTILINE)
            H_match = re.search(r"^H:([0-9.]+)$", result.stdout, re.MULTILINE)
            if page_match and y_match:
                page_num = int(page_match.group(1))
                y_pt = float(y_match.group(1))
                box_pt = None
                if h_match and v_match and w_match and H_match:
                    box_pt = (
                        float(h_match.group(1)),
                        float(v_match.group(1)),
                        float(w_match.group(1)),
                        float(H_match.group(1)),
                    )
                if self._view_mode == "editor":
                    self.set_view_mode("split")
                self.ui.pdfView.scroll_to_position(page_num, y_pt, box_pt)
                self.statusBar().showMessage(f"SyncTeX → página {page_num}", 3000)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Archivos recientes
    # ------------------------------------------------------------------
    def add_recent_file(self, path: pathlib.Path):
        path_str = str(path.resolve())
        recent = self.settings.value("recent_files", [], type=list)
        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)
        recent = recent[:10]
        self.settings.setValue("recent_files", recent)
        self.update_recent_files_menu()

    def update_recent_files_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("recent_files", [], type=list)
        valid_files = [p for p in recent if pathlib.Path(p).exists()]

        if not valid_files:
            empty_action = self.recent_menu.addAction("(Sin archivos recientes)")
            empty_action.setEnabled(False)
            return

        for path_str in valid_files:
            p = pathlib.Path(path_str)
            action = self.recent_menu.addAction(f"{p.name} — {p.parent}")
            action.triggered.connect(lambda checked=False, target=p: self.open_recent_file(target))
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Limpiar historial")
        clear_action.triggered.connect(self.clear_recent_files)

    def open_recent_file(self, path: pathlib.Path):
        self.load_file(path)

    def clear_recent_files(self):
        self.settings.setValue("recent_files", [])
        self.update_recent_files_menu()

    # ------------------------------------------------------------------
    # Barra de búsqueda y reemplazo responsive (2 filas, contador, Aa)
    # ------------------------------------------------------------------
    def setup_find_bar(self):
        self.find_bar = QFrame(self)
        self.find_bar.setObjectName("findBar")
        outer = QVBoxLayout(self.find_bar)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(8)

        # Fila 1: Búsqueda
        row_find = QHBoxLayout()
        row_find.setSpacing(8)

        self.btn_toggle_replace = QPushButton(self.find_bar)
        self.btn_toggle_replace.setObjectName("iconBtn")
        self.btn_toggle_replace.setIconSize(QSize(15, 15))
        self.btn_toggle_replace.setCheckable(True)
        self.btn_toggle_replace.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_replace.setAccessibleName("Mostrar u ocultar reemplazo")
        self.btn_toggle_replace.setToolTip("Mostrar / ocultar Reemplazar (Ctrl+H)")
        self.btn_toggle_replace.toggled.connect(self._set_replace_row_visible)

        self.find_input = QLineEdit(self.find_bar)
        self.find_input.setAccessibleName("Texto a buscar")
        self.find_input.setPlaceholderText("Buscar en el documento...")
        self.find_input.setMinimumWidth(140)
        self.find_input.returnPressed.connect(self.find_next)
        self.find_input.textChanged.connect(lambda *_: self._refresh_find_matches())

        self.lbl_match_count = QLabel("", self.find_bar)
        self.lbl_match_count.setObjectName("matchCount")
        self.lbl_match_count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_case = QPushButton("Aa", self.find_bar)
        self.btn_case.setObjectName("iconBtn")
        self.btn_case.setCheckable(True)
        self.btn_case.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_case.setAccessibleName("Distinguir mayúsculas y minúsculas")
        self.btn_case.setToolTip("Distinguir mayúsculas / minúsculas")
        self.btn_case.toggled.connect(lambda *_: self._refresh_find_matches())

        self.btn_regex = QPushButton(".*", self.find_bar)
        self.btn_regex.setObjectName("iconBtn")
        self.btn_regex.setCheckable(True)
        self.btn_regex.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_regex.setAccessibleName("Usar expresiones regulares")
        self.btn_regex.setToolTip("Expresiones regulares (Regex — soporta \\1, \\2 al reemplazar)")
        self.btn_regex.toggled.connect(lambda *_: self._refresh_find_matches())

        self.btn_find_prev = QPushButton(self.find_bar)
        self.btn_find_prev.setObjectName("iconBtn")
        self.btn_find_prev.setIconSize(QSize(14, 14))
        self.btn_find_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_find_prev.setAccessibleName("Coincidencia anterior")
        self.btn_find_prev.setToolTip("Anterior (Shift+Enter)")
        self.btn_find_prev.clicked.connect(self.find_prev)

        self.btn_find_next = QPushButton(self.find_bar)
        self.btn_find_next.setObjectName("iconBtn")
        self.btn_find_next.setIconSize(QSize(14, 14))
        self.btn_find_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_find_next.setAccessibleName("Coincidencia siguiente")
        self.btn_find_next.setToolTip("Siguiente (Enter)")
        self.btn_find_next.clicked.connect(self.find_next)

        self.btn_find_close = QPushButton(self.find_bar)
        self.btn_find_close.setObjectName("iconBtn")
        self.btn_find_close.setIconSize(QSize(14, 14))
        self.btn_find_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_find_close.setAccessibleName("Cerrar barra de búsqueda")
        self.btn_find_close.setToolTip("Cerrar (Esc)")
        self.btn_find_close.clicked.connect(self.hide_find_bar)

        row_find.addWidget(self.btn_toggle_replace)
        row_find.addWidget(self.find_input, 1)
        row_find.addWidget(self.lbl_match_count)
        row_find.addWidget(self.btn_case)
        row_find.addWidget(self.btn_regex)
        row_find.addWidget(self.btn_find_prev)
        row_find.addWidget(self.btn_find_next)
        row_find.addWidget(self.btn_find_close)
        outer.addLayout(row_find)

        # Fila 2: Reemplazo (desplegable para no saturar ni aplastar inputs)
        self.replace_row_widget = QWidget(self.find_bar)
        row_replace = QHBoxLayout(self.replace_row_widget)
        row_replace.setContentsMargins(38, 0, 0, 0)
        row_replace.setSpacing(8)

        self.replace_input = QLineEdit(self.replace_row_widget)
        self.replace_input.setAccessibleName("Texto de reemplazo")
        self.replace_input.setPlaceholderText("Reemplazar con...")
        self.replace_input.setMinimumWidth(140)
        self.replace_input.returnPressed.connect(self.replace_one)

        btn_replace = QPushButton("Reemplazar", self.replace_row_widget)
        btn_replace.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_replace.clicked.connect(self.replace_one)

        btn_replace_all = QPushButton("Reemplazar todo", self.replace_row_widget)
        btn_replace_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_replace_all.clicked.connect(self.replace_all)

        row_replace.addWidget(self.replace_input, 1)
        row_replace.addWidget(btn_replace)
        row_replace.addWidget(btn_replace_all)
        outer.addWidget(self.replace_row_widget)
        self.replace_row_widget.hide()

        self.ui.verticalLayout_3.insertWidget(0, self.find_bar)
        self.find_bar.hide()

        self.action_find = self.ui.menuView.addAction("Buscar")
        self.action_find.setShortcut(QKeySequence.StandardKey.Find)
        self.action_find.triggered.connect(lambda: self.show_find_bar(show_replace=False))

        self.action_replace = self.ui.menuView.addAction("Buscar y reemplazar")
        self.action_replace.setShortcut(QKeySequence("Ctrl+H"))
        self.action_replace.triggered.connect(lambda: self.show_find_bar(show_replace=True))

        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.find_bar)
        self.esc_shortcut.activated.connect(self.hide_find_bar)

    def _set_replace_row_visible(self, visible: bool):
        self.replace_row_widget.setVisible(visible)
        theme_name = getattr(self, "_current_theme", "dark")
        fg = SEMANTIC_TOKENS[theme_name]["text_secondary"]
        self.btn_toggle_replace.setIcon(
            svg_icon("chevron_down" if visible else "chevron_right", fg, 15)
        )

    def _set_find_notfound_state(self, not_found: bool):
        state = "notfound" if not_found else ""
        for w in (self.find_input, self.lbl_match_count):
            if w.property("findState") != state:
                w.setProperty("findState", state)
                w.style().unpolish(w)
                w.style().polish(w)

    def _compile_find_regex(self, query: str):
        flags = 0 if self.btn_case.isChecked() else re.IGNORECASE
        use_regex = self.btn_regex.isChecked()
        if use_regex:
            flags |= re.MULTILINE
        try:
            return re.compile(query if use_regex else re.escape(query), flags)
        except re.error:
            return None

    def _refresh_find_matches(self):
        query = self.find_input.text()
        if not query:
            self.current_editor.set_search_highlights("")
            self.lbl_match_count.setText("")
            self._set_find_notfound_state(False)
            return
        total = self.current_editor.set_search_highlights(
            query,
            case_sensitive=self.btn_case.isChecked(),
            use_regex=self.btn_regex.isChecked(),
        )
        if total == -1:
            self.lbl_match_count.setText("Regex inv.")
            self._set_find_notfound_state(True)
        elif total == 0:
            self.lbl_match_count.setText("0 / 0")
            self._set_find_notfound_state(True)
        else:
            self.lbl_match_count.setText(f"{total} coinc.")
            self._set_find_notfound_state(False)

    def _find_flags(self, backward: bool = False):
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.btn_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def show_find_bar(self, show_replace: bool = False):
        self.find_bar.show()
        if show_replace:
            self.btn_toggle_replace.setChecked(True)
        selected = self.current_editor.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.find_input.setText(selected)
        self._refresh_find_matches()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find_bar(self):
        self.find_bar.hide()
        self.current_editor.set_search_highlights("")
        self.current_editor.setFocus()

    def _select_span(self, start: int, end: int):
        editor = self.current_editor
        c = editor.textCursor()
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(c)
        editor.ensureCursorVisible()

    def find_next(self):
        query = self.find_input.text()
        if not query:
            return
        if self.btn_regex.isChecked():
            pattern = self._compile_find_regex(query)
            if pattern is None:
                self._set_find_notfound_state(True)
                self.statusBar().showMessage("Expresión regular inválida", 3000)
                return
            editor = self.current_editor
            text = editor.toPlainText()
            start_pos = editor.textCursor().selectionEnd()
            m = pattern.search(text, start_pos)
            if m is not None and m.start() == m.end():
                m = pattern.search(text, m.end() + 1) if m.end() + 1 <= len(text) else None
            if m is None:
                m = pattern.search(text, 0)
            if m is not None and m.start() < m.end():
                self._select_span(m.start(), m.end())
                self._set_find_notfound_state(False)
            else:
                self._set_find_notfound_state(True)
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)
            return

        flags = self._find_flags(backward=False)
        if not self.current_editor.find(query, flags):
            cursor = self.current_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.current_editor.setTextCursor(cursor)
            if not self.current_editor.find(query, flags):
                self._set_find_notfound_state(True)
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)

    def find_prev(self):
        query = self.find_input.text()
        if not query:
            return
        if self.btn_regex.isChecked():
            pattern = self._compile_find_regex(query)
            if pattern is None:
                self._set_find_notfound_state(True)
                self.statusBar().showMessage("Expresión regular inválida", 3000)
                return
            editor = self.current_editor
            text = editor.toPlainText()
            anchor = editor.textCursor().selectionStart()
            matches = [m for m in pattern.finditer(text) if m.start() < m.end()]
            if not matches:
                self._set_find_notfound_state(True)
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)
                return
            prev_matches = [m for m in matches if m.start() < anchor]
            target = prev_matches[-1] if prev_matches else matches[-1]
            self._select_span(target.start(), target.end())
            self._set_find_notfound_state(False)
            return

        flags = self._find_flags(backward=True)
        if not self.current_editor.find(query, flags):
            cursor = self.current_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.current_editor.setTextCursor(cursor)
            if not self.current_editor.find(query, flags):
                self._set_find_notfound_state(True)
                self.statusBar().showMessage(f"No se encontró '{query}'", 3000)

    def replace_one(self):
        query = self.find_input.text()
        if not query:
            return
        editor = self.current_editor
        cursor = editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")

        if self.btn_regex.isChecked():
            pattern = self._compile_find_regex(query)
            if pattern is None:
                self._set_find_notfound_state(True)
                return
            if cursor.hasSelection():
                m = pattern.fullmatch(selected)
                if m is not None:
                    try:
                        repl = m.expand(self.replace_input.text())
                    except re.error:
                        repl = self.replace_input.text()
                    cursor.insertText(repl)
                    self._refresh_find_matches()
            self.find_next()
            return

        matched = (
            selected == query
            if self.btn_case.isChecked()
            else selected.lower() == query.lower()
        )
        if cursor.hasSelection() and matched:
            cursor.insertText(self.replace_input.text())
            self._refresh_find_matches()
        self.find_next()

    def replace_all(self):
        query = self.find_input.text()
        if not query:
            return
        replacement = self.replace_input.text()
        editor = self.current_editor

        if self.btn_regex.isChecked():
            pattern = self._compile_find_regex(query)
            if pattern is None:
                self._set_find_notfound_state(True)
                self.statusBar().showMessage("Expresión regular inválida", 3000)
                return
            text = editor.toPlainText()
            matches = [m for m in pattern.finditer(text) if m.start() < m.end()]
            if not matches:
                self.statusBar().showMessage("0 reemplazos realizados", 3000)
                return
            cursor = editor.textCursor()
            cursor.beginEditBlock()
            for m in reversed(matches):
                try:
                    repl = m.expand(replacement)
                except re.error:
                    repl = replacement
                cursor.setPosition(m.start())
                cursor.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(repl)
            cursor.endEditBlock()
            self._refresh_find_matches()
            self.statusBar().showMessage(f"{len(matches)} reemplazos realizados", 3000)
            return

        flags = self._find_flags(backward=False)
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)
        count = 0
        while editor.find(query, flags):
            editor.textCursor().insertText(replacement)
            count += 1
        cursor.endEditBlock()
        self._refresh_find_matches()
        self.statusBar().showMessage(f"{count} reemplazos realizados", 3000)

    # ------------------------------------------------------------------
    # Preferencias, Restauración de sesión y Paleta de comandos (Ctrl+Shift+P)
    # ------------------------------------------------------------------
    def open_preferences(self):
        dlg = PreferencesDialog(self.settings, self._current_theme, self)
        if dlg.exec() == PreferencesDialog.DialogCode.Accepted and dlg.result_prefs:
            self.apply_editor_preferences(dlg.result_prefs)

    def apply_editor_preferences(self, prefs: dict):
        font_family = prefs.get("font_family", self._editor_font.family())
        font_size = int(prefs.get("font_size", self._editor_font.pointSize() or 11))
        self._tab_width = int(prefs.get("tab_width", self._tab_width))
        self._word_wrap = bool(prefs.get("word_wrap", self._word_wrap))
        self._auto_close = bool(prefs.get("auto_close", self._auto_close))
        self._autocompile_ms = int(prefs.get("autocompile_ms", self._autocompile_ms))
        self._restore_session = bool(prefs.get("restore_session", self._restore_session))
        self._autosave_on_blur = bool(prefs.get("autosave_on_blur", self._autosave_on_blur))

        self._editor_font = QFont(font_family, font_size)
        self._editor_font.setStyleHint(QFont.StyleHint.Monospace)
        for ed in self.iter_editors():
            ed.set_tab_width(self._tab_width)
            ed.set_word_wrap(self._word_wrap)
            ed.set_auto_close_enabled(self._auto_close)
            ed.setFont(QFont(self._editor_font))

        self.auto_compiler_timer.setInterval(self._autocompile_ms)
        if "engine" in prefs:
            self.set_compile_engine(prefs["engine"])
        if "shell_escape" in prefs:
            self.set_shell_escape(bool(prefs["shell_escape"]))
        self.statusBar().showMessage("Preferencias guardadas y aplicadas", 3000)

    def save_session_state(self):
        open_paths: list[str] = []
        active_file_str = ""
        cur_ed = self.current_editor
        for ed in self.iter_editors():
            if ed.file_path is not None and ed.file_path.is_file():
                p_str = str(ed.file_path.resolve())
                open_paths.append(p_str)
                if ed is cur_ed:
                    active_file_str = p_str

        self.settings.setValue("session/open_files", open_paths)
        self.settings.setValue("session/active_file", active_file_str)
        self.settings.setValue(
            "session/master_file",
            str(self.master_file.resolve()) if self.master_file is not None and self.master_file.is_file() else "",
        )
        self.settings.setValue(
            "session/project_root",
            str(self._project_root.resolve()) if self._project_root is not None and self._project_root.is_dir() else "",
        )
        self.settings.setValue("session/view_mode", self._view_mode)
        self.settings.setValue("session/window_geometry", self.saveGeometry())

    def restore_session_state(self):
        geo = self.settings.value("session/window_geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass

        saved_root = self.settings.value("session/project_root", "", type=str)
        if saved_root and pathlib.Path(saved_root).is_dir():
            self.update_project_root(pathlib.Path(saved_root))

        saved_files = self.settings.value("session/open_files", [], type=list) or []
        valid_paths = [pathlib.Path(p) for p in saved_files if p and pathlib.Path(p).is_file()]
        for p in valid_paths:
            self.load_file(p)

        saved_master = self.settings.value("session/master_file", "", type=str)
        if saved_master and pathlib.Path(saved_master).is_file():
            self.set_master_file(pathlib.Path(saved_master))

        active_file = self.settings.value("session/active_file", "", type=str)
        if active_file:
            idx = self._find_tab_by_path(pathlib.Path(active_file))
            if idx >= 0:
                self.editor_tabs.setCurrentIndex(idx)

        saved_view = self.settings.value("session/view_mode", "split", type=str)
        if saved_view in ("editor", "split", "pdf"):
            self.set_view_mode(saved_view)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            if getattr(self, "_autosave_on_blur", False):
                for ed in self.iter_editors():
                    if ed.file_path is not None and ed.document().isModified():
                        self.save_to(ed.file_path, editor=ed)

    def _build_palette_commands(self) -> list[PaletteCommand]:
        cmds = [
            # Compilación
            PaletteCommand("Compilar", f"Compilar documento ({self._compile_engine})", self.action_compile_triggered, "F5", "build latexmk pdf"),
            PaletteCommand("Compilar", "Detener compilación en curso", self.stop_compilation, "Shift+F5", "stop cancelar abortar"),
            PaletteCommand("Compilar", "Ir al PDF desde el cursor (SyncTeX)", self.sync_code_to_pdf, "Ctrl+Shift+J", "synctex saltar"),
            PaletteCommand("Compilar", "Cambiar motor a LuaLaTeX", lambda: self.set_compile_engine("LuaLaTeX"), "", "motor engine lualatex"),
            PaletteCommand("Compilar", "Cambiar motor a pdfLaTeX", lambda: self.set_compile_engine("pdfLaTeX"), "", "motor engine pdflatex"),
            PaletteCommand("Compilar", "Cambiar motor a XeLaTeX", lambda: self.set_compile_engine("XeLaTeX"), "", "motor engine xelatex"),
            PaletteCommand("Compilar", "Alternar --shell-escape (minted / svg)", lambda: self.set_shell_escape(not self._shell_escape), "", "shell escape minted"),
            PaletteCommand("Compilar", "Limpiar archivos auxiliares (.tex_builds)", self.clean_auxiliary_files, "", "clean aux borrar temporales"),
            # Archivo
            PaletteCommand("Archivo", "Nueva pestaña (documento por defecto)", self.action_new_triggered, "Ctrl+N", "nuevo crear"),
            PaletteCommand("Archivo", "Abrir archivo...", self.action_open_triggered, "Ctrl+O", "open tex bib"),
            PaletteCommand("Archivo", "Abrir carpeta de proyecto...", self.open_project_folder, "", "folder directorio workspace"),
            PaletteCommand("Archivo", "Guardar documento actual", self.action_save_triggered, "Ctrl+S", "save"),
            PaletteCommand("Archivo", "Guardar todas las pestañas", self.save_all_tabs, "Ctrl+Alt+S", "save all"),
            PaletteCommand("Archivo", "Cerrar pestaña actual", lambda: self.close_tab(self.editor_tabs.currentIndex()), "Ctrl+W", "close tab"),
            PaletteCommand("Archivo", "Exportar PDF como...", self.export_pdf_as, "", "guardar exportar"),
            PaletteCommand("Archivo", "Exportar proyecto (.zip)...", self.export_project_zip, "", "comprimir zip backup"),
            PaletteCommand("Archivo", "Abrir Preferencias...", self.open_preferences, "Ctrl+,", "ajustes configuracion settings"),
            # Herramientas visuales
            PaletteCommand("Herramientas", "Generador visual de tablas...", self.open_table_generator, "Ctrl+Shift+T", "tabla tabular booktabs csv excel"),
            PaletteCommand("Herramientas", "Mostrar / ocultar Paleta de símbolos", lambda: self.symbols_dock.setVisible(not self.symbols_dock.isVisible()), "Ctrl+Shift+Y", "simbolos griego math sigma"),
            PaletteCommand("Herramientas", "Mostrar / ocultar Gestor de bibliografía (.bib)", self.toggle_bibliography_dock, "Ctrl+Shift+B", "bib citas doi referencias"),
            PaletteCommand("Herramientas", "Previsualizar fórmula / TikZ actual", lambda: self.trigger_math_preview(force=True), "Ctrl+Shift+M", "ecuacion preview math tikz"),
            PaletteCommand("Herramientas", "Alternar previsualización automática de fórmulas", lambda: self.action_math_preview_auto.setChecked(not self.action_math_preview_auto.isChecked()), "", "ecuacion preview auto"),
            # Edición y búsqueda
            PaletteCommand("Edición", "Buscar en el documento", lambda: self.show_find_bar(False), "Ctrl+F", "find regex"),
            PaletteCommand("Edición", "Buscar y reemplazar (soporta Regex)", lambda: self.show_find_bar(True), "Ctrl+H", "replace regex"),
            PaletteCommand("Edición", "Comentar / Descomentar selección", lambda: self.current_editor.toggle_comment(), "Ctrl+/", "comentario %"),
            PaletteCommand("Edición", "Negrita (\\textbf)", lambda: self.current_editor.wrap_selection(r"\textbf{", "}"), "Ctrl+B", "bold formato"),
            PaletteCommand("Edición", "Cursiva (\\textit)", lambda: self.current_editor.wrap_selection(r"\textit{", "}"), "Ctrl+I", "italic formato"),
            PaletteCommand("Edición", "Modo matemático ($...$)", lambda: self.current_editor.wrap_selection("$", "$"), "Ctrl+M", "math ecuacion"),
            # Visor PDF y vista
            PaletteCommand("Vista", "Buscar texto dentro del PDF", self._open_pdf_search, "Ctrl+Shift+F", "pdf find"),
            PaletteCommand("Vista", "Ajustar PDF al ancho", self.ui.pdfView.fit_width, "Ctrl+0", "zoom fit"),
            PaletteCommand("Vista", "Ajustar PDF a página completa", self.ui.pdfView.fit_page, "", "zoom fit page"),
            PaletteCommand("Vista", "Alternar vista de doble página (PDF)", lambda: self.ui.pdfView.set_two_page_mode(not self.ui.pdfView.two_page_mode), "", "libro book spread"),
            PaletteCommand("Vista", "Rotar PDF 90°", self.ui.pdfView.rotate_cw, "", "girar rotacion"),
            PaletteCommand("Vista", "Alternar PDF en Modo Noche", lambda: self.action_dark_pdf.setChecked(not self.action_dark_pdf.isChecked()), "Ctrl+Shift+D", "oscuro invert"),
            PaletteCommand("Vista", "Alternar Tema Oscuro / Claro", self._toggle_theme_action, "", "dark light theme"),
            PaletteCommand("Vista", "Modo Solo Código", lambda: self.set_view_mode("editor"), "Ctrl+1", "layout vista"),
            PaletteCommand("Vista", "Modo Vista Dividida (Código + PDF)", lambda: self.set_view_mode("split"), "Ctrl+2", "layout vista"),
            PaletteCommand("Vista", "Modo Solo PDF", lambda: self.set_view_mode("pdf"), "Ctrl+3", "layout vista"),
            PaletteCommand("Vista", "Mostrar / ocultar panel de salida (Log)", lambda: self.set_log_visible(not self._log_visible), "Ctrl+J", "registro consola"),
            # Selene IA
            PaletteCommand("Selene IA", "Abrir / cerrar Asistente Selene IA", self.toggle_ai_bubble, "Ctrl+Shift+A", "chat ai asistente"),
            PaletteCommand("Selene IA", "Imagen del portapapeles a LaTeX (OCR)", self.ocr_clipboard_image_with_ai, "Ctrl+Alt+V", "captura foto ecuacion"),
            PaletteCommand("Selene IA", "Arreglar último error de compilación con IA", self._open_ai_and_fix_error, "", "debug fix log"),
            PaletteCommand("Selene IA", "Configurar proveedor y API Key de IA...", self.open_ai_settings, "", "gemini ollama openai"),
            # Ayuda y diagnóstico
            PaletteCommand("Ayuda", "Comprobar entorno LaTeX (latexmk, lualatex, synctex)...", self.open_environment_check, "", "diagnostico instalar texlive miktex"),
            PaletteCommand("Ayuda", "Acerca de SeleneTeX...", self.open_about_dialog, "", "version licencia info"),
        ]
        # Añadir todas las plantillas disponibles
        for tmpl_name in TEMPLATES:
            cmds.append(
                PaletteCommand(
                    "Plantilla",
                    f"Nuevo desde plantilla: {tmpl_name}",
                    lambda t=tmpl_name: self.new_from_template(t),
                    "",
                    f"template nuevo {tmpl_name}",
                )
            )
        return cmds

    def open_command_palette(self):
        dlg = CommandPaletteDialog(self._build_palette_commands(), self._current_theme, self)
        dlg.position_over_parent(self)
        if dlg.exec() == CommandPaletteDialog.DialogCode.Accepted and dlg.selected_command is not None:
            dlg.selected_command.callback()

    def open_environment_check(self):
        dlg = EnvironmentCheckDialog(self._current_theme, self)
        dlg.exec()

    def open_about_dialog(self):
        dlg = AboutDialog(ICON_PATH, self._current_theme, self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Plantillas y cierre
    # ------------------------------------------------------------------
    def new_from_template(self, template_name: str):
        content = TEMPLATES[template_name]
        cur = self.current_editor
        if self._is_reusable_empty_tab(cur):
            cur.setPlainText(content)
            cur.document().setModified(False)
            cur.file_path = None
            cur.clear_diagnostics()
            self._update_tab_appearance(cur)
        else:
            self._create_editor_tab(file_path=None, content=content, activate=True)

        self.update_title()
        self.update_outline()
        self.update_page_count()
        self.update_word_count()
        self.update_cursor_status()
        self.current_editor.setFocus()

    def closeEvent(self, event: QCloseEvent):
        for editor in list(self.iter_editors()):
            if editor.document().isModified():
                self.editor_tabs.setCurrentWidget(editor)
                if not self.maybe_save(editor):
                    event.ignore()
                    return
        if getattr(self, "ai_worker", None) is not None and self.ai_worker.isRunning():
            self.ai_worker.cancel()
        self.save_session_state()
        event.accept()

    # ------------------------------------------------------------------
    # Barra de estado plana estilo IDE moderno (sin 6 cajas con borde)
    # ------------------------------------------------------------------
    def _make_status_sep(self) -> QFrame:
        sep = QFrame(self)
        sep.setObjectName("statusSep")
        sep.setFixedHeight(14)
        return sep

    def setup_status_bar(self):
        self.btn_status_log = QPushButton(" Registro", self)
        self.btn_status_log.setObjectName("statusToggleBtn")
        self.btn_status_log.setIconSize(QSize(13, 13))
        self.btn_status_log.setCheckable(True)
        self.btn_status_log.setChecked(True)
        self.btn_status_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_status_log.setToolTip("Mostrar u ocultar panel de salida (Ctrl+J)")
        self.btn_status_log.toggled.connect(self.set_log_visible)
        self.statusBar().addPermanentWidget(self.btn_status_log)

        self.lbl_status = QLabel("● Listo", self)
        self.lbl_status.setObjectName("statusBadge")
        self.statusBar().addPermanentWidget(self.lbl_status)

        self.btn_engine = QPushButton(self._compile_engine, self)
        self.btn_engine.setObjectName("statusToggleBtn")
        self.btn_engine.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_engine.setToolTip("Cambiar motor de compilación (LuaLaTeX / pdfLaTeX / XeLaTeX)")
        self.btn_engine.clicked.connect(self._show_engine_selector_menu)
        self._refresh_engine_indicators()

        self.lbl_pages = QLabel("0 págs", self)
        self.lbl_pages.setObjectName("statusText")
        self.lbl_words = QLabel("0 palabras", self)
        self.lbl_words.setObjectName("statusText")
        self.lbl_cursor = QLabel("Ln 1, Col 1", self)
        self.lbl_cursor.setObjectName("statusMono")
        self.lbl_cursor.setMinimumWidth(92)
        self.lbl_cursor.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for lbl in (self.btn_engine, self.lbl_pages, self.lbl_words, self.lbl_cursor):
            self.statusBar().addPermanentWidget(self._make_status_sep())
            self.statusBar().addPermanentWidget(lbl)

        self._set_compile_status("ok", "Listo")

    def _show_engine_selector_menu(self):
        menu = QMenu(self)
        for eng_name in LATEX_ENGINES:
            act = menu.addAction(eng_name)
            act.setCheckable(True)
            act.setChecked(eng_name == self._compile_engine)
            act.triggered.connect(lambda checked=False, e=eng_name: self.set_compile_engine(e))
        menu.addSeparator()
        act_se = menu.addAction("Habilitar --shell-escape")
        act_se.setCheckable(True)
        act_se.setChecked(self._shell_escape)
        act_se.toggled.connect(self.set_shell_escape)
        pos = self.btn_engine.mapToGlobal(self.btn_engine.rect().topLeft())
        menu.exec(pos)

    def _set_compile_status(self, state: str, text: str):
        if not hasattr(self, "lbl_status"):
            return
        colors = {
            "ok": "#34d399",
            "compiling": "#38bdf8",
            "stopped": "#fbbf24",
            "error": "#f87171",
        }
        dot_color = colors.get(state, "#94a3b8")
        self.lbl_status.setText(f"<span style='color:{dot_color};'>●</span> {text}")

    def update_cursor_status(self):
        cursor = self.ui.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self.lbl_cursor.setText(f"Ln {line}, Col {col}")

    def update_word_count(self):
        text = self.ui.editor.toPlainText()
        if r"\begin{document}" in text:
            text = text.split(r"\begin{document}", 1)[1]
        text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
        words = re.findall(r"\b[^\W\d_]+\b", text)
        n = len(words)
        self.lbl_words.setText(f"{n} {'palabra' if n == 1 else 'palabras'}")

    def update_page_count(self):
        count = self.ui.pdfView.page_count()
        self.lbl_pages.setText(f"{count} {'pág' if count == 1 else 'págs'}")

    def on_file_dropped(self, file_path: str):
        path = pathlib.Path(file_path)
        ext = path.suffix.lower()

        if ext in (".tex", ".bib", ".sty", ".cls"):
            self.load_file(path)
            return

        if ext in (".png", ".jpg", ".jpeg", ".pdf", ".eps"):
            anchor = self.master_file or self.opened_file
            if anchor is not None:
                try:
                    rel_path = path.relative_to(anchor.parent).as_posix()
                except ValueError:
                    rel_path = path.as_posix()
            else:
                rel_path = path.as_posix()

            label_name = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)
            snippet = (
                "\\begin{figure}[htbp]\n"
                "    \\centering\n"
                f"    \\includegraphics[width=0.8\\textwidth]{{{rel_path}}}\n"
                f"    \\caption{{{path.stem}}}\n"
                f"    \\label{{fig:{label_name}}}\n"
                "\\end{figure}\n"
            )
            self.ui.editor.textCursor().insertText(snippet)
            self.statusBar().showMessage(f"Figura insertada: {rel_path}", 3000)

    # ------------------------------------------------------------------
    # Mascota y burbuja Selene IA adaptativa (multi-turno + Imagen a LaTeX)
    # ------------------------------------------------------------------
    def setup_ai_mascot(self):
        self.ai_worker = None
        self.ai_history: list[dict] = []
        self._pending_ai_user_turn: str = ""
        self._last_ai_request: tuple[str, str | None] | None = None
        self.mascot = SeleneMascot(self.ui.centralwidget)
        self.ai_bubble = QuickAIBubble(self.ui.centralwidget)
        self.ai_bubble.set_theme(getattr(self, "_current_theme", "dark"))

        self.mascot.clicked.connect(self.toggle_ai_bubble)
        self.ai_bubble.prompt_submitted.connect(self.send_ai_prompt)
        self.ai_bubble.fix_error_requested.connect(self.fix_log_error_with_ai)
        self.ai_bubble.insert_code_requested.connect(self.insert_ai_code)
        self.ai_bubble.replace_code_requested.connect(self.replace_ai_code)
        self.ai_bubble.add_packages_requested.connect(self.add_packages_to_preamble)
        self.ai_bubble.new_chat_requested.connect(self.reset_ai_history)
        self.ai_bubble.settings_requested.connect(self.open_ai_settings)
        self.ai_bubble.stop_requested.connect(self.stop_ai_generation)
        self.ai_bubble.retry_requested.connect(self.retry_last_ai_prompt)
        self.ai_bubble.expand_toggled.connect(lambda *_: self.position_mascot())
        self.ai_bubble.closed.connect(lambda: self.current_editor.setFocus())

        self.ui.main_splitter.splitterMoved.connect(lambda *_: self.position_mascot())
        self.ui.top_splitter.splitterMoved.connect(lambda *_: (self.position_mascot(), self.position_math_preview()))

        self.ui.menuView.addSeparator()
        act_ai = self.ui.menuView.addAction("Asistente Selene IA")
        act_ai.setShortcut("Ctrl+Shift+A")
        act_ai.triggered.connect(self.toggle_ai_bubble)

        act_ai_ocr = self.ui.menuView.addAction("Imagen del portapapeles a LaTeX (Selene IA)")
        act_ai_ocr.setShortcut("Ctrl+Alt+V")
        act_ai_ocr.triggered.connect(self.ocr_clipboard_image_with_ai)

        act_ai_cfg = self.ui.menuView.addAction("Configurar IA...")
        act_ai_cfg.triggered.connect(self.open_ai_settings)

        QTimer.singleShot(0, self.position_mascot)

    def _sync_ai_selection_state(self, editor: CodeEditor):
        if editor is self.current_editor and hasattr(self, "ai_bubble"):
            self.ai_bubble.set_has_editor_selection(editor.textCursor().hasSelection())

    def reset_ai_history(self):
        self.ai_history.clear()
        self._pending_ai_user_turn = ""
        self._last_ai_request = None
        self.statusBar().showMessage("Nueva conversación iniciada en Selene IA", 2500)

    def _ensure_ai_bubble_open(self):
        if not self.ai_bubble.isVisible():
            self.position_mascot()
            self.ai_bubble.show()
            self.ai_bubble.raise_()

    def on_editor_ai_action(self, kind: str, prompt: str):
        self._ensure_ai_bubble_open()
        if kind == "open":
            self.ai_bubble.input.setFocus()
            return
        if kind == "ocr_clipboard":
            self.ocr_clipboard_image_with_ai()
            return
        if kind == "prompt" and prompt:
            self.ai_bubble.add_user_message(prompt)
            self.send_ai_prompt(prompt)

    def ocr_clipboard_image_with_ai(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData() if clipboard is not None else None
        if mime is None or not mime.hasImage():
            self._ensure_ai_bubble_open()
            self.ai_bubble.set_response(
                "No hay ninguna imagen en el portapapeles. Copia una captura de pantalla y vuelve a pulsar Ctrl+Alt+V (o pégala con Ctrl+V dentro del asistente).",
                is_error=True,
            )
            return
        img = clipboard.image()
        if img.isNull():
            return
        self._ensure_ai_bubble_open()
        if self.ai_bubble.attach_qimage(img, "Captura del portapapeles"):
            image_url = self.ai_bubble._pending_image_data_url
            image_label = self.ai_bubble._pending_image_label
            self.ai_bubble.clear_attached_image()
            self.ai_bubble.add_user_message(DEFAULT_OCR_PROMPT, image_label=image_label)
            self.send_ai_prompt(DEFAULT_OCR_PROMPT, image_data_url=image_url)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(self.width())
        if hasattr(self, "mascot"):
            self.position_mascot()
        if hasattr(self, "math_preview"):
            self.position_math_preview()

    # ------------------------------------------------------------------
    # Previsualización rápida en vivo de fórmulas y diagramas TikZ
    # ------------------------------------------------------------------
    def setup_math_preview(self):
        self._math_preview_auto = self.settings.value("editor/math_preview_auto", True, type=bool)
        self._math_preview_req_id = 0
        self._math_preview_worker: MathRenderWorker | None = None
        self._math_preview_last_key: tuple[str, str] | None = None
        self._math_preview_dismissed_snippet: str | None = None
        self._math_preview_kind_label = "Fórmula"

        self.math_preview = MathPreviewPopup(self.editor_tabs)
        self.math_preview.set_theme(self._current_theme)
        self.math_preview.dismissed.connect(self._on_math_preview_dismissed)

        self._math_preview_timer = QTimer(self)
        self._math_preview_timer.setSingleShot(True)
        self._math_preview_timer.setInterval(550)
        self._math_preview_timer.timeout.connect(lambda: self.trigger_math_preview(force=False))

        self.ui.menuView.addSeparator()
        act_preview_now = self.ui.menuView.addAction("Previsualizar fórmula / TikZ")
        act_preview_now.setShortcut("Ctrl+Shift+M")
        act_preview_now.triggered.connect(lambda: self.trigger_math_preview(force=True))

        self.action_math_preview_auto = self.ui.menuView.addAction("Previsualización automática de fórmulas")
        self.action_math_preview_auto.setCheckable(True)
        self.action_math_preview_auto.setChecked(self._math_preview_auto)
        self.action_math_preview_auto.toggled.connect(self._toggle_math_preview_auto)

    def _toggle_math_preview_auto(self, enabled: bool):
        self._math_preview_auto = bool(enabled)
        self.settings.setValue("editor/math_preview_auto", self._math_preview_auto)
        if not self._math_preview_auto:
            self._math_preview_timer.stop()
            self.math_preview.hide()

    def _on_math_preview_dismissed(self):
        editor = self.current_editor
        cur = editor.textCursor()
        found = extract_math_at_cursor(editor.toPlainText(), cur.position(), cur.selectedText())
        self._math_preview_dismissed_snippet = found[0] if found else None

    def _schedule_math_preview(self):
        if not hasattr(self, "math_preview"):
            return
        editor = self.current_editor
        cur = editor.textCursor()
        found = extract_math_at_cursor(editor.toPlainText(), cur.position(), cur.selectedText())
        if found is None:
            self._math_preview_timer.stop()
            self._math_preview_last_key = None
            self._math_preview_dismissed_snippet = None
            if self.math_preview.isVisible():
                self.math_preview.hide()
            return
        if found[0] == self._math_preview_dismissed_snippet:
            return
        self._math_preview_timer.start()

    def position_math_preview(self):
        if not hasattr(self, "math_preview") or not self.math_preview.isVisible():
            return
        tb_h = self.editor_tabs.tabBar().height() if self.editor_tabs.tabBar() else 32
        x = max(12, self.editor_tabs.width() - self.math_preview.width() - 16)
        y = tb_h + 12
        self.math_preview.move(x, y)
        self.math_preview.raise_()

    def trigger_math_preview(self, force: bool = False):
        if not hasattr(self, "math_preview"):
            return
        editor = self.current_editor
        doc_text = editor.toPlainText()
        cur = editor.textCursor()
        found = extract_math_at_cursor(doc_text, cur.position(), cur.selectedText())
        if found is None:
            if force:
                self.statusBar().showMessage(
                    "Coloca el cursor dentro de una fórmula ($...$, \\[...\\], equation, align, tikzpicture) o selecciónala",
                    3500,
                )
            self.math_preview.hide()
            return

        snippet, kind_label = found
        if force:
            self._math_preview_dismissed_snippet = None
        elif snippet == self._math_preview_dismissed_snippet:
            return

        extra_preamble = extract_safe_math_preamble(doc_text, snippet)
        tex_source = build_standalone_tex(snippet, extra_preamble)
        cache_key, cached_pm = get_cached_preview(tex_source, self._current_theme)

        if not force and cache_key == self._math_preview_last_key and self.math_preview.isVisible():
            return

        self._math_preview_last_key = cache_key
        self._math_preview_kind_label = kind_label

        if cached_pm is not None:
            self.math_preview.show_pixmap(kind_label, cached_pm)
            self.position_math_preview()
            return

        self._math_preview_req_id += 1
        req_id = self._math_preview_req_id
        self.math_preview.show_loading(kind_label)
        self.position_math_preview()

        dpr = max(1.0, min(2.5, float(self.devicePixelRatioF() or 1.0)))
        worker = MathRenderWorker(
            req_id,
            tex_source,
            cache_key,
            dark_mode=(self._current_theme == "dark"),
            dpr=dpr,
            parent=self,
        )
        worker.rendered.connect(self._on_math_preview_rendered)
        worker.failed.connect(self._on_math_preview_failed)
        self._math_preview_worker = worker
        worker.start()

    def _on_math_preview_rendered(self, req_id: int, pixmap: QPixmap):
        if req_id != self._math_preview_req_id:
            return
        self.math_preview.show_pixmap(self._math_preview_kind_label, pixmap)
        self.position_math_preview()

    def _on_math_preview_failed(self, req_id: int, message: str):
        if req_id != self._math_preview_req_id:
            return
        self.math_preview.show_error(self._math_preview_kind_label, message)
        self.position_math_preview()

    def position_mascot(self):
        cw = self.ui.centralwidget

        mx = cw.width() - self.mascot.width() - 10
        if self.log_container.isVisible():
            log_tr = self.log_container.mapTo(cw, self.log_container.rect().topRight())
            # Posado sobre el borde superior del panel de log, sin tapar el botón ✕ de su cabecera
            my = log_tr.y() - 45
        else:
            my = cw.height() - self.mascot.height() - 12

        mx = max(8, mx)
        my = max(8, min(my, cw.height() - self.mascot.height() - 8))
        self.mascot.move(mx, my)
        self.mascot.raise_()

        max_bubble_h = max(240, my - 20)
        self.ai_bubble.adapt_to_parent(cw.width(), cw.height(), max_height=max_bubble_h)

        bx = cw.width() - self.ai_bubble.width() - 12
        by = my - self.ai_bubble.height() - 8
        bx = max(12, bx)
        by = max(12, min(by, max(12, my - self.ai_bubble.height() - 6)))
        self.ai_bubble.move(bx, by)
        if self.ai_bubble.isVisible():
            self.ai_bubble.raise_()

    def toggle_ai_bubble(self):
        if self.ai_bubble.isVisible():
            self.ai_bubble.close_bubble()
        else:
            self.position_mascot()
            self.ai_bubble.set_has_editor_selection(self.current_editor.textCursor().hasSelection())
            self.ai_bubble.show()
            self.ai_bubble.raise_()
            self.ai_bubble.input.setFocus()

    def open_ai_settings(self):
        dlg = AISettingsDialog(self.settings, self)
        dlg.exec()

    def _extract_custom_macros(self, text: str, max_macros: int = 15) -> list[str]:
        macros: list[str] = []
        seen: set[str] = set()
        macro_re = re.compile(
            r"^[ \t]*(\\(?:re)?newcommand\*?|\\providecommand\*?|\\DeclareMathOperator\*?)\s*"
            r"\{?(\\[A-Za-z@]+)\}?(?:\[\d+\](?:\[[^\]]*\])?)?\s*\{([^\n]{1,90})\}",
            re.MULTILINE,
        )
        for m in macro_re.finditer(text):
            cmd_name = m.group(2)
            if cmd_name in seen:
                continue
            seen.add(cmd_name)
            macros.append(f"{cmd_name} -> {m.group(3).strip()}")
            if len(macros) >= max_macros:
                break
        return macros

    def _build_ai_doc_context(self) -> str:
        editor = self.current_editor
        text = editor.toPlainText()
        file_label = self.opened_file.name if self.opened_file else "Sin título (.tex)"
        line_num = editor.textCursor().blockNumber() + 1
        parts = [
            f"- Archivo abierto: {file_label} (cursor en línea {line_num})",
            f"- Motor de compilación activo: {self._compile_engine}" + (" (--shell-escape)" if self._shell_escape else ""),
        ]
        if self.master_file and self.master_file != self.opened_file:
            parts.append(f"- Archivo maestro: {self.master_file.name}")

        if hasattr(self, "ai_bubble") and not self.ai_bubble.include_doc_context():
            return "\n".join(parts)

        pkgs = extract_document_packages(text)
        if pkgs:
            parts.append(f"- Clase y paquetes cargados: {', '.join(pkgs)}")

        macros = self._extract_custom_macros(text)
        if macros:
            parts.append("- Macros personalizadas definidas: " + "; ".join(macros))

        proj_ctx = self._get_editor_project_context()
        labels = list(collect_project_labels(text, proj_ctx["open_texts"], proj_ctx["base_dir"]).keys())
        if labels:
            shown = labels[:25]
            suffix = f" (+{len(labels) - 25} más)" if len(labels) > 25 else ""
            parts.append(f"- Etiquetas \\label disponibles: {', '.join(shown)}{suffix}")

        cites = list(collect_project_citations(text, proj_ctx["open_texts"], proj_ctx["base_dir"]).keys())
        if cites:
            shown = cites[:25]
            suffix = f" (+{len(cites) - 25} más)" if len(cites) > 25 else ""
            parts.append(f"- Claves bibliográficas \\cite disponibles: {', '.join(shown)}{suffix}")

        # Ventana de código ±20 líneas alrededor del cursor para dar contexto real sin desperdiciar tokens
        lines = text.splitlines()
        if lines:
            start = max(0, line_num - 21)
            end = min(len(lines), line_num + 20)
            numbered: list[str] = []
            for idx in range(start, end):
                marker = "  <<< CURSOR" if (idx + 1) == line_num else ""
                numbered.append(f"{idx + 1:>4}: {lines[idx]}{marker}")
            snippet = "\n".join(numbered)
            if len(snippet) > 3200:
                snippet = snippet[:3200] + "\n... [recortado]"
            parts.append(f"- Código alrededor del cursor (líneas {start + 1}-{end}):\n```latex\n{snippet}\n```")

        return "\n".join(parts)

    def send_ai_prompt(self, prompt: str, image_data_url: str | None = None):
        if self.ai_worker is not None and self.ai_worker.isRunning():
            return
        self._last_ai_request = (prompt, image_data_url)
        full_prompt = prompt
        selected = self.current_editor.textCursor().selectedText().replace("\u2029", "\n")
        if selected and not image_data_url:
            full_prompt = f"{prompt}\n\nTexto seleccionado en el editor:\n```latex\n{selected}\n```"
        doc_context = self._build_ai_doc_context()
        self._pending_ai_user_turn = f"[Imagen adjunta] {full_prompt}" if image_data_url else full_prompt
        self.mascot.set_state("thinking")
        self.ai_bubble.set_busy(True)
        self.ai_worker = AIWorker(
            full_prompt,
            self.settings,
            self,
            doc_context=doc_context,
            history=self.ai_history,
            image_data_url=image_data_url,
        )
        self.ai_worker.chunk_received.connect(self.ai_bubble.append_chunk)
        self.ai_worker.response_ready.connect(self.on_ai_response)
        self.ai_worker.error_occurred.connect(self.on_ai_error)
        self.ai_worker.cancelled.connect(self.on_ai_cancelled)
        self.ai_worker.start()

    def stop_ai_generation(self):
        if self.ai_worker is not None and self.ai_worker.isRunning():
            self.ai_worker.cancel()
            self.statusBar().showMessage("Deteniendo generación de Selene IA...", 2000)

    def on_ai_cancelled(self, partial_text: str):
        self._pending_ai_user_turn = ""
        self.mascot.set_state("idle")
        self.ai_bubble.set_busy(False)
        if partial_text.strip():
            self.ai_bubble.set_response(
                partial_text + "\n\n_(Generación detenida por el usuario)_",
                is_error=False,
            )
        else:
            self.ai_bubble.set_response("Generación detenida por el usuario.", is_error=False)
        self.statusBar().showMessage("Generación de IA detenida", 2500)

    def retry_last_ai_prompt(self):
        if not self._last_ai_request:
            return
        if self.ai_worker is not None and self.ai_worker.isRunning():
            return
        prompt, image_url = self._last_ai_request
        self.send_ai_prompt(prompt, image_data_url=image_url)

    def _extract_targeted_error_code(self, log_text: str, full_text: str) -> str:
        lines = full_text.splitlines()
        if not lines:
            return ""

        error_lines: list[int] = []
        for pattern in (r"\.tex:(\d+):", r"^l\.(\d+)\b", r"on input line (\d+)"):
            for m in re.finditer(pattern, log_text, re.MULTILINE):
                ln = int(m.group(1))
                if 1 <= ln <= len(lines) and ln not in error_lines:
                    error_lines.append(ln)

        # Preámbulo (hasta \begin{document}, máx 50 líneas)
        preamble_end = 0
        for i, line in enumerate(lines[:60]):
            if r"\begin{document}" in line:
                preamble_end = i + 1
                break
        sections: list[str] = []
        if preamble_end > 0:
            pre_chunk = "\n".join(f"{i + 1:>4}: {lines[i]}" for i in range(preamble_end))
            sections.append(f"% --- Preámbulo (líneas 1-{preamble_end}) ---\n{pre_chunk}")

        if error_lines:
            for ln in error_lines[:3]:
                start = max(preamble_end, ln - 18)
                end = min(len(lines), ln + 18)
                if start >= end:
                    start = max(0, ln - 18)
                chunk = "\n".join(
                    f"{i + 1:>4}: {lines[i]}" + ("  <<< ERROR" if (i + 1) == ln else "")
                    for i in range(start, end)
                )
                sections.append(f"% --- Contexto del error en línea {ln} ---\n{chunk}")
            return "\n\n".join(sections)[:4500]

        # Sin número de línea en el log: enviar el principio del documento (hasta 4000 chars)
        return full_text[:4000]

    def fix_log_error_with_ai(self):
        log_text = self.ui.logView.toPlainText().strip()
        if not log_text:
            self.ai_bubble.set_response(
                "No hay salida en el log todavía. Compila primero con F5.",
                is_error=True,
            )
            return
        code_snippet = self._extract_targeted_error_code(log_text, self.current_editor.toPlainText())
        prompt = (
            f"Analiza este error de compilación de {self._compile_engine} y dime cómo corregirlo:\n\n"
            f"LOG (últimas líneas):\n{log_text[-2000:]}\n\n"
            f"CÓDIGO RELEVANTE:\n```latex\n{code_snippet}\n```"
        )
        self.ai_bubble.add_user_message("Arreglar error del último log de compilación")
        self.send_ai_prompt(prompt)

    def on_ai_response(self, text: str):
        if self._pending_ai_user_turn and text.strip():
            self.ai_history.append({"role": "user", "content": self._pending_ai_user_turn})
            self.ai_history.append({"role": "assistant", "content": text})
            if len(self.ai_history) > 20:
                self.ai_history = self.ai_history[-20:]
        self._pending_ai_user_turn = ""

        self.mascot.set_state("happy")
        self.ai_bubble.set_busy(False)
        self.ai_bubble.set_response(text, is_error=False)

        # Detectar paquetes sugeridos que faltan en el preámbulo del documento
        existing_pkgs = extract_document_packages(self.current_editor.toPlainText())
        if self.master_file is not None and self.master_file != self.opened_file:
            master_idx = self._find_tab_by_path(self.master_file)
            if master_idx >= 0:
                master_ed = self.editor_tabs.widget(master_idx)
                if isinstance(master_ed, CodeEditor):
                    existing_pkgs.extend(extract_document_packages(master_ed.toPlainText()))
        missing = extract_recommended_packages(text, existing_pkgs)
        self.ai_bubble.set_recommended_packages(missing)

    def on_ai_error(self, msg: str):
        self._pending_ai_user_turn = ""
        self.mascot.set_state("idle")
        self.ai_bubble.set_busy(False)
        self.ai_bubble.set_response(f"⚠ {msg}", is_error=True)

    def insert_ai_code(self, code: str):
        self.current_editor.textCursor().insertText(code)
        self.current_editor.setFocus()
        self.statusBar().showMessage("Código LaTeX insertado desde Selene IA", 3000)

    def replace_ai_code(self, code: str, show_diff: bool = True):
        editor = self.current_editor
        cursor = editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")
        if selected and show_diff:
            dlg = AIDiffDialog(selected, code, self._current_theme, self)
            if dlg.exec() != AIDiffDialog.DialogCode.Accepted:
                return
        cursor.beginEditBlock()
        cursor.insertText(code)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        editor.setFocus()
        msg = "Selección reemplazada con código de Selene IA" if selected else "Código LaTeX insertado desde Selene IA"
        self.statusBar().showMessage(msg, 3000)

    def add_packages_to_preamble(self, packages: list[str]):
        if not packages:
            return
        target_editor = self.current_editor
        text = target_editor.toPlainText()

        # Si el archivo activo es un subarchivo sin \documentclass y hay un maestro, insertar en el maestro
        if r"\documentclass" not in text and self.master_file is not None and self.master_file.exists():
            self.load_file(self.master_file)
            target_editor = self.current_editor
            text = target_editor.toPlainText()

        existing = set(extract_document_packages(text))
        to_add = [p for p in packages if p not in existing]
        if not to_add:
            self.statusBar().showMessage("Esos paquetes ya están en el preámbulo", 3000)
            return

        lines = text.splitlines()
        insert_after_line = -1
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("%"):
                continue
            if r"\begin{document}" in stripped:
                break
            if re.search(r"\\usepackage(?:\[[^\]]*\])?\{", stripped):
                insert_after_line = i
            elif r"\documentclass" in stripped and insert_after_line == -1:
                insert_after_line = i

        snippet = "\n".join(f"\\usepackage{{{pkg}}}" for pkg in to_add)
        doc = target_editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        if insert_after_line >= 0:
            blk = doc.findBlockByLineNumber(insert_after_line)
            cursor.setPosition(blk.position() + len(blk.text()))
            cursor.insertText("\n" + snippet)
        else:
            cursor.setPosition(0)
            cursor.insertText(snippet + "\n")
        cursor.endEditBlock()
        target_editor.setTextCursor(cursor)
        target_editor.setFocus()
        self.statusBar().showMessage(f"Añadido al preámbulo: {', '.join(to_add)}", 4000)


def _ensure_tex_in_path():
    """En macOS, las apps .app lanzadas desde Finder no heredan /Library/TeX/texbin en PATH."""
    if sys.platform != "darwin":
        return
    extra_dirs = ["/Library/TeX/texbin", "/opt/homebrew/bin", "/usr/local/bin"]
    current = os.environ.get("PATH", "").split(os.pathsep)
    to_prepend = [d for d in extra_dirs if os.path.isdir(d) and d not in current]
    if to_prepend:
        os.environ["PATH"] = os.pathsep.join(to_prepend + current)


def main(argv: list[str] | None = None) -> int:
    _ensure_tex_in_path()
    args = sys.argv if argv is None else argv
    app = QApplication(args)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName("selenetex")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    widget = MainWindow()
    # Abrir archivos o carpeta pasados por línea de comandos (p. ej. `python selenetex.py tesis.tex`)
    for arg in args[1:]:
        if arg.startswith("-"):
            continue
        target = pathlib.Path(arg).expanduser()
        if target.is_dir():
            widget.update_project_root(target.resolve())
        elif target.is_file():
            widget.load_file(target.resolve())
    widget.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
