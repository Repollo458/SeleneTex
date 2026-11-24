# This Python file uses the following encoding: utf-8
"""Previsualización rápida en vivo de fórmulas LaTeX y diagramas TikZ."""

from collections import OrderedDict
import hashlib
import pathlib
import re
import subprocess
import tempfile

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from highlighter import SEMANTIC_TOKENS
from icons import svg_icon

PREVIEW_ENVIRONMENTS = {
    "equation", "equation*",
    "align", "align*",
    "gather", "gather*",
    "multline", "multline*",
    "flalign", "flalign*",
    "alignat", "alignat*",
    "eqnarray", "eqnarray*",
    "displaymath", "math",
    "tikzpicture", "circuitikz", "pgfpicture",
}

SAFE_MATH_PACKAGES = {
    "amsmath", "amssymb", "amsthm", "mathtools", "physics", "siunitx",
    "bm", "cancel", "mathrsfs", "stmaryrd", "esint", "tikz", "pgfplots",
    "circuitikz", "xcolor", "mhchem", "chemfig", "braket", "nicematrix",
    "dsfont", "bbm", "amsfonts", "extarrows", "stackrel",
}

_PREVIEW_CACHE: OrderedDict[tuple[str, str], QPixmap] = OrderedDict()
_MAX_PREVIEW_CACHE = 64


def _is_escaped(text: str, pos: int) -> bool:
    count = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        count += 1
        i -= 1
    return (count % 2) == 1


def _in_line_comment(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    i = line_start
    while i < pos:
        if text[i] == "%" and not _is_escaped(text, i):
            return True
        i += 1
    return False


def extract_math_at_cursor(text: str, cursor_pos: int, selected_text: str = "") -> tuple[str, str] | None:
    """Detecta la fórmula o entorno TikZ bajo el cursor (o selección).

    Devuelve (fragmento_latex, etiqueta_tipo) o None si el cursor no está en un bloque matemático.
    """
    sel = selected_text.replace("\u2029", "\n").strip()
    if sel:
        if re.search(r"\\begin\{(?:tikz|pgf|circuitikz)", sel):
            return (sel, "Diagrama TikZ")
        if (
            sel.startswith("$")
            or sel.startswith(r"\[")
            or sel.startswith(r"\(")
            or sel.startswith(r"\begin{")
        ):
            return (sel, "Selección")
        # Si parece expresión matemática sin delimitadores, envolver en \[ ... \]
        if any(tok in sel for tok in ("\\", "^", "_", "=", "+", "-", "/", "{")):
            return (f"\\[\n{sel}\n\\]", "Selección")
        return None

    if not text:
        return None
    pos = max(0, min(cursor_pos, len(text)))
    if _in_line_comment(text, pos):
        return None

    # 1. Entornos matemáticos o TikZ (\begin{env} ... \end{env})
    env_names = "|".join(re.escape(e) for e in sorted(PREVIEW_ENVIRONMENTS, key=len, reverse=True))
    env_re = re.compile(rf"\\begin\{{({env_names})\}}(.*?)\\end\{{\1\}}", re.DOTALL)
    for m in env_re.finditer(text):
        if m.start() <= pos <= m.end():
            env = m.group(1)
            snippet = m.group(0).strip()
            if "tikz" in env or "pgf" in env:
                return (snippet, f"TikZ ({env})")
            return (snippet, f"Entorno {env}")

    # 2. Display math \[ ... \]
    for m in re.finditer(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", text, re.DOTALL):
        if m.start() <= pos <= m.end():
            if m.group(1).strip():
                return (m.group(0).strip(), "Fórmula en bloque")

    # 3. Display math $$ ... $$
    for m in re.finditer(r"(?<!\\)\$\$(.*?)(?<!\\)\$\$", text, re.DOTALL):
        if m.start() <= pos <= m.end():
            if m.group(1).strip():
                inner = m.group(1).strip()
                return (f"\\[\n{inner}\n\\]", "Fórmula en bloque")

    # 4. Inline math \( ... \)
    for m in re.finditer(r"(?<!\\)\\\((.*?)(?<!\\)\\\)", text, re.DOTALL):
        if m.start() <= pos <= m.end():
            if m.group(1).strip():
                return (m.group(0).strip(), "Fórmula en línea")

    # 5. Inline math $ ... $ (escaneo seguro dentro de la ventana cercana al cursor)
    win_start = max(0, text.rfind("\n\n", 0, pos))
    win_end = text.find("\n\n", pos)
    if win_end == -1:
        win_end = len(text)
    segment = text[win_start:win_end]
    rel_pos = pos - win_start

    i = 0
    n = len(segment)
    open_idx = -1
    while i < n:
        ch = segment[i]
        if ch == "%" and not _is_escaped(segment, i):
            nl = segment.find("\n", i)
            if nl == -1:
                break
            i = nl + 1
            continue
        if ch == "$" and not _is_escaped(segment, i):
            if i + 1 < n and segment[i + 1] == "$":
                i += 2
                continue
            if open_idx == -1:
                open_idx = i
            else:
                close_idx = i
                if open_idx <= rel_pos <= close_idx + 1:
                    inner = segment[open_idx + 1 : close_idx].strip()
                    if inner:
                        return (f"${inner}$", "Fórmula en línea")
                open_idx = -1
        i += 1

    return None


def extract_safe_math_preamble(doc_text: str, snippet: str) -> str:
    """Extrae paquetes matemáticos seguros y macros del usuario desde el preámbulo."""
    preamble = doc_text.split(r"\begin{document}", 1)[0] if r"\begin{document}" in doc_text else ""
    clean = re.sub(r"(?<!\\)%[^\n]*", "", preamble)

    pkgs: list[str] = ["amsmath", "amssymb", "mathtools"]
    seen = set(pkgs)

    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", clean):
        for raw in m.group(1).split(","):
            pkg = raw.strip()
            if pkg in SAFE_MATH_PACKAGES and pkg not in seen:
                seen.add(pkg)
                pkgs.append(pkg)

    if any(k in snippet for k in ("tikzpicture", "tikz")):
        if "tikz" not in seen:
            pkgs.append("tikz")
            seen.add("tikz")
    if "circuitikz" in snippet and "circuitikz" not in seen:
        pkgs.append("circuitikz")
        seen.add("circuitikz")
    if "axis" in snippet and "pgfplots" not in seen and "tikzpicture" in snippet:
        pkgs.append("pgfplots")
        seen.add("pgfplots")

    lines = [f"\\usepackage{{{p}}}" for p in pkgs]
    if "pgfplots" in seen:
        lines.append(r"\pgfplotsset{compat=1.18}")

    # Copiar \usetikzlibrary y macros del usuario (\newcommand, \DeclareMathOperator)
    for line in clean.splitlines():
        s = line.strip()
        if s.startswith((r"\usetikzlibrary", r"\DeclareMathOperator", r"\newcommand", r"\providecommand")):
            lines.append(s)

    return "\n".join(lines)


def build_standalone_tex(snippet: str, extra_preamble: str) -> str:
    """Construye un documento standalone mínimo listo para compilar rápido con pdflatex."""
    is_tikz = any(k in snippet for k in (r"\begin{tikzpicture}", r"\begin{circuitikz}", r"\begin{pgfpicture}"))
    if is_tikz:
        doc_cls = r"\documentclass[border=8pt]{standalone}"
        body = snippet
    else:
        doc_cls = r"\documentclass[preview,border=8pt]{standalone}"
        # Añadimos \displaystyle a fórmulas inline para legibilidad
        if snippet.startswith("$") and snippet.endswith("$") and not snippet.startswith("$$"):
            inner = snippet[1:-1].strip()
            body = f"$\\displaystyle {inner}$"
        elif snippet.startswith(r"\(") and snippet.endswith(r"\)"):
            inner = snippet[2:-2].strip()
            body = f"$\\displaystyle {inner}$"
        else:
            body = snippet

    return (
        f"{doc_cls}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T1]{fontenc}\n"
        f"{extra_preamble}\n"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n"
    )


def _tight_crop_white_margin(image: QImage, pad_px: int = 16) -> QImage:
    """Recorta los márgenes blancos sobrantes dejando un relleno uniforme alrededor de la fórmula."""
    w, h = image.width(), image.height()
    if w == 0 or h == 0:
        return image
    # Muestreo rápido sobre bytes RGB888 para detectar la caja exacta de tinta (< 248)
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    stride = rgb.bytesPerLine()
    buf = bytes(rgb.constBits())

    min_x, min_y = w, h
    max_x, max_y = -1, -1
    for y in range(h):
        row = buf[y * stride : y * stride + w * 3]
        # Comprobación rápida de fila completamente blanca
        if row == b"\xff" * (w * 3):
            continue
        for x in range(w):
            i = x * 3
            if row[i] < 248 or row[i + 1] < 248 or row[i + 2] < 248:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y

    if max_x < min_x or max_y < min_y:
        return image

    x0 = max(0, min_x - pad_px)
    y0 = max(0, min_y - pad_px)
    x1 = min(w, max_x + 1 + pad_px)
    y1 = min(h, max_y + 1 + pad_px)
    return rgb.copy(x0, y0, x1 - x0, y1 - y0)


def _theme_render_pixmap(pdf_path: pathlib.Path, dark_mode: bool, dpr: float = 2.0) -> QPixmap:
    eff_dpr = max(1.0, min(2.5, dpr))
    with fitz.open(pdf_path) as doc:
        page = doc[0]
        scale = 2.0 * eff_dpr
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888,
        ).copy()

    image = _tight_crop_white_margin(image, pad_px=int(round(10 * eff_dpr)))

    if dark_mode:
        # Invertir negro->blanco y tintar el fondo al color de la tarjeta oscura (#121728)
        image.invertPixels(QImage.InvertMode.InvertRgb)
        image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.fillRect(image.rect(), QColor("#121728"))
        painter.end()

    pm = QPixmap.fromImage(image)
    pm.setDevicePixelRatio(eff_dpr)
    return pm


class MathRenderWorker(QThread):
    """Compila un fragmento matemático/TikZ en segundo plano sin bloquear el editor."""

    rendered = Signal(int, QPixmap)
    failed = Signal(int, str)

    def __init__(
        self,
        request_id: int,
        tex_source: str,
        cache_key: tuple[str, str],
        dark_mode: bool,
        dpr: float = 2.0,
        parent=None,
    ):
        super().__init__(parent)
        self.request_id = request_id
        self.tex_source = tex_source
        self.cache_key = cache_key
        self.dark_mode = dark_mode
        self.dpr = dpr

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="selenetex_math_") as tmp:
                tdir = pathlib.Path(tmp)
                tex_file = tdir / "preview.tex"
                tex_file.write_text(self.tex_source, encoding="utf-8")

                proc = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "preview.tex"],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                pdf_file = tdir / "preview.pdf"
                if proc.returncode != 0 or not pdf_file.is_file():
                    err_line = self._extract_short_error(proc.stdout + "\n" + proc.stderr)
                    self.failed.emit(self.request_id, err_line)
                    return

                pm = _theme_render_pixmap(pdf_file, self.dark_mode, self.dpr)
                _PREVIEW_CACHE[self.cache_key] = pm
                while len(_PREVIEW_CACHE) > _MAX_PREVIEW_CACHE:
                    _PREVIEW_CACHE.popitem(last=False)
                self.rendered.emit(self.request_id, pm)
        except subprocess.TimeoutExpired:
            self.failed.emit(self.request_id, "Tiempo agotado al renderizar la fórmula.")
        except FileNotFoundError:
            self.failed.emit(self.request_id, "No se encontró pdflatex en el sistema.")
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc)[:140])

    @staticmethod
    def _extract_short_error(output: str) -> str:
        for line in output.splitlines():
            s = line.strip()
            if s.startswith("! "):
                return s[2:].strip()[:120]
        return "Error de sintaxis en la fórmula."


class MathPreviewPopup(QFrame):
    """Tarjeta flotante de vista previa en vivo para ecuaciones y diagramas TikZ."""

    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mathPreviewCard")
        self.setMinimumWidth(200)
        self.setMaximumWidth(480)
        self.setMaximumHeight(280)
        self._theme = "dark"
        self._current_pixmap: QPixmap | None = None

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)
        self._shadow = shadow

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 10)
        layout.setSpacing(6)

        # Cabecera compacta
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        self.lbl_kind = QLabel("Fórmula", self)
        self.lbl_kind.setObjectName("mathPreviewBadge")

        self.btn_copy_img = QPushButton(self)
        self.btn_copy_img.setObjectName("dockCloseBtn")
        self.btn_copy_img.setIconSize(QSize(13, 13))
        self.btn_copy_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_img.setToolTip("Copiar fórmula como imagen al portapapeles")
        self.btn_copy_img.clicked.connect(self._copy_image)
        self.btn_copy_img.setEnabled(False)

        self.btn_close = QPushButton(self)
        self.btn_close.setObjectName("dockCloseBtn")
        self.btn_close.setIconSize(QSize(13, 13))
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Cerrar vista previa")
        self.btn_close.clicked.connect(self._on_close)

        hdr.addWidget(self.lbl_kind)
        hdr.addStretch(1)
        hdr.addWidget(self.btn_copy_img)
        hdr.addWidget(self.btn_close)
        layout.addLayout(hdr)

        # Progreso fino durante compilación
        self.progress = QProgressBar(self)
        self.progress.setObjectName("compileProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Imagen renderizada o mensaje de error
        self.lbl_image = QLabel(self)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setMinimumHeight(34)
        self.lbl_image.setWordWrap(True)
        layout.addWidget(self.lbl_image)

        self.set_theme("dark")
        self.hide()

    def set_theme(self, theme_name: str):
        self._theme = theme_name
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        self.btn_copy_img.setIcon(svg_icon("copy", t["text_muted"], 13))
        self.btn_close.setIcon(svg_icon("close", t["text_muted"], 13))
        self._shadow.setColor(QColor(15, 23, 42, 125 if theme_name == "dark" else 40))

    def show_loading(self, kind_label: str):
        self.lbl_kind.setText(kind_label)
        self.progress.show()
        if self._current_pixmap is None:
            self.lbl_image.setObjectName("fieldHint")
            self.lbl_image.setText("Renderizando...")
        self.adjustSize()
        self.show()
        self.raise_()

    def show_pixmap(self, kind_label: str, pixmap: QPixmap):
        self.lbl_kind.setText(kind_label)
        self.progress.hide()
        self._current_pixmap = pixmap
        self.btn_copy_img.setEnabled(True)

        # Escalar suavemente si la fórmula o TikZ excede el ancho/alto máximo del popup
        max_w, max_h = 448, 220
        logical_w = pixmap.width() / pixmap.devicePixelRatio()
        logical_h = pixmap.height() / pixmap.devicePixelRatio()
        shown = pixmap
        if logical_w > max_w or logical_h > max_h:
            dpr = pixmap.devicePixelRatio()
            shown = pixmap.scaled(
                int(max_w * dpr),
                int(max_h * dpr),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            shown.setDevicePixelRatio(dpr)

        self.lbl_image.setText("")
        shown_w = int(round(shown.width() / shown.devicePixelRatio()))
        shown_h = int(round(shown.height() / shown.devicePixelRatio()))
        self.lbl_image.setMinimumSize(shown_w, shown_h)
        self.lbl_image.setPixmap(shown)
        self.adjustSize()
        self.resize(self.sizeHint())
        self.show()
        self.raise_()

    def show_error(self, kind_label: str, message: str):
        self.lbl_kind.setText(kind_label)
        self.progress.hide()
        self._current_pixmap = None
        self.btn_copy_img.setEnabled(False)
        self.lbl_image.setMinimumSize(0, 34)
        self.lbl_image.setPixmap(QPixmap())
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        self.lbl_image.setText(f"<span style='color:{t['danger_text']};font-size:11.5px;'>⚠ {message}</span>")
        self.adjustSize()
        self.resize(self.sizeHint())
        self.show()
        self.raise_()

    def _copy_image(self):
        if self._current_pixmap is None:
            return
        QApplication.clipboard().setPixmap(self._current_pixmap)

    def _on_close(self):
        self.hide()
        self.dismissed.emit()


def get_cached_preview(tex_source: str, theme_name: str) -> tuple[tuple[str, str], QPixmap | None]:
    digest = hashlib.sha256(tex_source.encode("utf-8")).hexdigest()[:20]
    key = (digest, theme_name)
    cached = _PREVIEW_CACHE.get(key)
    if cached is not None:
        _PREVIEW_CACHE.move_to_end(key)
    return key, cached
