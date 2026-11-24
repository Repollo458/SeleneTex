# This Python file uses the following encoding: utf-8
"""Diálogos de Ayuda de SeleneTeX: comprobación del entorno LaTeX y Acerca de."""

import pathlib
import platform
import shutil

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from highlighter import SEMANTIC_TOKENS
from icons import svg_icon

APP_VERSION = "1.0.0"

_TEX_TOOLS: list[tuple[str, str, bool]] = [
    ("latexmk", "Compilación automática (recomendado)", True),
    ("lualatex", "Motor moderno por defecto (UTF-8 y fuentes del sistema)", True),
    ("pdflatex", "Motor clásico y previsualización rápida de fórmulas", True),
    ("xelatex", "Motor Unicode alternativo", False),
    ("synctex", "Sincronización bidireccional Código ↔ PDF", False),
]


def _install_hint_for_platform() -> tuple[str, str]:
    sys_name = platform.system()
    if sys_name == "Darwin":
        return ("macOS (Homebrew + BasicTeX / MacTeX)", "brew install --cask mactex-no-gui")
    if sys_name == "Windows":
        return ("Windows (winget + MiKTeX)", "winget install MiKTeX.MiKTeX")
    return (
        "Linux (Ubuntu / Debian)",
        "sudo apt update && sudo apt install texlive-latex-extra texlive-luatex latexmk",
    )


class EnvironmentCheckDialog(QDialog):
    """Comprueba las herramientas LaTeX instaladas en el sistema y ofrece guía de instalación."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme_name
        self.setWindowTitle("Comprobar entorno LaTeX — SeleneTeX")
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Entorno LaTeX del sistema", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "SeleneTeX usa tu distribución local de TeX (TeX Live, MiKTeX o MacTeX) para compilar PDF y previsualizar fórmulas.",
            self,
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.summary_label = QLabel("", self)
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.list_frame = QFrame(self)
        self.list_frame.setObjectName("aiBubble")
        self.list_layout = QGridLayout(self.list_frame)
        self.list_layout.setContentsMargins(16, 14, 16, 14)
        self.list_layout.setHorizontalSpacing(12)
        self.list_layout.setVerticalSpacing(10)
        self.list_layout.setColumnStretch(2, 1)
        root.addWidget(self.list_frame)

        os_label, self._install_cmd = _install_hint_for_platform()
        hint_lbl = QLabel(f"Instalación rápida recomendada — {os_label}:", self)
        hint_lbl.setObjectName("fieldLabel")
        hint_lbl.setWordWrap(True)
        root.addWidget(hint_lbl)

        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(8)
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        self.cmd_box = QLabel(self._install_cmd, self)
        self.cmd_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cmd_box.setWordWrap(True)
        self.cmd_box.setStyleSheet(
            f"background:{t['bg_chrome']};color:{t['text_primary']};"
            f"border:1px solid {t['border_default']};border-radius:8px;"
            f"padding:8px 10px;font-family:'JetBrains Mono','DejaVu Sans Mono',monospace;font-size:11.5px;"
        )
        btn_copy_cmd = QPushButton(" Copiar", self)
        btn_copy_cmd.setIcon(svg_icon("copy", t["text_secondary"], size=14))
        btn_copy_cmd.setIconSize(QSize(14, 14))
        btn_copy_cmd.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_cmd.clicked.connect(self._copy_install_cmd)
        cmd_row.addWidget(self.cmd_box, 1)
        cmd_row.addWidget(btn_copy_cmd)
        root.addLayout(cmd_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_recheck = QPushButton("Volver a comprobar", self)
        btn_recheck.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_recheck.clicked.connect(self.refresh_checks)
        btn_row.addWidget(btn_recheck)
        btn_row.addStretch(1)
        btn_close = QPushButton("Cerrar", self)
        btn_close.setObjectName("primaryBtn")
        btn_close.setDefault(True)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self.refresh_checks()

    def _copy_install_cmd(self):
        QApplication.clipboard().setText(self._install_cmd)
        self.summary_label.setObjectName("fieldSuccess")
        self.summary_label.setText("✓ Comando de instalación copiado al portapapeles.")
        self.summary_label.style().unpolish(self.summary_label)
        self.summary_label.style().polish(self.summary_label)

    def refresh_checks(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        missing_required: list[str] = []

        for row_idx, (binary, desc, required) in enumerate(_TEX_TOOLS):
            found_path = shutil.which(binary)
            if not found_path and required:
                missing_required.append(binary)

            if found_path:
                badge_color = t["success_text"]
            elif required:
                badge_color = t["danger_text"]
            else:
                badge_color = t["warn_text"]

            badge = QLabel("✓" if found_path else "✕", self.list_frame)
            badge.setFixedWidth(18)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(f"color:{badge_color};font-weight:700;font-size:13px;")

            lbl_bin = QLabel(binary, self.list_frame)
            lbl_bin.setStyleSheet(
                f"color:{t['text_primary']};font-weight:600;font-size:12.5px;"
            )

            lbl_desc = QLabel(desc, self.list_frame)
            lbl_desc.setStyleSheet(f"color:{t['text_muted']};font-size:12px;")

            status_txt = found_path if found_path else ("Falta (recomendado)" if required else "No instalado")
            status = QLabel(status_txt, self.list_frame)
            status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            status.setStyleSheet(
                f"color:{t['text_secondary'] if found_path else badge_color};"
                f"font-family:'JetBrains Mono','DejaVu Sans Mono',monospace;font-size:11.5px;"
            )

            self.list_layout.addWidget(badge, row_idx, 0)
            self.list_layout.addWidget(lbl_bin, row_idx, 1)
            self.list_layout.addWidget(lbl_desc, row_idx, 2)
            self.list_layout.addWidget(status, row_idx, 3)

        if not missing_required:
            self.summary_label.setObjectName("fieldSuccess")
            self.summary_label.setText(
                "✓ Todo listo: tu sistema cuenta con las herramientas esenciales para compilar LaTeX y previsualizar fórmulas."
            )
        else:
            self.summary_label.setObjectName("fieldError")
            self.summary_label.setText(
                f"⚠ Faltan herramientas recomendadas: {', '.join(missing_required)}. "
                "Instala TeX Live o MiKTeX y pulsa «Volver a comprobar»."
            )
        self.summary_label.style().unpolish(self.summary_label)
        self.summary_label.style().polish(self.summary_label)


class AboutDialog(QDialog):
    """Ventana Acerca de SeleneTeX con versión, resumen de funciones y licencia."""

    def __init__(self, logo_path: pathlib.Path, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acerca de SeleneTeX")
        self.setFixedWidth(470)
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(16)
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            lbl_logo = QLabel(self)
            lbl_logo.setPixmap(pm)
            lbl_logo.setFixedSize(76, 76)
            top.addWidget(lbl_logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        lbl_name = QLabel("SeleneTeX", self)
        lbl_name.setObjectName("dialogTitle")
        lbl_ver = QLabel(f"Versión {APP_VERSION}", self)
        lbl_ver.setStyleSheet(f"color:{t['accent_text']};font-weight:600;font-size:12.5px;")
        lbl_desc = QLabel(
            "IDE LaTeX moderno de escritorio con visor PDF + SyncTeX, previsualización de fórmulas, herramientas visuales e IA integrada.",
            self,
        )
        lbl_desc.setObjectName("dialogSubtitle")
        lbl_desc.setWordWrap(True)
        title_col.addWidget(lbl_name)
        title_col.addWidget(lbl_ver)
        title_col.addWidget(lbl_desc)
        top.addLayout(title_col, 1)
        root.addLayout(top)

        card = QFrame(self)
        card.setObjectName("aiBubble")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(14, 12, 14, 12)
        card_l.setSpacing(5)
        highlights = QLabel(
            f"<div style='color:{t['text_secondary']};font-size:12px;line-height:1.5;'>"
            "• <b>Editor multipestaña</b> con autocompletado contextual (\\ref, \\cite) y diagnósticos en línea.<br>"
            "• <b>Visor PDF HiDPI</b> con SyncTeX bidireccional, búsqueda, selección, doble página y Modo Noche.<br>"
            "• <b>Herramientas visuales</b>: generador de tablas, paleta de símbolos, gestor BibTeX/DOI y preview de fórmulas/TikZ.<br>"
            "• <b>Selene IA</b>: contexto inteligente del proyecto, Imagen a LaTeX (OCR), diff visual y soporte Gemini / Ollama local."
            "</div>",
            card,
        )
        highlights.setTextFormat(Qt.TextFormat.RichText)
        highlights.setWordWrap(True)
        card_l.addWidget(highlights)
        root.addWidget(card)

        footer = QHBoxLayout()
        lbl_meta = QLabel(
            f"Python {platform.python_version()} · PySide6 · Licencia MIT",
            self,
        )
        lbl_meta.setStyleSheet(f"color:{t['text_muted']};font-size:11.5px;")
        btn_close = QPushButton("Cerrar", self)
        btn_close.setObjectName("primaryBtn")
        btn_close.setDefault(True)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(lbl_meta)
        footer.addStretch(1)
        footer.addWidget(btn_close)
        root.addLayout(footer)
