# This Python file uses the following encoding: utf-8
"""Preferencias de usuario y Paleta de Comandos (Ctrl+Shift+P) para SeleneTeX."""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QRect, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

from ai_client import ChevronComboBox
from highlighter import SEMANTIC_TOKENS
from latex_tools import SeleneCheckBox

CURATED_MONO_FONTS = (
    "JetBrains Mono",
    "Fira Code",
    "Cascadia Code",
    "Ubuntu Mono",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Source Code Pro",
    "Hack",
    "IBM Plex Mono",
    "Monospace",
)


def list_available_mono_fonts() -> list[str]:
    """Devuelve fuentes monoespaciadas instaladas priorizando las más legibles para código."""
    installed = set(QFontDatabase.families())
    found: list[str] = [f for f in CURATED_MONO_FONTS if f in installed]
    for fam in sorted(installed):
        if fam not in found and QFontDatabase.isFixedPitch(fam):
            found.append(fam)
    if "Monospace" not in found:
        found.append("Monospace")
    return found


class PreferencesDialog(QDialog):
    """Ventana de Preferencias de SeleneTeX organizada en tarjetas claras."""

    def __init__(self, settings: QSettings, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.settings = settings
        self._theme = theme_name
        self.setWindowTitle("Preferencias — SeleneTeX")
        self.setMinimumWidth(520)
        self.resize(560, 520)
        self.result_prefs: dict = {}

        # Leer valores actuales desde QSettings
        mono_fonts = list_available_mono_fonts()
        default_font = mono_fonts[0]
        saved_font = settings.value("editor/font_family", default_font, type=str)
        if saved_font not in mono_fonts:
            saved_font = default_font
        self._font_size = max(8, min(28, settings.value("editor/font_size", 11, type=int)))
        self._tab_width = settings.value("editor/tab_width", 4, type=int)
        if self._tab_width not in (2, 4, 8):
            self._tab_width = 4
        saved_wrap = settings.value("editor/word_wrap", True, type=bool)
        saved_autoclose = settings.value("editor/auto_close", True, type=bool)

        saved_engine = settings.value("build/engine", "LuaLaTeX", type=str)
        if saved_engine not in ("LuaLaTeX", "pdfLaTeX", "XeLaTeX"):
            saved_engine = "LuaLaTeX"
        saved_shell_escape = settings.value("build/shell_escape", False, type=bool)
        self._autocompile_ms = max(500, min(5000, settings.value("build/autocompile_ms", 1500, type=int)))
        saved_restore = settings.value("session/restore_enabled", True, type=bool)
        saved_autosave = settings.value("session/autosave_on_blur", False, type=bool)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("Preferencias", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Personaliza el editor, la compilación y la restauración de sesiones.", self)
        subtitle.setObjectName("dialogSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        # ---- Tarjeta 1: Editor ----
        ed_card = QFrame(self)
        ed_card.setObjectName("toolCard")
        ed_lay = QVBoxLayout(ed_card)
        ed_lay.setContentsMargins(16, 12, 16, 14)
        ed_lay.setSpacing(10)

        lbl_ed = QLabel("Editor de código", ed_card)
        lbl_ed.setObjectName("fieldLabel")
        ed_lay.addWidget(lbl_ed)

        # Fila tipografía + tamaño
        font_row = QHBoxLayout()
        font_row.setSpacing(10)
        font_row.addWidget(QLabel("Fuente:", ed_card))
        self.combo_font = ChevronComboBox(theme_name, ed_card)
        self.combo_font.addItems(mono_fonts)
        self.combo_font.setCurrentText(saved_font)
        font_row.addWidget(self.combo_font, 1)

        font_row.addWidget(QLabel("Tamaño:", ed_card))
        btn_fs_m = QPushButton("−", ed_card)
        btn_fs_m.setObjectName("stepBtn")
        btn_fs_m.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fs_m.clicked.connect(lambda: self._step_font_size(-1))

        self.lbl_font_size = QLabel(f"{self._font_size} pt", ed_card)
        self.lbl_font_size.setObjectName("dimCountBadge")
        self.lbl_font_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_font_size.setMinimumWidth(46)

        btn_fs_p = QPushButton("+", ed_card)
        btn_fs_p.setObjectName("stepBtn")
        btn_fs_p.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fs_p.clicked.connect(lambda: self._step_font_size(1))

        font_row.addWidget(btn_fs_m)
        font_row.addWidget(self.lbl_font_size)
        font_row.addWidget(btn_fs_p)
        ed_lay.addLayout(font_row)

        # Fila tabulación (control segmentado 2 | 4 | 8)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(10)
        tab_row.addWidget(QLabel("Sangría / Tabulación:", ed_card))
        seg_tab = QFrame(ed_card)
        seg_tab.setObjectName("segmentedControl")
        seg_lay = QHBoxLayout(seg_tab)
        seg_lay.setContentsMargins(2, 2, 2, 2)
        seg_lay.setSpacing(2)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        for spaces in (2, 4, 8):
            b = QPushButton(f"{spaces} espacios", seg_tab)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if spaces == self._tab_width:
                b.setChecked(True)
            b.clicked.connect(lambda checked=False, sp=spaces: self._set_tab_width(sp))
            self._tab_group.addButton(b)
            seg_lay.addWidget(b)
        tab_row.addWidget(seg_tab)
        tab_row.addStretch(1)
        ed_lay.addLayout(tab_row)

        self.chk_word_wrap = SeleneCheckBox("Ajuste automático de línea (Word Wrap)", ed_card)
        self.chk_word_wrap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_word_wrap.setChecked(saved_wrap)
        ed_lay.addWidget(self.chk_word_wrap)

        self.chk_autoclose = SeleneCheckBox("Autocierre de llaves, corchetes y entornos \\begin{...}", ed_card)
        self.chk_autoclose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autoclose.setChecked(saved_autoclose)
        ed_lay.addWidget(self.chk_autoclose)

        root.addWidget(ed_card)

        # ---- Tarjeta 2: Compilación y sesión ----
        build_card = QFrame(self)
        build_card.setObjectName("toolCard")
        build_lay = QVBoxLayout(build_card)
        build_lay.setContentsMargins(16, 12, 16, 14)
        build_lay.setSpacing(10)

        lbl_build = QLabel("Compilación y sesión", build_card)
        lbl_build.setObjectName("fieldLabel")
        build_lay.addWidget(lbl_build)

        eng_row = QHBoxLayout()
        eng_row.setSpacing(10)
        eng_row.addWidget(QLabel("Motor por defecto:", build_card))
        self.combo_engine = ChevronComboBox(theme_name, build_card)
        self.combo_engine.addItems(["LuaLaTeX", "pdfLaTeX", "XeLaTeX"])
        self.combo_engine.setCurrentText(saved_engine)
        eng_row.addWidget(self.combo_engine, 1)

        eng_row.addWidget(QLabel("Autocompilar:", build_card))
        btn_ac_m = QPushButton("−", build_card)
        btn_ac_m.setObjectName("stepBtn")
        btn_ac_m.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ac_m.clicked.connect(lambda: self._step_autocompile(-250))

        self.lbl_ac_delay = QLabel(f"{self._autocompile_ms / 1000:.2f} s", build_card)
        self.lbl_ac_delay.setObjectName("dimCountBadge")
        self.lbl_ac_delay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_ac_delay.setMinimumWidth(52)

        btn_ac_p = QPushButton("+", build_card)
        btn_ac_p.setObjectName("stepBtn")
        btn_ac_p.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ac_p.clicked.connect(lambda: self._step_autocompile(250))

        eng_row.addWidget(btn_ac_m)
        eng_row.addWidget(self.lbl_ac_delay)
        eng_row.addWidget(btn_ac_p)
        build_lay.addLayout(eng_row)

        self.chk_shell_escape = SeleneCheckBox("Habilitar --shell-escape (necesario para minted / svg)", build_card)
        self.chk_shell_escape.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_shell_escape.setChecked(saved_shell_escape)
        build_lay.addWidget(self.chk_shell_escape)

        self.chk_restore_session = SeleneCheckBox("Restaurar pestañas y sesión anterior al abrir SeleneTeX", build_card)
        self.chk_restore_session.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_restore_session.setChecked(saved_restore)
        build_lay.addWidget(self.chk_restore_session)

        self.chk_autosave = SeleneCheckBox("Guardar automáticamente archivos abiertos al cambiar de ventana", build_card)
        self.chk_autosave.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autosave.setChecked(saved_autosave)
        build_lay.addWidget(self.chk_autosave)

        root.addWidget(build_card)
        root.addStretch(1)

        # Acciones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Guardar preferencias", self)
        btn_save.setObjectName("primaryBtn")
        btn_save.setDefault(True)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save_and_accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    def _step_font_size(self, delta: int):
        self._font_size = max(8, min(28, self._font_size + delta))
        self.lbl_font_size.setText(f"{self._font_size} pt")

    def _set_tab_width(self, spaces: int):
        self._tab_width = spaces

    def _step_autocompile(self, delta_ms: int):
        self._autocompile_ms = max(500, min(5000, self._autocompile_ms + delta_ms))
        self.lbl_ac_delay.setText(f"{self._autocompile_ms / 1000:.2f} s")

    def save_and_accept(self):
        prefs = {
            "font_family": self.combo_font.currentText(),
            "font_size": self._font_size,
            "tab_width": self._tab_width,
            "word_wrap": self.chk_word_wrap.isChecked(),
            "auto_close": self.chk_autoclose.isChecked(),
            "engine": self.combo_engine.currentText(),
            "shell_escape": self.chk_shell_escape.isChecked(),
            "autocompile_ms": self._autocompile_ms,
            "restore_session": self.chk_restore_session.isChecked(),
            "autosave_on_blur": self.chk_autosave.isChecked(),
        }
        self.settings.setValue("editor/font_family", prefs["font_family"])
        self.settings.setValue("editor/font_size", prefs["font_size"])
        self.settings.setValue("editor/tab_width", prefs["tab_width"])
        self.settings.setValue("editor/word_wrap", prefs["word_wrap"])
        self.settings.setValue("editor/auto_close", prefs["auto_close"])
        self.settings.setValue("build/engine", prefs["engine"])
        self.settings.setValue("build/shell_escape", prefs["shell_escape"])
        self.settings.setValue("build/autocompile_ms", prefs["autocompile_ms"])
        self.settings.setValue("session/restore_enabled", prefs["restore_session"])
        self.settings.setValue("session/autosave_on_blur", prefs["autosave_on_blur"])
        self.result_prefs = prefs
        self.accept()


# ==============================================================================
# PALETA DE COMANDOS (Ctrl+Shift+P)
# ==============================================================================
@dataclass
class PaletteCommand:
    category: str
    title: str
    callback: Callable[[], None]
    shortcut: str = ""
    keywords: str = ""


class CommandPaletteDelegate(QStyledItemDelegate):
    """Renderiza cada fila de la paleta de comandos con categoría, título y atajo."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme_name

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 36)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        dark = self._theme == "dark"
        t = SEMANTIC_TOKENS["dark" if dark else "light"]
        cmd: PaletteCommand | None = index.data(Qt.ItemDataRole.UserRole)
        if cmd is None:
            painter.restore()
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = option.rect.adjusted(4, 2, -4, -2)

        if is_selected:
            bg = QColor("#1f2a4d") if dark else QColor("#e0e7ff")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 7.0, 7.0)
            bar = QRectF(rect.left() + 1, rect.top() + 5, 3.0, rect.height() - 10)
            painter.setBrush(QColor("#818cf8") if dark else QColor("#4f46e5"))
            painter.drawRoundedRect(bar, 1.5, 1.5)
        elif is_hovered:
            bg = QColor("#192038") if dark else QColor("#f1f4fa")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 7.0, 7.0)

        # Insignia de categoría a la izquierda
        cat_font = QFont(option.font)
        cat_font.setPointSize(8)
        cat_font.setBold(True)
        cat_fm = QFontMetrics(cat_font)
        cat_text = cmd.category
        cat_w = max(68, cat_fm.horizontalAdvance(cat_text) + 14)
        cat_rect = QRectF(rect.left() + 10, rect.top() + 6, cat_w, rect.height() - 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["bg_pill"]))
        painter.drawRoundedRect(cat_rect, 5.0, 5.0)
        painter.setFont(cat_font)
        painter.setPen(QColor(t["accent_text"] if is_selected else t["text_muted"]))
        painter.drawText(cat_rect, Qt.AlignmentFlag.AlignCenter, cat_text)

        # Atajo de teclado a la derecha
        right_edge = rect.right() - 10
        if cmd.shortcut:
            sc_font = QFont("JetBrains Mono", 8)
            sc_font.setStyleHint(QFont.StyleHint.Monospace)
            sc_fm = QFontMetrics(sc_font)
            sc_w = sc_fm.horizontalAdvance(cmd.shortcut) + 14
            sc_rect = QRectF(right_edge - sc_w, rect.top() + 6, sc_w, rect.height() - 12)
            painter.setPen(QColor(t["border_default"]))
            painter.setBrush(QColor(t["bg_input"]))
            painter.drawRoundedRect(sc_rect, 5.0, 5.0)
            painter.setFont(sc_font)
            painter.setPen(QColor(t["text_secondary"]))
            painter.drawText(sc_rect, Qt.AlignmentFlag.AlignCenter, cmd.shortcut)
            right_edge = int(sc_rect.left()) - 10

        # Título del comando
        title_font = QFont(option.font)
        title_font.setPointSize(10)
        title_font.setWeight(QFont.Weight.DemiBold if is_selected else QFont.Weight.Normal)
        title_rect = QRect(int(cat_rect.right()) + 10, rect.top(), max(40, right_edge - int(cat_rect.right()) - 10), rect.height())
        painter.setFont(title_font)
        painter.setPen(QColor(t["text_primary"]))
        elided = QFontMetrics(title_font).elidedText(cmd.title, Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.restore()


class CommandPaletteDialog(QDialog):
    """Paleta flotante de comandos con búsqueda instantánea por teclado (Ctrl+Shift+P)."""

    def __init__(self, commands: list[PaletteCommand], theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._all_commands = list(commands)
        self._theme = theme_name
        self.selected_command: PaletteCommand | None = None

        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 14)

        self.card = QFrame(self)
        self.card.setObjectName("commandPalette")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 140 if theme_name == "dark" else 48))
        self.card.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        self.search_input = QLineEdit(self.card)
        self.search_input.setObjectName("paletteInput")
        self.search_input.setPlaceholderText("Escribe un comando, plantilla o herramienta...")
        self.search_input.setAccessibleName("Buscar comando")
        self.search_input.textChanged.connect(self._filter_commands)
        self.search_input.installEventFilter(self)
        lay.addWidget(self.search_input)

        self.list_widget = QListWidget(self.card)
        self.list_widget.setObjectName("paletteList")
        self.list_widget.setMouseTracking(True)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setItemDelegate(CommandPaletteDelegate(theme_name, self.list_widget))
        self.list_widget.setMaximumHeight(330)
        self.list_widget.itemActivated.connect(self._execute_item)
        self.list_widget.itemClicked.connect(self._execute_item)
        lay.addWidget(self.list_widget)

        outer.addWidget(self.card)
        self._filter_commands("")
        self.search_input.setFocus()

    def position_over_parent(self, parent_widget):
        if parent_widget is None:
            return
        geo = parent_widget.geometry()
        x = geo.x() + max(16, (geo.width() - self.width()) // 2)
        y = geo.y() + 68
        self.move(x, y)

    def eventFilter(self, obj, event):
        if obj is self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = self.list_widget.currentRow()
                if self.list_widget.count() > 0:
                    self.list_widget.setCurrentRow((row + 1) % self.list_widget.count())
                return True
            if key == Qt.Key.Key_Up:
                row = self.list_widget.currentRow()
                if self.list_widget.count() > 0:
                    self.list_widget.setCurrentRow((row - 1) % self.list_widget.count())
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list_widget.currentItem()
                if item is not None:
                    self._execute_item(item)
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def _filter_commands(self, raw_query: str):
        self.list_widget.clear()
        tokens = raw_query.strip().lower().split()
        matched: list[PaletteCommand] = []
        for cmd in self._all_commands:
            haystack = f"{cmd.category} {cmd.title} {cmd.keywords} {cmd.shortcut}".lower()
            if all(tok in haystack for tok in tokens):
                matched.append(cmd)

        for cmd in matched:
            item = QListWidgetItem(cmd.title)
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        visible_rows = max(1, min(9, self.list_widget.count()))
        self.list_widget.setFixedHeight(visible_rows * 36 + 6)
        self.adjustSize()

    def _execute_item(self, item: QListWidgetItem):
        cmd: PaletteCommand | None = item.data(Qt.ItemDataRole.UserRole)
        if cmd is None:
            return
        self.selected_command = cmd
        self.accept()
