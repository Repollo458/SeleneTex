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

