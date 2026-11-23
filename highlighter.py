# This Python file uses the following encoding: utf-8

import re
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

THEMES = {
    "dark": {
        "cmd": "#79b8ff",      # Azul claro brillante
        "env": "#b392f0",      # Lavanda / morado claro
        "bracket": "#ffab70",  # Naranja suave
        "math": "#85e89d",     # Verde menta
        "comment": "#8b949e",
    },
    "light": {
        "cmd": "#005cc5",      # Azul oscuro
        "env": "#6f42c1",      # Morado intenso
        "bracket": "#d73a49",  # Rojo/naranja
        "math": "#22863a",     # Verde bosque
        "comment": "#6a737d",  # Gris medio
    },
}

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #13151f;
    color: #e2e8f0;
    font-family: "Inter", "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #0f111a;
    color: #cbd5e1;
    border-bottom: 1px solid #1e2235;
    padding: 3px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected {
    background-color: #1e2438;
    color: #38bdf8;
}

QMenu {
    background-color: #161926;
    color: #e2e8f0;
    border: 1px solid #282e45;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #282e45;
    margin: 4px 8px;
}

QDockWidget {
    titlebar-close-icon: none;
    color: #94a3b8;
    font-weight: bold;
}
QDockWidget::title {
    background-color: #0f111a;
    padding: 7px 10px;
    border-bottom: 1px solid #1e2235;
}

QTreeView {
    background-color: #11131c;
    color: #cbd5e1;
    border: none;
    border-right: 1px solid #1e2235;
    padding: 4px;
    outline: none;
}
QTreeView::item {
    padding: 5px 6px;
    border-radius: 4px;
}
QTreeView::item:hover {
    background-color: #1a1e2e;
}
QTreeView::item:selected {
    background-color: #1e293b;
    color: #38bdf8;
}

QPlainTextEdit {
    background-color: #1a1b26;
    color: #e2e8f0;
    border: 1px solid #1e2235;
    border-radius: 6px;
    selection-background-color: #2e3c64;
    selection-color: #ffffff;
}
QPlainTextEdit#logView {
    background-color: #0f111a;
    color: #94a3b8;
    font-family: "Monospace";
    font-size: 12px;
}

QScrollArea {
    background-color: #0f111a;
    border: 1px solid #1e2235;
    border-radius: 6px;
}

QLineEdit {
    background-color: #0f111a;
    color: #f1f5f9;
    border: 1px solid #282e45;
    border-radius: 5px;
    padding: 4px 8px;
}
QLineEdit:focus {
    border: 1px solid #38bdf8;
}

QPushButton {
    background-color: #1e2438;
    color: #e2e8f0;
    border: 1px solid #2e3650;
    border-radius: 5px;
    padding: 4px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #28314d;
    border-color: #38bdf8;
    color: #38bdf8;
}
QPushButton:pressed {
    background-color: #1e3a8a;
}

QSplitter::handle {
    background-color: #13151f;
}
QSplitter::handle:horizontal {
    width: 5px;
}
QSplitter::handle:vertical {
    height: 5px;
}
QSplitter::handle:hover {
    background-color: #38bdf8;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #282e45;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #3b4466;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #282e45;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #3b4466;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QStatusBar {
    background-color: #0f111a;
    color: #94a3b8;
    border-top: 1px solid #1e2235;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #f3f4f6;
    color: #1e293b;
    font-family: "Inter", "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #ffffff;
    color: #334155;
    border-bottom: 1px solid #e2e8f0;
    padding: 3px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected {
    background-color: #eff6ff;
    color: #2563eb;
}

QMenu {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 4px 8px;
}

QDockWidget {
    color: #475569;
    font-weight: bold;
}
QDockWidget::title {
    background-color: #e2e8f0;
    padding: 7px 10px;
    border-bottom: 1px solid #cbd5e1;
}

QTreeView {
    background-color: #f8fafc;
    color: #334155;
    border: none;
    border-right: 1px solid #e2e8f0;
    padding: 4px;
    outline: none;
}
QTreeView::item {
    padding: 5px 6px;
    border-radius: 4px;
}
QTreeView::item:hover {
    background-color: #e2e8f0;
}
QTreeView::item:selected {
    background-color: #dbeafe;
    color: #1d4ed8;
}

QPlainTextEdit {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    selection-background-color: #bfdbfe;
    selection-color: #0f172a;
}
QPlainTextEdit#logView {
    background-color: #f8fafc;
    color: #475569;
    font-family: "Monospace";
    font-size: 12px;
}

QScrollArea {
    background-color: #e2e8f0;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
}

QLineEdit {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 4px 8px;
}
QLineEdit:focus {
    border: 1px solid #2563eb;
}

QPushButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 4px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #eff6ff;
    border-color: #2563eb;
    color: #2563eb;
}
QPushButton:pressed {
    background-color: #dbeafe;
}

QSplitter::handle {
    background-color: #e2e8f0;
}
QSplitter::handle:horizontal {
    width: 5px;
}
QSplitter::handle:vertical {
    height: 5px;
}
QSplitter::handle:hover {
    background-color: #2563eb;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QStatusBar {
    background-color: #ffffff;
    color: #475569;
    border-top: 1px solid #e2e8f0;
}
"""

def make_format(color, bold=False,italic=False):
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt

class LatexHighLighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        self.rules = []
        super().__init__(parent)

    def set_theme(self, theme_name):
        colors = THEMES.get(theme_name, THEMES["dark"])

        cmd_format = make_format(colors["cmd"], bold=True)
        env_format = make_format(colors["env"], bold=True)
        bracket_format = make_format(colors["bracket"])
        math_format = make_format(colors["math"])
        comment_format = make_format(colors["comment"], italic=True)

        self.rules = [
            (re.compile(r"\\[A-Za-z@]+|\\."), cmd_format),
            (re.compile(r"\\(?:begin|end)\{[^}]*\}"), env_format),
            (re.compile(r"[\{\}\[\]]"), bracket_format),
            (re.compile(r"\$[^\$]+\$"), math_format),
            (re.compile(r"(?<!\\)%.*$"), comment_format),
        ]

        self.rehighlight()


    def highlightBlock(self,text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)

