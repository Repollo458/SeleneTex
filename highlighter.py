# This Python file uses the following encoding: utf-8

import re
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

# ==============================================================================
# 1. TOKENS PRIMITIVOS (Paleta Lunar SeleneTeX + Escala Espacial 4px/8px)
# Inspirada en logo.png: índigo nocturno profundo, cielo lunar, menta y destello dorado
# ==============================================================================
PRIMITIVES = {
    # Neutros oscuros con matiz índigo lunar muy sutil (desaturado para confort visual)
    "night_975": "#090b14",
    "night_950": "#0c0f1a",
    "night_925": "#0f1322",
    "night_900": "#121728",
    "night_850": "#181e34",
    "night_800": "#202845",
    "night_700": "#2d375c",
    # Neutros claros (porcelana fría y niebla lunar)
    "mist_50": "#f8f9fc",
    "mist_100": "#f1f4fa",
    "mist_200": "#e4e9f4",
    "mist_300": "#cfd7e8",
    "mist_400": "#94a3b8",
    "mist_500": "#64748b",
    "mist_600": "#475569",
    "mist_700": "#334155",
    "mist_900": "#0f172a",
    "white": "#ffffff",
    # Acentos lunares (índigo cósmico → azul cielo → menta)
    "indigo_400": "#818cf8",
    "indigo_500": "#6366f1",
    "indigo_600": "#4f46e5",
    "indigo_700": "#4338ca",
    "indigo_100": "#e0e7ff",
    "indigo_50": "#eef2ff",
    "sky_300": "#7dd3fc",
    "sky_400": "#38bdf8",
    "blue_500": "#3b82f6",
    "blue_600": "#2563eb",
    "blue_700": "#1d4ed8",
    # Semánticos de estado
    "mint_300": "#6ee7b7",
    "emerald_400": "#34d399",
    "emerald_600": "#059669",
    "star_300": "#fde047",
    "amber_400": "#fbbf24",
    "amber_600": "#b45309",
    "rose_300": "#fca5a5",
    "rose_400": "#f87171",
    "rose_600": "#dc2626",
}

# Escala espacial de 8 puntos con sub-unidad de 4 puntos
SPACE = {
    "1": "4px",
    "2": "8px",
    "3": "12px",
    "4": "16px",
    "6": "24px",
}

# ==============================================================================
# 2. TOKENS SEMÁNTICOS (Regla 60-30-10 & WCAG 2.2 AA >= 4.5:1)
# ==============================================================================
SEMANTIC_TOKENS = {
    "dark": {
        # 60% Superficie base neutra
        "bg_app": PRIMITIVES["night_950"],
        "bg_chrome": PRIMITIVES["night_975"],
        "bg_canvas": "#0a0d17",
        # 30% Superficies elevadas (jerarquía tonal con mínimos bordes)
        "bg_surface": PRIMITIVES["night_900"],
        "bg_surface_alt": PRIMITIVES["night_925"],
        "bg_elevated": PRIMITIVES["night_850"],
        "bg_hover": PRIMITIVES["night_800"],
        "bg_active": "#252f52",
        "bg_input": "#0b0e19",
        "bg_pill": "#171d32",
        # Bordes discretos
        "border_subtle": "#1a2038",
        "border_default": "#252e4d",
        "border_strong": "#374470",
        # Texto calibrado WCAG 2.2 AA (>= 4.5:1)
        "text_primary": "#f1f5f9",
        "text_secondary": "#cbd5e1",
        "text_muted": "#94a3b8",
        "text_disabled": "#64748b",
        # 10% Acento lunar funcional (CTA principal + foco)
        "accent_primary": PRIMITIVES["indigo_600"],
        "accent_primary_hover": PRIMITIVES["indigo_500"],
        "accent_primary_pressed": PRIMITIVES["indigo_700"],
        "accent_grad_start": PRIMITIVES["indigo_600"],
        "accent_grad_end": PRIMITIVES["blue_600"],
        "accent_grad_hover_start": PRIMITIVES["indigo_500"],
        "accent_grad_hover_end": PRIMITIVES["blue_500"],
        "accent_text": PRIMITIVES["sky_300"],
        "accent_icon": PRIMITIVES["indigo_400"],
        "accent_soft_bg": "#1a2240",
        "accent_soft_hover": "#232e54",
        "focus_ring": PRIMITIVES["sky_400"],
        # Estados semánticos suaves (sin cajas chillonas)
        "selection_bg": "#27386b",
        "selection_fg": PRIMITIVES["white"],
        "danger_border": "#7f2837",
        "danger_bg": "#28131d",
        "danger_text": PRIMITIVES["rose_300"],
        "warning_bg": "#261f12",
        "warning_text": PRIMITIVES["amber_400"],
        "success_bg": "#102721",
        "success_text": PRIMITIVES["emerald_400"],
        # Scrollbars y tooltips
        "scroll_handle": "#273152",
        "scroll_handle_hover": "#3d4c7a",
        "tooltip_bg": "#181e34",
        "tooltip_fg": "#f8fafc",
        # Editor gutter
        "gutter_bg": "#0e1220",
        "gutter_border": "#192036",
        "gutter_fg": "#64748b",
        "gutter_active": PRIMITIVES["sky_300"],
        "editor_line_hl": "#181f36",
    },
    "light": {
        # 60% Superficie base neutra
        "bg_app": PRIMITIVES["mist_100"],
        "bg_chrome": PRIMITIVES["white"],
        "bg_canvas": "#e8edf6",
        # 30% Superficies elevadas
        "bg_surface": PRIMITIVES["white"],
        "bg_surface_alt": PRIMITIVES["mist_50"],
        "bg_elevated": PRIMITIVES["white"],
        "bg_hover": PRIMITIVES["mist_200"],
        "bg_active": PRIMITIVES["indigo_100"],
        "bg_input": PRIMITIVES["white"],
        "bg_pill": PRIMITIVES["mist_200"],
        # Bordes suaves
        "border_subtle": "#e3e8f2",
        "border_default": PRIMITIVES["mist_300"],
        "border_strong": PRIMITIVES["mist_400"],
        # Texto WCAG 2.2 AA (>= 4.5:1)
        "text_primary": PRIMITIVES["mist_900"],
        "text_secondary": PRIMITIVES["mist_700"],
        "text_muted": PRIMITIVES["mist_600"],
        "text_disabled": PRIMITIVES["mist_400"],
        # 10% Acento lunar funcional
        "accent_primary": PRIMITIVES["indigo_600"],
        "accent_primary_hover": PRIMITIVES["indigo_700"],
        "accent_primary_pressed": "#3730a3",
        "accent_grad_start": PRIMITIVES["indigo_600"],
        "accent_grad_end": PRIMITIVES["blue_600"],
        "accent_grad_hover_start": PRIMITIVES["indigo_700"],
        "accent_grad_hover_end": PRIMITIVES["blue_700"],
        "accent_text": PRIMITIVES["indigo_700"],
        "accent_icon": PRIMITIVES["indigo_600"],
        "accent_soft_bg": PRIMITIVES["indigo_50"],
        "accent_soft_hover": PRIMITIVES["indigo_100"],
        "focus_ring": PRIMITIVES["indigo_500"],
        # Estados semánticos suaves
        "selection_bg": "#c7d2fe",
        "selection_fg": PRIMITIVES["mist_900"],
        "danger_border": "#fca5a5",
        "danger_bg": "#fef2f2",
        "danger_text": PRIMITIVES["rose_600"],
        "warning_bg": "#fffbeb",
        "warning_text": PRIMITIVES["amber_600"],
        "success_bg": "#ecfdf5",
        "success_text": PRIMITIVES["emerald_600"],
        # Scrollbars y tooltips
        "scroll_handle": "#cbd5e1",
        "scroll_handle_hover": "#94a3b8",
        "tooltip_bg": "#0f172a",
        "tooltip_fg": "#f8fafc",
        # Editor gutter
        "gutter_bg": "#f8f9fc",
        "gutter_border": "#e4e9f4",
        "gutter_fg": "#64748b",
        "gutter_active": PRIMITIVES["indigo_600"],
        "editor_line_hl": "#eef2ff",
    },
}

# Colores de resaltado de sintaxis en armonía con el logo (cielo, lavanda, menta, estrella)
THEMES = {
    "dark": {
        "cmd": "#7dd3fc",      # Cielo lunar
        "env": "#a5b4fc",      # Índigo/lavanda suave
        "bracket": "#fde047",  # Destello estelar
        "math": "#6ee7b7",     # Menta lunar
        "comment": "#7c8ba8",  # Pizarra lunar legible (AA)
    },
    "light": {
        "cmd": "#2563eb",      # Azul cobalto
        "env": "#4f46e5",      # Índigo
        "bracket": "#b45309",  # Ámbar oscuro AA
        "math": "#047857",     # Esmeralda AA
        "comment": "#64748b",  # Gris pizarra AA
    },
}


# ==============================================================================
# 3. GENERADOR DE STYLESHEET (Tonal Elevation + Bajo ruido de bordes)
# ==============================================================================
def build_stylesheet(theme_name: str) -> str:
    t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
    s = SPACE
    return f"""
/* Base global (60% superficie neutra) */
QMainWindow, QDialog {{
    background-color: {t["bg_app"]};
    color: {t["text_primary"]};
    font-family: "Inter", "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {t["text_primary"]};
}}

QWidget#centralwidget {{
    background-color: {t["bg_app"]};
}}

QLabel {{
    background: transparent;
    color: {t["text_primary"]};
}}

/* Barra de menú */
QMenuBar {{
    background-color: {t["bg_chrome"]};
    color: {t["text_secondary"]};
    border-bottom: 1px solid {t["border_subtle"]};
    padding: 2px {s["2"]};
    spacing: {s["1"]};
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px {s["3"]};
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}

QMenu {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {s["1"]};
}}
QMenu::item {{
    padding: 6px 28px 6px {s["3"]};
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {t["accent_primary"]};
    color: #ffffff;
}}
QMenu::item:disabled {{
    color: {t["text_disabled"]};
}}
QMenu::separator {{
    height: 1px;
    background: {t["border_subtle"]};
    margin: {s["1"]} {s["2"]};
}}

/* Barra de herramientas superior */
QToolBar#mainToolBar {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
    spacing: {s["1"]};
    padding: 6px {s["3"]};
}}
QToolBar#mainToolBar::separator {{
    width: 1px;
    background-color: {t["border_subtle"]};
    margin: 5px {s["2"]};
}}
QLabel#brandTitle {{
    color: {t["text_primary"]};
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.3px;
    padding-right: {s["2"]};
}}

/* Botones de barra (planos sin bordes innecesarios; foco accesible en teclado) */
QPushButton#toolBtn, QPushButton#formatBtn {{
    background-color: transparent;
    color: {t["text_secondary"]};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 4px 9px;
    min-height: 22px;
    font-weight: 500;
}}
QPushButton#formatBtn {{
    min-width: 26px;
    padding: 4px 7px;
}}
QPushButton#toolBtn:hover, QPushButton#formatBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#toolBtn:pressed, QPushButton#formatBtn:pressed {{
    background-color: {t["bg_active"]};
}}
QPushButton#toolBtn:checked {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    font-weight: 600;
}}
QPushButton#toolBtn:focus, QPushButton#formatBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Control segmentado de modo de vista (Código | Dividido | PDF) */
QFrame#segmentedControl {{
    background-color: {t["bg_input"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 8px;
    padding: 2px;
}}
QPushButton#segBtn {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 20px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#segBtn:hover {{
    color: {t["text_primary"]};
}}
QPushButton#segBtn:checked {{
    background-color: {t["bg_elevated"]};
    color: {t["text_primary"]};
    border-color: {t["border_subtle"]};
    font-weight: 600;
}}
QPushButton#segBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* CTA principal único en la barra (índigo → cobalto, sin borde neón) */
QPushButton#compileBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["accent_grad_start"]}, stop:1 {t["accent_grad_end"]});
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 6px {s["4"]};
    min-height: 20px;
    font-weight: 600;
}}
QPushButton#compileBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["accent_grad_hover_start"]}, stop:1 {t["accent_grad_hover_end"]});
}}
QPushButton#compileBtn:pressed {{
    background-color: {t["accent_primary_pressed"]};
}}
QPushButton#compileBtn:focus {{
    border: 2px solid {t["focus_ring"]};
    padding: 4px 14px;
}}
QPushButton#compileBtn:disabled {{
    background: {t["bg_elevated"]};
    color: {t["text_disabled"]};
}}
QPushButton#stopBtn {{
    background-color: {t["danger_bg"]};
    color: {t["danger_text"]};
    border: 1px solid {t["danger_border"]};
    border-radius: 7px;
    padding: 5px 10px;
    min-height: 20px;
    font-weight: 600;
}}
QPushButton#stopBtn:hover {{
    background-color: {t["danger_border"]};
    color: #ffffff;
}}
QPushButton#stopBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Botones cuadrados de icono (30x30 ergonómicos, tonal sin recuadro duro) */
QPushButton#iconBtn {{
    background-color: transparent;
    color: {t["text_secondary"]};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 0px;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#iconBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#iconBtn:checked {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
}}
QPushButton#iconBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Botón compacto para cabecera de docks */
QPushButton#dockCloseBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 0px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
}}
QPushButton#dockCloseBtn:hover {{
    background-color: {t["bg_hover"]};
}}
QPushButton#dockCloseBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

QPushButton#zoomBtn {{
    background-color: transparent;
    color: {t["text_secondary"]};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    min-width: 48px;
    min-height: 22px;
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#zoomBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#zoomBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Paneles laterales (Dock) con cabecera personalizada */
QDockWidget {{
    color: {t["text_muted"]};
    border: none;
}}
QFrame#dockHeader {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
    border-right: 1px solid {t["border_subtle"]};
}}
QLabel#dockTitle {{
    color: {t["text_muted"]};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.7px;
}}
QLabel#dockSubtitle {{
    background-color: {t["bg_pill"]};
    color: {t["text_secondary"]};
    border-radius: 5px;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 500;
}}

QTreeView, QTreeWidget {{
    background-color: {t["bg_surface_alt"]};
    color: {t["text_secondary"]};
    border: none;
    border-right: 1px solid {t["border_subtle"]};
    padding: 6px {s["2"]};
    outline: none;
}}
QTreeView:focus, QTreeWidget:focus {{
    border-right: 2px solid {t["focus_ring"]};
}}
QTreeView::item, QTreeWidget::item {{
    padding: 5px {s["2"]};
    border-radius: 6px;
    margin: 1px 0px;
}}
QTreeView::item:hover, QTreeWidget::item:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    font-weight: 600;
}}
QTreeView::branch, QTreeWidget::branch {{
    background: transparent;
}}

/* Editor de código y pestañas múltiples */
QTabWidget#editorTabs {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QTabWidget#editorTabs::pane {{
    border: none;
    background-color: {t["bg_surface"]};
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
}}
QTabWidget#editorTabs::tab-bar {{
    alignment: left;
}}
QTabWidget#editorTabs > QTabBar {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    qproperty-drawBase: 0;
}}
QTabWidget#editorTabs > QTabBar::tab {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: none;
    border-right: 1px solid {t["border_subtle"]};
    border-top: 2px solid transparent;
    padding: 7px 10px 7px 12px;
    min-width: 96px;
    max-width: 220px;
    font-size: 12px;
    font-weight: 500;
}}
QTabWidget#editorTabs > QTabBar::tab:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QTabWidget#editorTabs > QTabBar::tab:selected {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border-top: 2px solid {t["accent_primary"]};
    font-weight: 600;
}}
QTabWidget#editorTabs QPlainTextEdit {{
    border: none;
    border-radius: 0px;
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
}}
QTabWidget#editorTabs QPlainTextEdit:focus {{
    border: none;
}}
QPushButton#tabAddBtn {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: none;
    border-radius: 6px;
    margin: 3px 6px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
}}
QPushButton#tabAddBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#tabCloseBtn {{
    background-color: transparent;
    border: none;
    border-radius: 4px;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0px;
    margin-left: 4px;
}}
QPushButton#tabCloseBtn:hover {{
    background-color: {t["bg_hover"]};
}}

QPlainTextEdit {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
    padding: 0px;
    selection-background-color: {t["selection_bg"]};
    selection-color: {t["selection_fg"]};
}}
QPlainTextEdit:focus {{
    border: 1px solid {t["border_default"]};
}}

/* Panel de Registro de compilación */
QFrame#logContainer {{
    background-color: {t["bg_chrome"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QFrame#logHeader {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
}}
QLabel#logTitle {{
    color: {t["text_secondary"]};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
QLabel#logBadgeError {{
    background-color: {t["danger_bg"]};
    color: {t["danger_text"]};
    border: none;
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#logBadgeWarn {{
    background-color: {t["warning_bg"]};
    color: {t["warning_text"]};
    border: none;
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QPlainTextEdit#logView {{
    background-color: {t["bg_chrome"]};
    color: {t["text_secondary"]};
    border: none;
    border-radius: 0px;
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
    padding: {s["2"]} {s["3"]};
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", "Monospace";
    font-size: 12px;
}}
QProgressBar#compileProgress {{
    background-color: {t["bg_elevated"]};
    border: none;
    border-radius: 2px;
    max-height: 3px;
    min-height: 3px;
}}
QProgressBar#compileProgress::chunk {{
    background-color: {t["accent_primary"]};
    border-radius: 2px;
}}

/* Visor PDF y Estados (Vacío / Carga / Error) */
QFrame#pdfViewerFrame {{
    background-color: {t["bg_canvas"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QFrame#pdfToolBar {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
}}
QFrame#pdfSearchBar {{
    background-color: {t["bg_surface"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}
QLineEdit#pdfPageInput {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 6px;
    padding: 2px 4px;
    min-height: 18px;
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11.5px;
    font-weight: 600;
}}
QLabel#pdfMetaLabel {{
    color: {t["text_muted"]};
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11.5px;
    font-weight: 500;
}}
QFrame#pdfViewerFrame QScrollArea {{
    background-color: {t["bg_canvas"]};
    border: none;
    border-radius: 0px;
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
}}
QScrollArea {{
    background-color: {t["bg_canvas"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QWidget#pdfCanvas {{
    background: transparent;
}}
QFrame#pdfEmptyCard {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 14px;
}}
QLabel#pdfEmptyTitle {{
    color: {t["text_primary"]};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#pdfEmptyDesc {{
    color: {t["text_muted"]};
    font-size: 13px;
}}
QFrame#pdfErrorCard {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["danger_border"]};
    border-radius: 14px;
}}
QLabel#pdfErrorTitle {{
    color: {t["danger_text"]};
    font-size: 15px;
    font-weight: 700;
}}

/* Barra de búsqueda y reemplazo */
QFrame#findBar {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QLabel#matchCount {{
    color: {t["text_muted"]};
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11.5px;
    font-weight: 600;
    padding: 0 6px;
    min-width: 54px;
}}
QLabel#matchCount[findState="notfound"] {{
    color: {t["danger_text"]};
}}

/* Burbuja Selene IA (borde sutil elegante, sin contorno neón) */
QFrame#aiBubble {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_default"]};
    border-radius: 14px;
}}
QLabel#aiTitle {{
    font-weight: 700;
    font-size: 13px;
    color: {t["text_primary"]};
}}
QTextBrowser#aiChatView {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
    padding: 6px 8px;
    selection-background-color: {t["selection_bg"]};
    selection-color: {t["selection_fg"]};
}}
QFrame#aiImageChip {{
    background-color: {t["bg_elevated"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
}}
QLabel#aiImageLabel {{
    color: {t["text_secondary"]};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#aiPkgBtn {{
    background-color: {t["success_bg"]};
    color: {t["success_text"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: 4px 10px;
    min-height: 20px;
    font-size: 11.5px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#aiPkgBtn:hover {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
}}
QPushButton#aiCompactBtn {{
    background-color: {t["bg_elevated"]};
    color: {t["text_secondary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: 4px 9px;
    min-height: 20px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#aiCompactBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
    border-color: {t["border_default"]};
}}
QPushButton#aiCompactBtn:disabled {{
    color: {t["text_disabled"]};
    background-color: {t["bg_surface_alt"]};
}}
QPushButton#aiChipBtn {{
    background-color: {t["bg_pill"]};
    color: {t["text_secondary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 11px;
    padding: 3px 9px;
    min-height: 18px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton#aiChipBtn:hover {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    border-color: {t["accent_primary"]};
}}
QPushButton#aiCtxBtn {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
    padding: 2px 8px;
    min-height: 18px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#aiCtxBtn:checked {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    border-color: {t["accent_primary"]};
}}
QLabel#fieldSuccess {{
    background-color: {t["success_bg"]};
    color: {t["success_text"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: {s["2"]} {s["3"]};
    font-size: 12px;
    font-weight: 500;
}}

/* Diálogos y formularios */
QLabel#dialogTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {t["text_primary"]};
}}
QLabel#dialogSubtitle {{
    font-size: 12.5px;
    color: {t["text_muted"]};
}}
QLabel#fieldLabel {{
    font-size: 12.5px;
    font-weight: 600;
    color: {t["text_secondary"]};
}}
QLabel#fieldHint {{
    font-size: 12px;
    color: {t["text_muted"]};
}}
QLabel#fieldError {{
    background-color: {t["danger_bg"]};
    color: {t["danger_text"]};
    border: 1px solid {t["danger_border"]};
    border-radius: 7px;
    padding: {s["2"]} {s["3"]};
    font-size: 12px;
    font-weight: 500;
}}

/* Entradas y botones generales */
QLineEdit, QComboBox {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 7px;
    padding: 6px 10px;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {t["focus_ring"]};
    padding: 5px 9px;
}}
QLineEdit[findState="notfound"] {{
    border: 1px solid {t["danger_border"]};
    background-color: {t["danger_bg"]};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
}}
QComboBox QAbstractItemView {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {s["1"]};
    selection-background-color: {t["accent_primary"]};
    selection-color: #ffffff;
    outline: none;
}}

QPushButton {{
    background-color: {t["bg_elevated"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: 6px {s["3"]};
    min-height: 20px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {t["bg_hover"]};
    border-color: {t["border_default"]};
    color: {t["text_primary"]};
}}
QPushButton:pressed {{
    background-color: {t["bg_active"]};
}}
QPushButton:focus {{
    border: 2px solid {t["focus_ring"]};
}}
QPushButton:disabled {{
    color: {t["text_disabled"]};
    background-color: {t["bg_surface_alt"]};
    border-color: {t["border_subtle"]};
}}

QPushButton#primaryBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["accent_grad_start"]}, stop:1 {t["accent_grad_end"]});
    color: #ffffff;
    border: none;
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["accent_grad_hover_start"]}, stop:1 {t["accent_grad_hover_end"]});
    color: #ffffff;
}}
QPushButton#primaryBtn:pressed {{
    background-color: {t["accent_primary_pressed"]};
}}
QPushButton#primaryBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Botón tonal de acento (Arreglar con IA sin duplicar alerta roja) */
QPushButton#aiActionBtn {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    border: none;
    border-radius: 7px;
    padding: 4px 10px;
    min-height: 20px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#aiActionBtn:hover {{
    background-color: {t["accent_soft_hover"]};
}}
QPushButton#aiActionBtn:focus {{
    border: 2px solid {t["focus_ring"]};
}}

/* Popup de autocompletado */
QListView {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: {s["1"]};
    outline: none;
}}
QListView::item {{
    padding: 5px 10px;
    border-radius: 5px;
}}
QListView::item:selected {{
    background-color: {t["accent_primary"]};
    color: #ffffff;
}}

/* Divisores */
QSplitter::handle {{
    background-color: transparent;
}}
QSplitter::handle:horizontal {{
    width: 6px;
}}
QSplitter::handle:vertical {{
    height: 6px;
}}
QSplitter::handle:hover {{
    background-color: {t["accent_primary"]};
    border-radius: 3px;
}}

/* Barras de desplazamiento minimalistas */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t["scroll_handle"]};
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t["scroll_handle_hover"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t["scroll_handle"]};
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t["scroll_handle_hover"]};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Barra de estado plana estilo IDE moderno (sin 6 cajas con borde) */
QStatusBar {{
    background-color: {t["bg_chrome"]};
    color: {t["text_muted"]};
    border-top: 1px solid {t["border_subtle"]};
    font-size: 12px;
    padding: 2px {s["2"]};
}}
QStatusBar::item {{
    border: none;
}}
QLabel#statusText {{
    background: transparent;
    color: {t["text_muted"]};
    padding: 2px 8px;
    font-size: 11.5px;
}}
QLabel#statusMono {{
    background: transparent;
    color: {t["text_secondary"]};
    padding: 2px 8px;
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11.5px;
}}
QFrame#statusSep {{
    background-color: {t["border_subtle"]};
    max-width: 1px;
    min-width: 1px;
    margin: 5px 0px;
}}
QLabel#statusBadge {{
    background-color: {t["bg_pill"]};
    color: {t["text_secondary"]};
    border: none;
    border-radius: 9px;
    padding: 2px 10px;
    margin: 2px 4px;
    font-size: 11.5px;
    font-weight: 500;
}}
QPushButton#statusToggleBtn {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: none;
    border-radius: 6px;
    padding: 2px 9px;
    margin: 2px 4px;
    font-size: 11.5px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton#statusToggleBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#statusToggleBtn:checked {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    font-weight: 600;
}}

/* Tooltips */
QToolTip {{
    background-color: {t["tooltip_bg"]};
    color: {t["tooltip_fg"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 6px;
    padding: 4px 8px;
}}

/* Herramientas visuales: Paleta de símbolos, Tablas y Bibliografía */
QFrame#toolCard {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 10px;
}}
QWidget#symbolTopBar {{
    background-color: {t["bg_surface_alt"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}
QFrame#symbolScrollCanvas {{
    background-color: {t["bg_surface_alt"]};
}}
QScrollArea#symbolScroll {{
    background-color: {t["bg_surface_alt"]};
    border: none;
    border-radius: 0px;
}}
QLabel#symbolSectionTitle {{
    color: {t["text_muted"]};
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.7px;
    padding: 6px 2px 2px 2px;
}}
QFrame#symbolPreviewBar {{
    background-color: {t["bg_surface"]};
    border-top: 1px solid {t["border_subtle"]};
}}
QLabel#symbolPreviewGlyph {{
    color: {t["accent_text"]};
    font-size: 16px;
    font-weight: 700;
    min-width: 26px;
}}
QLabel#symbolPreviewCmd {{
    color: {t["text_primary"]};
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11.5px;
    font-weight: 600;
}}
QLabel#symbolPreviewDesc {{
    color: {t["text_muted"]};
    font-size: 11px;
}}
QPushButton#symbolBtn {{
    background-color: {t["bg_surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: 2px 2px;
    min-width: 34px;
    min-height: 34px;
    font-size: 15px;
    font-weight: 500;
}}
QPushButton#symbolBtn:hover {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    border-color: {t["accent_primary"]};
}}
QPushButton#symbolBtn:pressed {{
    background-color: {t["accent_soft_hover"]};
}}
QPushButton#symbolCatBtn {{
    background-color: transparent;
    color: {t["text_muted"]};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 6px;
    min-height: 20px;
    font-size: 11.5px;
    font-weight: 500;
}}
QPushButton#symbolCatBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
}}
QPushButton#symbolCatBtn:checked {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    font-weight: 600;
}}
QTableWidget {{
    background-color: {t["bg_input"]};
    alternate-background-color: {t["bg_surface_alt"]};
    color: {t["text_primary"]};
    gridline-color: {t["border_subtle"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    selection-background-color: {t["accent_soft_bg"]};
    selection-color: {t["text_primary"]};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QHeaderView {{
    background-color: {t["bg_surface_alt"]};
}}
QTableCornerButton::section {{
    background-color: {t["bg_surface_alt"]};
    border: none;
    border-right: 1px solid {t["border_subtle"]};
    border-bottom: 1px solid {t["border_subtle"]};
}}
QHeaderView::section {{
    background-color: {t["bg_surface_alt"]};
    color: {t["text_secondary"]};
    border: none;
    border-right: 1px solid {t["border_subtle"]};
    border-bottom: 1px solid {t["border_subtle"]};
    padding: 5px 8px;
    font-size: 11.5px;
    font-weight: 600;
}}
QLabel#dimCountBadge {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 6px;
    padding: 2px 6px;
    min-width: 24px;
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#stepBtn {{
    background-color: {t["bg_elevated"]};
    color: {t["text_secondary"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 6px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
    font-weight: 700;
}}
QPushButton#stepBtn:hover {{
    background-color: {t["bg_hover"]};
    color: {t["text_primary"]};
    border-color: {t["border_default"]};
}}
QListWidget#bibList {{
    background-color: {t["bg_surface_alt"]};
    color: {t["text_primary"]};
    border: none;
    padding: 4px;
    outline: none;
}}
QListWidget#bibList::item {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_subtle"]};
    border-radius: 7px;
    padding: 7px 9px;
    margin: 3px 2px;
}}
QListWidget#bibList::item:hover {{
    border-color: {t["border_strong"]};
    background-color: {t["bg_elevated"]};
}}
QListWidget#bibList::item:selected {{
    background-color: {t["accent_soft_bg"]};
    border-color: {t["accent_primary"]};
    color: {t["text_primary"]};
}}
QSpinBox {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 7px;
    padding: 4px 8px;
    min-height: 20px;
}}
QCheckBox {{
    color: {t["text_secondary"]};
    spacing: 8px;
    font-size: 12.5px;
}}
QCheckBox:hover {{
    color: {t["text_primary"]};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1.5px solid {t["border_strong"]};
    background-color: {t["bg_input"]};
}}
QCheckBox::indicator:hover {{
    border-color: {t["accent_primary"]};
}}
QCheckBox::indicator:checked {{
    background-color: {t["accent_primary"]};
    border-color: {t["accent_primary"]};
}}

/* Paleta de comandos (Ctrl+Shift+P) */
QFrame#commandPalette {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 12px;
}}
QLineEdit#paletteInput {{
    background-color: {t["bg_input"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border_default"]};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13.5px;
}}
QLineEdit#paletteInput:focus {{
    border: 2px solid {t["focus_ring"]};
    padding: 7px 11px;
}}
QListWidget#paletteList {{
    background-color: transparent;
    color: {t["text_primary"]};
    border: none;
    outline: none;
    padding: 2px 0px;
}}
QListWidget#paletteList::item {{
    border: none;
    background: transparent;
}}

/* Tarjeta flotante de previsualización de fórmulas y TikZ */
QFrame#mathPreviewCard {{
    background-color: {t["bg_surface"]};
    border: 1px solid {t["border_strong"]};
    border-radius: 12px;
}}
QLabel#mathPreviewBadge {{
    background-color: {t["accent_soft_bg"]};
    color: {t["accent_text"]};
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 10.5px;
    font-weight: 700;
}}
"""


DARK_STYLESHEET = build_stylesheet("dark")
LIGHT_STYLESHEET = build_stylesheet("light")


def make_format(color, bold=False, italic=False):
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

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)


class LogHighlighter(QSyntaxHighlighter):
    """Resalta errores, advertencias, líneas clicables y éxitos en el log de LuaLaTeX."""

    def __init__(self, parent=None):
        self.rules = []
        super().__init__(parent)
        self.set_theme("dark")

    def set_theme(self, theme_name: str):
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        err_fmt = make_format(t["danger_text"], bold=True)
        warn_fmt = make_format(t["warning_text"], bold=True)
        ok_fmt = make_format(t["success_text"], bold=True)
        ref_fmt = make_format(t["accent_text"], bold=True)

        self.rules = [
            (re.compile(r"(?:^!.*|Error en la compilación|Undefined control sequence.*|Emergency stop.*|Fatal error.*)"), err_fmt),
            (re.compile(r"(?:LaTeX Warning:.*|Package .* Warning:.*|Overfull \\[hv]box.*|Underfull \\[hv]box.*)"), warn_fmt),
            (re.compile(r"(?:Compilación Exitosa|Output written on .*)"), ok_fmt),
            (re.compile(r"(?:[^\s:]+\.tex:\d+|^l\.\d+)"), ref_fmt),
        ]
        self.rehighlight()

    def highlightBlock(self, text: str):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
