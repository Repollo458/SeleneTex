# This Python file uses the following encoding: utf-8
import pathlib
import re
import subprocess
from PySide6.QtCore import QEvent, QRect, QRectF, QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QListView,
    QPlainTextEdit,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolTip,
    QWidget,
)

from highlighter import SEMANTIC_TOKENS
from templates import LATEX_COMMANDS, PACKAGE_COMMANDS

_STRUCT_COMMANDS = {
    r"\documentclass", r"\usepackage", r"\title", r"\author", r"\date",
    r"\maketitle", r"\tableofcontents", r"\part", r"\chapter", r"\section",
    r"\subsection", r"\subsubsection", r"\paragraph", r"\input", r"\include",
    r"\label", r"\ref", r"\eqref", r"\cite", r"\caption", r"\bibliography",
    r"\bibliographystyle", r"\addbibresource", r"\printbibliography",
}

_MATH_PACKAGES = {"amsmath", "amssymb", "amsthm", "mathtools", "physics", "siunitx", "bm", "esint"}

_MATH_BASE_NAMES = {
    "frac", "dfrac", "tfrac", "sqrt", "sum", "int", "iint", "iiint", "oint",
    "prod", "lim", "inf", "sup", "partial", "nabla", "cdot", "cdots", "ldots",
    "times", "pm", "mp", "leq", "geq", "neq", "approx", "equiv", "sim", "in",
    "notin", "subset", "subseteq", "cup", "cap", "forall", "exists", "infty",
    "rightarrow", "leftarrow", "Rightarrow", "Leftarrow", "leftrightarrow",
    "mapsto", "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta",
    "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi",
    "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi",
    "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi",
    "Psi", "Omega", "mathbb", "mathcal", "mathrm", "mathbf", "mathfrak", "left",
    "right", "binom", "operatorname", "text", "hat", "bar", "vec", "tilde", "dot",
}

_AUTO_CLOSE_PAIRS = {"{": "}", "[": "]", "(": ")", "$": "$"}
_CLOSING_CHARS = set(_AUTO_CLOSE_PAIRS.values())
_MATCH_OPEN = {"{": "}", "[": "]", "(": ")"}
_MATCH_CLOSE = {"}": "{", "]": "[", ")": "("}
_LIST_ENVIRONMENTS = {"itemize", "enumerate", "description"}

_REF_CONTEXT_RE = re.compile(
    r"\\(?:eq|page|auto|name|c|C|v)?ref\*?(?:\[[^\]]*\])?\{([^}]*)$"
)
_CITE_CONTEXT_RE = re.compile(
    r"\\(?:paren|text|auto|foot|super|no|full|smart)?cite(?:author|year|title|[pt])?\*?(?:\[[^\]]*\])*\{([^}]*)$"
)
_BEGIN_LINE_RE = re.compile(
    r"\\begin\{([A-Za-z0-9*_-]+)\}(?:\[[^\]]*\]|\{[^}]*\})*\s*$"
)

_LABEL_PREFIX_HINTS = {
    "fig": "figura",
    "eq": "ecuación",
    "eqn": "ecuación",
    "tab": "tabla",
    "tbl": "tabla",
    "sec": "sección",
    "subsec": "subsección",
    "ch": "capítulo",
    "chap": "capítulo",
    "lst": "código",
    "alg": "algoritmo",
    "thm": "teorema",
    "lem": "lema",
    "def": "definición",
    "app": "apéndice",
}


def _strip_comments(text: str) -> str:
    """Elimina comentarios de línea (% ...) preservando \\%."""
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def _is_escaped(text: str, pos: int) -> bool:
    """Devuelve True si la posición `pos` está precedida por un número impar de '\\'."""
    count = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        count += 1
        i -= 1
    return (count % 2) == 1


def _classify_command(cmd: str, source_pkg: str | None = None, is_user: bool = False) -> tuple[str, str]:
    """Clasifica un comando LaTeX en (categoría, etiqueta_fuente) para el completer."""
    if is_user:
        return ("user", "usuario")
    if cmd.startswith((r"\begin{", r"\end{")):
        return ("env", source_pkg or "entorno")
    base = re.split(r"[\{\[\s\*]", cmd, maxsplit=1)[0]
    if base in _STRUCT_COMMANDS:
        return ("struct", source_pkg or "estructura")
    base_name = base.lstrip("\\")
    if base_name in _MATH_BASE_NAMES or (source_pkg in _MATH_PACKAGES):
        return ("math", source_pkg or "math")
    return ("cmd", source_pkg or "comando")


class CompleterItemDelegate(QStyledItemDelegate):
    """Renderizado estilo IDE moderno para el popup de autocompletado de LaTeX."""

    _BADGE_GLYPH = {
        "env": "E",
        "math": "∑",
        "struct": "§",
        "user": "λ",
        "cmd": "\\",
        "ref": "#",
        "cite": "@",
    }

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 30)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        dark = self.editor.dark_mode
        t = SEMANTIC_TOKENS["dark" if dark else "light"]
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        kind, source_label = self.editor._command_meta.get(text, _classify_command(text))

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        rect = option.rect.adjusted(4, 1, -4, -1)

        # 1. Fondo de fila (selección tonal + barra de acento izquierda)
        if is_selected:
            bg = QColor("#1f2a4d") if dark else QColor("#e0e7ff")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 6.0, 6.0)

            bar_color = QColor("#818cf8") if dark else QColor("#4f46e5")
            painter.setBrush(bar_color)
            bar_rect = QRectF(rect.left() + 1, rect.top() + 5, 3.0, rect.height() - 10)
            painter.drawRoundedRect(bar_rect, 1.5, 1.5)
        elif is_hovered:
            bg = QColor("#192038") if dark else QColor("#f1f4fa")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 6.0, 6.0)

        # 2. Badge de categoría a la izquierda (20x20 squircle)
        badge_colors = {
            "env": "#a5b4fc" if dark else "#4f46e5",
            "math": "#6ee7b7" if dark else "#059669",
            "struct": "#fde047" if dark else "#b45309",
            "user": "#7dd3fc" if dark else "#2563eb",
            "cmd": "#7dd3fc" if dark else "#2563eb",
            "ref": "#f472b6" if dark else "#db2777",
            "cite": "#fbbf24" if dark else "#d97706",
        }
        cat_color = QColor(badge_colors.get(kind, t["accent_text"]))
        badge_bg = QColor(cat_color)
        badge_bg.setAlpha(36 if dark else 28)

        badge_size = 20
        bx = rect.left() + 10
        by = rect.top() + (rect.height() - badge_size) // 2
        badge_rect = QRectF(bx, by, badge_size, badge_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(badge_bg)
        painter.drawRoundedRect(badge_rect, 5.0, 5.0)

        badge_font = QFont(self.editor.font().family(), 9)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(cat_color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._BADGE_GLYPH.get(kind, "\\"))

        # 3. Etiqueta de fuente/categoría alineada a la derecha
        tag_font = QFont("Inter", 8)
        if not QFontMetrics(tag_font).inFont("a"):
            tag_font = QFont(option.font)
            tag_font.setPointSize(8)
        tag_font.setWeight(QFont.Weight.Medium)
        tag_fm = QFontMetrics(tag_font)
        shown_tag = source_label
        if len(shown_tag) > 22:
            shown_tag = shown_tag[:21] + "…"
        tag_w = tag_fm.horizontalAdvance(shown_tag) + 12
        tag_rect = QRect(rect.right() - tag_w - 6, rect.top(), tag_w, rect.height())

        # 4. Texto del comando con prefijo resaltado y argumentos {} suavizados
        cmd_font = QFont(self.editor.font())
        cmd_font.setPointSize(max(9, min(11, self.editor.font().pointSize())))
        cmd_fm = QFontMetrics(cmd_font)
        bold_font = QFont(cmd_font)
        bold_font.setBold(True)
        bold_fm = QFontMetrics(bold_font)

        text_left = bx + badge_size + 10
        text_right = tag_rect.left() - 8
        avail_w = max(40, text_right - text_left)

        prefix = self.editor.completer.completionPrefix() or ""
        match_len = len(prefix) if prefix and text.lower().startswith(prefix.lower()) else 0

        # Separar parte principal y placeholders finales ({} / [...]) solo en modo comando
        arg_idx = len(text)
        if kind not in ("ref", "cite"):
            m_arg = re.search(r"(\[[^\]]*\]|\{\})+$", text)
            if m_arg and m_arg.start() >= match_len:
                arg_idx = m_arg.start()

        part_match = text[:match_len]
        part_rest = text[match_len:arg_idx]
        part_args = text[arg_idx:]

        col_match = QColor("#7dd3fc") if dark else QColor("#1d4ed8")
        col_primary = QColor(t["text_primary"])
        col_args = QColor("#94a3b8") if dark else QColor("#64748b")

        x = text_left
        baseline_y = rect.top() + (rect.height() + cmd_fm.ascent() - cmd_fm.descent()) // 2

        painter.save()
        painter.setClipRect(QRect(text_left, rect.top(), avail_w, rect.height()))
        if part_match:
            painter.setFont(bold_font)
            painter.setPen(col_match)
            painter.drawText(x, baseline_y, part_match)
            x += bold_fm.horizontalAdvance(part_match)

        if part_rest:
            painter.setFont(cmd_font)
            painter.setPen(col_primary)
            painter.drawText(x, baseline_y, part_rest)
            x += cmd_fm.horizontalAdvance(part_rest)

        if part_args:
            painter.setFont(cmd_font)
            painter.setPen(col_args)
            painter.drawText(x, baseline_y, part_args)
        painter.restore()

        # Pintar etiqueta derecha si cabe holgadamente
        if rect.width() >= 200:
            painter.setFont(tag_font)
            tag_color = (
                QColor("#94a3b8" if not is_selected else "#cbd5e1")
                if dark
                else QColor("#64748b" if not is_selected else "#4338ca")
            )
            painter.setPen(tag_color)
            painter.drawText(
                tag_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                shown_tag,
            )

        painter.restore()


_STY_COMMANDS_CACHE: dict[str, set[str]] = {}
_BIB_FILE_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def _scan_sty_commands(pkg_name: str) -> set[str]:
    """Extrae comandos públicos de un .sty instalado en TeX Live (con caché)."""
    if pkg_name in _STY_COMMANDS_CACHE:
        return _STY_COMMANDS_CACHE[pkg_name]
    cmds: set[str] = set()
    try:
        res = subprocess.run(
            ["kpsewhich", f"{pkg_name}.sty"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        sty_path = res.stdout.strip()
        if sty_path and pathlib.Path(sty_path).is_file():
            content = pathlib.Path(sty_path).read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(
                r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\{?(\\[A-Za-z]{2,})\}?(?:\[(\d)\])?",
                content,
            ):
                name = m.group(1)
                n_args = int(m.group(2)) if m.group(2) else 0
                cmds.add(name + ("{}" * min(n_args, 3)))
            for m in re.finditer(
                r"\\(?:New|Renew|Provide)DocumentCommand\{?(\\[A-Za-z]{2,})\}?\{([^}]*)\}",
                content,
            ):
                name = m.group(1)
                n_mandatory = m.group(2).count("m")
                cmds.add(name + ("{}" * min(n_mandatory, 3)))
            for m in re.finditer(
                r"\\newenvironment\*?\{([A-Za-z]{2,})\}",
                content,
            ):
                env = m.group(1)
                cmds.add(rf"\begin{{{env}}}")
                cmds.add(rf"\end{{{env}}}")
    except Exception:
        pass
    _STY_COMMANDS_CACHE[pkg_name] = cmds
    return cmds


def extract_document_packages(text: str) -> list[str]:
    """Devuelve los paquetes y clases relevantes incluidos en un documento LaTeX."""
    clean = _strip_comments(text)
    found: list[str] = []
    seen: set[str] = set()

    cls_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", clean)
    if cls_match:
        cls_name = cls_match.group(1).strip()
        if cls_name and cls_name not in seen:
            seen.add(cls_name)
            found.append(cls_name)

    for m in re.finditer(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}", clean):
        for raw_pkg in m.group(1).split(","):
            pkg = raw_pkg.strip()
            if pkg and pkg not in seen:
                seen.add(pkg)
                found.append(pkg)
    return found


def extract_labels(text: str, source_name: str = "") -> dict[str, str]:
    """Extrae todos los \\label{...} de un texto LaTeX junto a una pista descriptiva."""
    clean = _strip_comments(text)
    labels: dict[str, str] = {}
    for m in re.finditer(r"\\label\{([^{}\s]+)\}", clean):
        key = m.group(1).strip()
        if not key or key in labels:
            continue
        hint = "label"
        if ":" in key:
            prefix = key.split(":", 1)[0].lower()
            hint = _LABEL_PREFIX_HINTS.get(prefix, prefix)
        if source_name:
            labels[key] = f"{hint} · {source_name}" if hint != "label" else source_name
        else:
            labels[key] = hint
    return labels


def extract_bib_entries(bib_text: str) -> dict[str, str]:
    """Extrae claves BibTeX (@type{key, ...}) y un resumen compacto (autor/año o tipo)."""
    entries: dict[str, str] = {}
    entry_re = re.compile(r"@([A-Za-z]+)\s*[\{\(]\s*([^,\s\}\)]+)\s*,", re.MULTILINE)
    matches = list(entry_re.finditer(bib_text))
    for i, m in enumerate(matches):
        entry_type = m.group(1).lower()
        if entry_type in ("string", "preamble", "comment"):
            continue
        key = m.group(2).strip()
        if not key:
            continue
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(bib_text)
        body = bib_text[m.end():end_pos]

        year_m = re.search(r"\byear\s*=\s*[\{\"]?(\d{4})", body, re.IGNORECASE)
        author_m = re.search(r"\b(?:author|editor)\s*=\s*[\{\"]([^\}\"]+)", body, re.IGNORECASE)
        author_short = ""
        if author_m:
            first_author = author_m.group(1).split(" and ")[0].strip()
            first_author = re.sub(r"[\{\}\\]", "", first_author)
            if "," in first_author:
                author_short = first_author.split(",", 1)[0].strip()
            else:
                parts = first_author.split()
                author_short = parts[-1] if parts else ""

        year_str = year_m.group(1) if year_m else ""
        if author_short and year_str:
            tag = f"{author_short} {year_str}"
        elif author_short:
            tag = author_short
        elif year_str:
            tag = f"{entry_type} · {year_str}"
        else:
            tag = entry_type
        entries[key] = tag
    return entries


def _read_bib_cached(bib_path: pathlib.Path) -> dict[str, str]:
    try:
        resolved = bib_path.resolve()
        mtime = resolved.stat().st_mtime
        key = str(resolved)
        cached = _BIB_FILE_CACHE.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        text = resolved.read_text(encoding="utf-8", errors="ignore")
        parsed = extract_bib_entries(text)
        _BIB_FILE_CACHE[key] = (mtime, parsed)
        return parsed
    except OSError:
        return {}


def collect_project_labels(
    current_text: str,
    open_texts: list[tuple[pathlib.Path | None, str]],
    base_dir: pathlib.Path | None,
) -> dict[str, str]:
    """Reúne todos los \\label{} del documento actual, pestañas abiertas y subarchivos \\input/\\include."""
    labels = extract_labels(current_text)
    visited_paths: set[pathlib.Path] = set()
    tex_sources = [current_text]

    for path, txt in open_texts:
        if path is not None:
            try:
                visited_paths.add(path.resolve())
            except OSError:
                pass
            if path.suffix.lower() in (".tex", ".sty", ".cls"):
                tex_sources.append(txt)
                for k, v in extract_labels(txt, path.name).items():
                    labels.setdefault(k, v)
        else:
            tex_sources.append(txt)
            for k, v in extract_labels(txt).items():
                labels.setdefault(k, v)

    if base_dir is not None and base_dir.is_dir():
        input_re = re.compile(r"\\(?:input|include)\{([^}]+)\}")
        queue: list[pathlib.Path] = []
        for src in tex_sources:
            for m in input_re.finditer(_strip_comments(src)):
                rel = m.group(1).strip()
                sub = base_dir / rel
                if sub.suffix == "":
                    sub = sub.with_suffix(".tex")
                queue.append(sub)

        scanned = 0
        while queue and scanned < 32:
            sub = queue.pop(0)
            try:
                resolved = sub.resolve()
            except OSError:
                continue
            if resolved in visited_paths or not resolved.is_file():
                continue
            visited_paths.add(resolved)
            scanned += 1
            try:
                sub_text = resolved.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for k, v in extract_labels(sub_text, resolved.name).items():
                labels.setdefault(k, v)
            for m in input_re.finditer(_strip_comments(sub_text)):
                rel = m.group(1).strip()
                nxt = base_dir / rel
                if nxt.suffix == "":
                    nxt = nxt.with_suffix(".tex")
                queue.append(nxt)

    return labels


def collect_project_citations(
    current_text: str,
    open_texts: list[tuple[pathlib.Path | None, str]],
    base_dir: pathlib.Path | None,
) -> dict[str, str]:
    """Reúne claves BibTeX de pestañas .bib abiertas, \\bibliography/\\addbibresource y carpeta del proyecto."""
    citations: dict[str, str] = {}
    open_bib_paths: set[pathlib.Path] = set()
    tex_sources = [current_text]

    for path, txt in open_texts:
        if path is not None and path.suffix.lower() == ".bib":
            try:
                open_bib_paths.add(path.resolve())
            except OSError:
                pass
            citations.update(extract_bib_entries(txt))
        else:
            tex_sources.append(txt)

    bib_candidates: list[pathlib.Path] = []
    if base_dir is not None and base_dir.is_dir():
        bib_res_re = re.compile(r"\\(?:addbibresource|bibliography)(?:\[[^\]]*\])?\{([^}]+)\}")
        for src in tex_sources:
            for m in bib_res_re.finditer(_strip_comments(src)):
                for raw in m.group(1).split(","):
                    name = raw.strip()
                    if not name:
                        continue
                    p = base_dir / name
                    if p.suffix == "":
                        p = p.with_suffix(".bib")
                    bib_candidates.append(p)

        # Incluir .bib en la raíz del proyecto y subcarpeta bib/ si existe
        for folder in (base_dir, base_dir / "bib", base_dir / "bibliography"):
            if folder.is_dir():
                try:
                    for p in sorted(folder.glob("*.bib"))[:12]:
                        bib_candidates.append(p)
                except OSError:
                    pass

    seen_bibs: set[pathlib.Path] = set(open_bib_paths)
    for bib_path in bib_candidates:
        try:
            resolved = bib_path.resolve()
        except OSError:
            continue
        if resolved in seen_bibs or not resolved.is_file():
            continue
        seen_bibs.add(resolved)
        for k, v in _read_bib_cached(resolved).items():
            citations.setdefault(k, v)

    return citations


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            tip = self.code_editor.diagnostic_tooltip_at_y(event.pos().y())
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class CodeEditor(QPlainTextEdit):
    file_dropped = Signal(str)
    font_size_changed = Signal(int)
    ai_action_requested = Signal(str, str)  # (action_kind, prompt_text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Editor de código LaTeX")
        self.document().setDocumentMargin(10)
        self.document().setModified(False)
        self.line_number_area = LineNumberArea(self)
        self.dark_mode = True
        self._base_font_size = 11
        self._tab_width = 4
        self.auto_close_enabled = True
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._diagnostics: dict[int, list[tuple[str, str]]] = {}
        self._project_context_provider = None
        self._completion_mode = "cmd"  # "cmd", "ref", "cite"
        self.file_path: pathlib.Path | None = None
        self.highlighter = None

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        self._command_meta: dict[str, tuple[str, str]] = {
            cmd: _classify_command(cmd) for cmd in LATEX_COMMANDS
        }
        self._cmd_list_cache: list[str] = sorted(set(LATEX_COMMANDS))
        self._cmd_meta_cache: dict[str, tuple[str, str]] = dict(self._command_meta)

        self.completer_model = QStringListModel(self._cmd_list_cache, self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setMaxVisibleItems(8)
        self.completer.activated.connect(self.insert_completion)

        popup = QListView()
        popup.setObjectName("completerPopup")
        popup.setUniformItemSizes(True)
        popup.setMouseTracking(True)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.completer.setPopup(popup)
        # IMPORTANTE: QCompleter.setPopup() reemplaza el delegate; hay que asignarlo DESPUÉS
        self.completer_delegate = CompleterItemDelegate(self)
        self.completer.popup().setItemDelegate(self.completer_delegate)
        self._style_completer_popup()

        self._commands_dirty = True
        self.textChanged.connect(self._mark_commands_dirty)

    def set_project_context_provider(self, provider):
        """Asigna un callable que devuelve {'open_texts': [...], 'base_dir': Path | None}."""
        self._project_context_provider = provider

    def _style_completer_popup(self):
        t = SEMANTIC_TOKENS["dark" if self.dark_mode else "light"]
        popup = self.completer.popup()
        popup.setStyleSheet(f"""
            QListView#completerPopup {{
                background-color: {t["bg_surface"]};
                color: {t["text_primary"]};
                border: 1px solid {t["border_default"]};
                border-radius: 10px;
                padding: 4px 0px;
                outline: none;
            }}
            QListView#completerPopup::item {{
                border: none;
                background: transparent;
            }}
            QListView#completerPopup QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px 4px 0px;
            }}
            QListView#completerPopup QScrollBar::handle:vertical {{
                background: {t["scroll_handle"]};
                min-height: 24px;
                border-radius: 3px;
            }}
            QListView#completerPopup QScrollBar::handle:vertical:hover {{
                background: {t["scroll_handle_hover"]};
            }}
            QListView#completerPopup QScrollBar::add-line:vertical,
            QListView#completerPopup QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        popup.viewport().update()

    def setFont(self, font):
        super().setFont(font)
        if font.pointSize() > 0:
            self._base_font_size = font.pointSize()
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)
        self.update_line_number_area_width(0)

    def set_tab_width(self, spaces: int):
        self._tab_width = max(2, min(8, int(spaces)))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)

    def set_word_wrap(self, enabled: bool):
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def set_auto_close_enabled(self, enabled: bool):
        self.auto_close_enabled = bool(enabled)

    def set_font_point_size(self, point_size: int):
        new_size = max(8, min(28, point_size))
        font = self.font()
        if font.pointSize() == new_size:
            return
        font.setPointSize(new_size)
        super().setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self._tab_width)
        self.update_line_number_area_width(0)

    def adjust_font_size(self, delta: int):
        font = self.font()
        size = font.pointSize() if font.pointSize() > 0 else self._base_font_size
        new_size = max(8, min(28, size + delta))
        self.set_font_point_size(new_size)
        self.font_size_changed.emit(new_size)

    def reset_font_size(self):
        self.set_font_point_size(self._base_font_size)
        self.font_size_changed.emit(self._base_font_size)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self.adjust_font_size(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def _mark_commands_dirty(self):
        self._commands_dirty = True

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 30 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area_width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        tokens = SEMANTIC_TOKENS["dark" if self.dark_mode else "light"]
        bg_color = QColor(tokens["gutter_bg"])
        border_color = QColor(tokens["gutter_border"])
        fg_color = QColor(tokens["gutter_fg"])
        active_fg = QColor(tokens["gutter_active"])
        err_dot = QColor(tokens["danger_text"])
        warn_dot = QColor(tokens["warning_text"])

        painter.fillRect(event.rect(), bg_color)
        painter.setPen(border_color)
        w = self.line_number_area.width()
        painter.drawLine(w - 1, event.rect().top(), w - 1, event.rect().bottom())

        current_block_num = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        line_h = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_num = block_number + 1
                diags = self._diagnostics.get(line_num)
                if diags:
                    has_err = any(sev == "error" for sev, _ in diags)
                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(err_dot if has_err else warn_dot)
                    dot_d = 6
                    dot_y = top + (line_h - dot_d) // 2
                    painter.drawEllipse(6, dot_y, dot_d, dot_d)
                    painter.restore()

                number = str(line_num)
                if diags:
                    has_err = any(sev == "error" for sev, _ in diags)
                    painter.setPen(err_dot if has_err else warn_dot)
                else:
                    painter.setPen(active_fg if block_number == current_block_num else fg_color)
                painter.drawText(
                    0,
                    top,
                    w - 10,
                    line_h,
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    # ------------------------------------------------------------------
    # Diagnósticos en línea (errores y avisos de LuaLaTeX)
    # ------------------------------------------------------------------
    def set_diagnostics(self, diagnostics: dict[int, list[tuple[str, str]]]):
        self._diagnostics = dict(diagnostics)
        self.highlight_current_line()
        self.line_number_area.update()

    def clear_diagnostics(self):
        if not self._diagnostics:
            return
        self._diagnostics.clear()
        self.highlight_current_line()
        self.line_number_area.update()

    def diagnostic_tooltip_at_y(self, y: int) -> str:
        if not self._diagnostics:
            return ""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid():
            if top <= y <= bottom:
                return self._format_line_diagnostics(block.blockNumber() + 1)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
        return ""

    def _format_line_diagnostics(self, line_num: int) -> str:
        diags = self._diagnostics.get(line_num)
        if not diags:
            return ""
        lines = []
        for sev, msg in diags[:6]:
            prefix = "Error" if sev == "error" else "Aviso"
            lines.append(f"[{prefix}] {msg}")
        return "\n".join(lines)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.ToolTip and self._diagnostics:
            cursor = self.cursorForPosition(event.pos())
            tip = self._format_line_diagnostics(cursor.blockNumber() + 1)
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def _build_diagnostic_selections(self) -> list[QTextEdit.ExtraSelection]:
        if not self._diagnostics:
            return []
        selections: list[QTextEdit.ExtraSelection] = []
        doc = self.document()
        err_bg = QColor(248, 113, 113, 28) if self.dark_mode else QColor(220, 38, 38, 22)
        warn_bg = QColor(251, 191, 36, 24) if self.dark_mode else QColor(217, 119, 6, 22)
        err_ul = QColor("#f87171") if self.dark_mode else QColor("#dc2626")
        warn_ul = QColor("#fbbf24") if self.dark_mode else QColor("#d97706")

        for line_num, items in self._diagnostics.items():
            block = doc.findBlockByLineNumber(line_num - 1)
            if not block.isValid():
                continue
            has_err = any(sev == "error" for sev, _ in items)

            # Tinte suave de fila completa
            row_sel = QTextEdit.ExtraSelection()
            row_sel.format.setBackground(err_bg if has_err else warn_bg)
            row_sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            row_cursor = QTextCursor(block)
            row_sel.cursor = row_cursor
            selections.append(row_sel)

            # Subrayado ondulado sobre el texto útil de la línea
            text = block.text()
            stripped = text.strip()
            if stripped:
                lead = len(text) - len(text.lstrip())
                trail = len(text.rstrip())
                wave_sel = QTextEdit.ExtraSelection()
                wave_sel.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                wave_sel.format.setUnderlineColor(err_ul if has_err else warn_ul)
                wc = QTextCursor(block)
                wc.setPosition(block.position() + lead)
                wc.setPosition(block.position() + trail, QTextCursor.MoveMode.KeepAnchor)
                wave_sel.cursor = wc
                selections.append(wave_sel)

        return selections

    # ------------------------------------------------------------------
    # Emparejado visual de delimitadores ({}, [], ())
    # ------------------------------------------------------------------
    def _find_matching_delimiter(self, text: str, pos: int) -> tuple[int, int] | None:
        """Devuelve (pos_origen, pos_pareja) o (pos_origen, -1) si no tiene pareja."""
        n = len(text)
        target_pos = -1
        for candidate in (pos - 1, pos):
            if 0 <= candidate < n and text[candidate] in (_MATCH_OPEN.keys() | _MATCH_CLOSE.keys()):
                if not _is_escaped(text, candidate):
                    target_pos = candidate
                    break
        if target_pos == -1:
            return None

        ch = text[target_pos]
        max_scan = 12000

        if ch in _MATCH_OPEN:
            closing = _MATCH_OPEN[ch]
            depth = 1
            limit = min(n, target_pos + max_scan)
            i = target_pos + 1
            while i < limit:
                c = text[i]
                if c == "%" and not _is_escaped(text, i):
                    nl = text.find("\n", i)
                    if nl == -1:
                        break
                    i = nl + 1
                    continue
                if not _is_escaped(text, i):
                    if c == ch:
                        depth += 1
                    elif c == closing:
                        depth -= 1
                        if depth == 0:
                            return (target_pos, i)
                i += 1
            return (target_pos, -1)

        opening = _MATCH_CLOSE[ch]
        depth = 1
        limit = max(0, target_pos - max_scan)
        i = target_pos - 1
        while i >= limit:
            c = text[i]
            if c in (ch, opening) and not _is_escaped(text, i):
                # Comprobar que no está dentro de un comentario en esa línea
                line_start = text.rfind("\n", 0, i) + 1
                in_comment = False
                j = line_start
                while j < i:
                    if text[j] == "%" and not _is_escaped(text, j):
                        in_comment = True
                        break
                    j += 1
                if not in_comment:
                    if c == ch:
                        depth += 1
                    elif c == opening:
                        depth -= 1
                        if depth == 0:
                            return (target_pos, i)
            i -= 1
        return (target_pos, -1)

    def _build_bracket_selections(self) -> list[QTextEdit.ExtraSelection]:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return []
        text = self.toPlainText()
        match = self._find_matching_delimiter(text, cursor.position())
        if match is None:
            return []

        src_pos, dst_pos = match
        selections: list[QTextEdit.ExtraSelection] = []

        if dst_pos != -1:
            bg = QColor("#2a3b6b") if self.dark_mode else QColor("#c7d2fe")
            fg = QColor("#f8fafc") if self.dark_mode else QColor("#1e1b4b")
            positions = (src_pos, dst_pos)
        else:
            bg = QColor("#5b1d2a") if self.dark_mode else QColor("#fecaca")
            fg = QColor("#fca5a5") if self.dark_mode else QColor("#991b1b")
            positions = (src_pos,)

        for p in positions:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(bg)
            sel.format.setForeground(fg)
            sel.format.setFontWeight(QFont.Weight.Bold)
            c = self.textCursor()
            c.setPosition(p)
            c.setPosition(p + 1, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            selections.append(sel)
        return selections

    def set_search_highlights(self, query: str, case_sensitive: bool = False, use_regex: bool = False) -> int:
        self._search_selections = []
        if not query:
            self.highlight_current_line()
            return 0
        re_flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            re_flags |= re.MULTILINE
        try:
            pattern = re.compile(query if use_regex else re.escape(query), re_flags)
        except re.error:
            self.highlight_current_line()
            return -1

        doc_text = self.toPlainText()
        hl_bg = QColor("#3a2e12") if self.dark_mode else QColor("#fef08a")
        hl_fg = QColor("#fde68a") if self.dark_mode else QColor("#713f12")
        count = 0
        for m in pattern.finditer(doc_text):
            if m.start() == m.end():
                continue
            count += 1
            if count <= 500:
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(hl_bg)
                sel.format.setForeground(hl_fg)
                c = self.textCursor()
                c.setPosition(m.start())
                c.setPosition(m.end(), c.MoveMode.KeepAnchor)
                sel.cursor = c
                self._search_selections.append(sel)
        self.highlight_current_line()
        return count

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            tokens = SEMANTIC_TOKENS["dark" if self.dark_mode else "light"]
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(tokens["editor_line_hl"])
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        extra_selections.extend(self._build_diagnostic_selections())
        extra_selections.extend(self._build_bracket_selections())
        extra_selections.extend(self._search_selections)
        self.setExtraSelections(extra_selections)
        self.line_number_area.update()

    def set_dark_mode(self, dark: bool):
        self.dark_mode = dark
        self.highlight_current_line()
        self.line_number_area.update()
        self._style_completer_popup()

    def go_to_line(self, line_number: int):
        block = self.document().findBlockByLineNumber(line_number - 1)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()
            self.setFocus()

    # ------------------------------------------------------------------
    # Autocompletado contextual (\comando, \ref{}, \cite{})
    # ------------------------------------------------------------------
    def _completion_context(self) -> tuple[str, str]:
        """Detecta si el cursor está en contexto 'ref', 'cite' o 'cmd' y devuelve (modo, prefijo)."""
        cursor = self.textCursor()
        line_text = cursor.block().text()[:cursor.positionInBlock()]

        m_ref = _REF_CONTEXT_RE.search(line_text)
        if m_ref:
            inner = m_ref.group(1)
            partial = inner.rsplit(",", 1)[-1].lstrip()
            return ("ref", partial)

        m_cite = _CITE_CONTEXT_RE.search(line_text)
        if m_cite:
            inner = m_cite.group(1)
            partial = inner.rsplit(",", 1)[-1].lstrip()
            return ("cite", partial)

        m_cmd = re.search(r"\\[A-Za-z@]*$", line_text)
        if m_cmd:
            return ("cmd", m_cmd.group(0))

        return ("none", "")

    def current_command_prefix(self):
        mode, prefix = self._completion_context()
        return prefix if mode != "none" else ""

    def insert_completion(self, completion: str):
        mode, prefix = self._completion_context()
        cursor = self.textCursor()

        if prefix:
            cursor.movePosition(
                cursor.MoveOperation.Left,
                cursor.MoveMode.KeepAnchor,
                len(prefix),
            )
        cursor.insertText(completion)
        if mode == "cmd":
            empty_brace = completion.find("{}")
            if empty_brace != -1:
                offset = len(completion) - empty_brace - 1
                cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, offset)
        self.setTextCursor(cursor)

    def wrap_selection(self, prefix: str, suffix: str):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertText(f"{prefix}{selected}{suffix}")
        else:
            cursor.insertText(f"{prefix}{suffix}")
            cursor.movePosition(
                cursor.MoveOperation.Left,
                cursor.MoveMode.MoveAnchor,
                len(suffix),
            )
        self.setTextCursor(cursor)

    def toggle_comment(self):
        """Comenta o descomenta con '% ' la línea actual o las líneas seleccionadas (Ctrl+/)."""
        cursor = self.textCursor()
        doc = self.document()
        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()

        start_block = doc.findBlock(start_pos)
        end_block = doc.findBlock(end_pos)
        if cursor.hasSelection() and end_block != start_block and end_pos == end_block.position():
            end_block = end_block.previous()

        blocks = []
        b = start_block
        while b.isValid():
            blocks.append(b)
            if b == end_block:
                break
            b = b.next()

        non_empty = [blk for blk in blocks if blk.text().strip()]
        target_blocks = non_empty if non_empty else blocks
        all_commented = all(blk.text().lstrip().startswith("%") for blk in target_blocks)

        edit_cursor = QTextCursor(doc)
        edit_cursor.beginEditBlock()
        if all_commented:
            for blk in target_blocks:
                txt = blk.text()
                indent = len(txt) - len(txt.lstrip())
                remove_len = 2 if txt[indent:indent + 2] == "% " else 1
                edit_cursor.setPosition(blk.position() + indent)
                edit_cursor.setPosition(blk.position() + indent + remove_len, QTextCursor.MoveMode.KeepAnchor)
                edit_cursor.removeSelectedText()
        else:
            min_indent = min(len(blk.text()) - len(blk.text().lstrip()) for blk in target_blocks)
            for blk in target_blocks:
                pos = blk.position() + min(min_indent, len(blk.text()))
                edit_cursor.setPosition(pos)
                edit_cursor.insertText("% ")
        edit_cursor.endEditBlock()

    def update_custom_commands(self):
        if not self._commands_dirty:
            return
        self._commands_dirty = False
        text = self.toPlainText()
        clean = _strip_comments(text)
        extra: set[str] = set()

        meta: dict[str, tuple[str, str]] = {
            cmd: _classify_command(cmd) for cmd in LATEX_COMMANDS
        }
        for pkg in extract_document_packages(clean):
            pkg_cmds = set()
            if pkg in PACKAGE_COMMANDS:
                pkg_cmds = set(PACKAGE_COMMANDS[pkg])
            elif pkg not in ("article", "report", "book", "letter", "standalone", "memoir"):
                pkg_cmds = _scan_sty_commands(pkg)
            extra.update(pkg_cmds)
            for cmd in pkg_cmds:
                meta[cmd] = _classify_command(cmd, source_pkg=pkg)

        user_cmds: set[str] = set()
        for match in re.finditer(
            r"\\(?:newcommand|renewcommand|providecommand)\*?\{(\\[A-Za-z@]+)\}(?:\[(\d)\])?",
            clean,
        ):
            cmd_name = match.group(1)
            num_args = int(match.group(2)) if match.group(2) else 0
            user_cmds.add(cmd_name + ("{}" * num_args))

        for match in re.finditer(r"\\DeclareMathOperator\*?\{(\\[A-Za-z@]+)\}", clean):
            user_cmds.add(match.group(1))

        for match in re.finditer(
            r"\\(?:New|Renew|Provide)DocumentCommand\{?(\\[A-Za-z@]+)\}?\{([^}]*)\}",
            clean,
        ):
            user_cmds.add(match.group(1) + ("{}" * min(match.group(2).count("m"), 3)))

        extra.update(user_cmds)
        for cmd in user_cmds:
            meta[cmd] = _classify_command(cmd, is_user=True)

        self._cmd_meta_cache = meta
        self._cmd_list_cache = sorted(set(LATEX_COMMANDS) | extra)

    def _get_project_context(self) -> tuple[list[tuple[pathlib.Path | None, str]], pathlib.Path | None]:
        if callable(self._project_context_provider):
            ctx = self._project_context_provider() or {}
            return ctx.get("open_texts", []), ctx.get("base_dir")
        base_dir = self.file_path.parent if self.file_path is not None else None
        return [], base_dir

    def _refresh_completer_for_mode(self, mode: str) -> bool:
        """Carga el modelo del completer según el modo ('cmd', 'ref', 'cite'). Devuelve True si hay elementos."""
        if mode == "cmd":
            self.update_custom_commands()
            self._command_meta = self._cmd_meta_cache
            if self._completion_mode != "cmd" or self.completer_model.rowCount() != len(self._cmd_list_cache):
                self.completer_model.setStringList(self._cmd_list_cache)
            self._completion_mode = "cmd"
            return bool(self._cmd_list_cache)

        open_texts, base_dir = self._get_project_context()
        if mode == "ref":
            labels = collect_project_labels(self.toPlainText(), open_texts, base_dir)
            if not labels:
                return False
            keys = sorted(labels.keys(), key=str.lower)
            self._command_meta = {k: ("ref", labels[k]) for k in keys}
            self.completer_model.setStringList(keys)
            self._completion_mode = "ref"
            return True

        if mode == "cite":
            cites = collect_project_citations(self.toPlainText(), open_texts, base_dir)
            if not cites:
                return False
            keys = sorted(cites.keys(), key=str.lower)
            self._command_meta = {k: ("cite", cites[k]) for k in keys}
            self.completer_model.setStringList(keys)
            self._completion_mode = "cite"
            return True

        return False

    def _update_completer_popup(self):
        mode, prefix = self._completion_context()
        if mode == "none" or (mode == "cmd" and len(prefix) < 2):
            self.completer.popup().hide()
            return

        if mode != self._completion_mode or mode in ("ref", "cite") or self._commands_dirty:
            has_items = self._refresh_completer_for_mode(mode)
            if not has_items:
                self.completer.popup().hide()
                return

        self.completer.setCompletionPrefix(prefix)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return

        self.completer.popup().setCurrentIndex(
            self.completer.completionModel().index(0, 0)
        )

        cr = self.cursorRect()
        pos_in_editor = self.viewport().mapToParent(cr.topLeft())
        cr.moveTopLeft(pos_in_editor)
        prefix_px = self.fontMetrics().horizontalAdvance(prefix)
        target_x = max(self.line_number_area_width() + 4, cr.left() - prefix_px - 36)
        cr.moveLeft(target_x)
        cr.translate(0, 4)
        cr.setWidth(350)
        self.completer.complete(cr)

    # ------------------------------------------------------------------
    # Autocierre de delimitadores, entornos \begin{...} e indentación
    # ------------------------------------------------------------------
    def _handle_enter_key(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False

        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        before = block_text[:col]
        after = block_text[col:]
        indent = before[: len(before) - len(before.lstrip(" \t"))]

        # 1. Autocierre de \begin{env} -> \end{env} si falta su cierre
        m_begin = _BEGIN_LINE_RE.search(before) if self.auto_close_enabled else None
        if m_begin and not after.strip():
            env = m_begin.group(1)
            clean_doc = _strip_comments(self.toPlainText())
            begins = len(re.findall(rf"\\begin\{{{re.escape(env)}\}}", clean_doc))
            ends = len(re.findall(rf"\\end\{{{re.escape(env)}\}}", clean_doc))
            if begins > ends:
                inner_indent = indent + (" " * self._tab_width)
                middle = f"{inner_indent}\\item " if env in _LIST_ENVIRONMENTS else inner_indent
                cursor.beginEditBlock()
                cursor.insertText(f"\n{middle}\n{indent}\\end{{{env}}}")
                cursor.movePosition(QTextCursor.MoveOperation.Up)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True

        # 2. Expansión limpia entre llaves vacías {|}
        if self.auto_close_enabled and before.endswith("{") and after.startswith("}") and not _is_escaped(before, len(before) - 1):
            inner_step = " " * self._tab_width
            cursor.beginEditBlock()
            cursor.insertText(f"\n{indent}{inner_step}\n{indent}")
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True

        # 3. Auto-indentación manteniendo la sangría actual
        if indent:
            cursor.insertText(f"\n{indent}")
            self.setTextCursor(cursor)
            return True

        return False

    def _handle_smart_backspace(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        # Borrar par escapado \[|\], \(|\), \{|\}
        if col >= 2 and col + 2 <= len(block_text):
            prev2 = block_text[col - 2 : col]
            next2 = block_text[col : col + 2]
            if (prev2, next2) in ((r"\[", r"\]"), (r"\(", r"\)"), (r"\{", r"\}")):
                if not _is_escaped(block_text, col - 2):
                    cursor.beginEditBlock()
                    cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 4)
                    cursor.removeSelectedText()
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    return True

        # Borrar par simple {|}, [|], (|), $|$
        if col >= 1 and col < len(block_text):
            prev_ch = block_text[col - 1]
            next_ch = block_text[col]
            if _AUTO_CLOSE_PAIRS.get(prev_ch) == next_ch and not _is_escaped(block_text, col - 1):
                cursor.beginEditBlock()
                cursor.deletePreviousChar()
                cursor.deleteChar()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True

        return False

    def _handle_auto_pair_char(self, ch: str) -> bool:
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        next_ch = block_text[col] if col < len(block_text) else ""

        # Envolver selección con delimitador ({}, [], (), $$)
        if cursor.hasSelection() and ch in _AUTO_CLOSE_PAIRS:
            closing = _AUTO_CLOSE_PAIRS[ch]
            selected = cursor.selectedText().replace("\u2029", "\n")
            cursor.beginEditBlock()
            start = cursor.selectionStart()
            cursor.insertText(f"{ch}{selected}{closing}")
            cursor.setPosition(start + len(ch))
            cursor.setPosition(start + len(ch) + len(selected), QTextCursor.MoveMode.KeepAnchor)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True

        # Saltar sobre delimitador de cierre ya existente (}, ], ), $)
        if ch in _CLOSING_CHARS and next_ch == ch and not _is_escaped(block_text, col):
            # Para $, no saltar si el anterior es "\" (el usuario escribe \$ literal)
            if not (ch == "$" and _is_escaped(block_text, col)):
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                return True

        if ch not in _AUTO_CLOSE_PAIRS:
            return False

        # No autocerrar si justo después hay un carácter alfanumérico o '\'
        if next_ch and (next_ch.isalnum() or next_ch == "\\"):
            return False

        escaped = _is_escaped(block_text, col)
        if escaped:
            if ch == "$":
                return False  # \$ es símbolo de dólar literal
            closing = "\\" + _AUTO_CLOSE_PAIRS[ch]
        else:
            closing = _AUTO_CLOSE_PAIRS[ch]

        cursor.beginEditBlock()
        cursor.insertText(ch + closing)
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(closing))
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible():
            if event.key() in (
                Qt.Key.Key_Enter,
                Qt.Key.Key_Return,
                Qt.Key.Key_Escape,
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
            ):
                event.ignore()
                return

        key = event.key()
        mods = event.modifiers()

        # Enter inteligente (\begin{env} -> \end{env}, {|} y auto-indentación)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
        ):
            if self._handle_enter_key():
                self.completer.popup().hide()
                return

        # Backspace inteligente en pares vacíos
        if self.auto_close_enabled and key == Qt.Key.Key_Backspace and not (
            mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        ):
            if self._handle_smart_backspace():
                self._update_completer_popup()
                return

        # Autocierre y salto de delimitadores ({}, [], (), $; compatible con AltGr)
        ch = event.text()
        if (
            self.auto_close_enabled
            and len(ch) == 1
            and (ch in _AUTO_CLOSE_PAIRS or ch in _CLOSING_CHARS)
            and not (mods & Qt.KeyboardModifier.MetaModifier)
        ):
            if self._handle_auto_pair_char(ch):
                self._update_completer_popup()
                return

        super().keyPressEvent(event)
        self._update_completer_popup()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        ai_menu = menu.addMenu("✨ Selene IA")

        has_sel = self.textCursor().hasSelection()
        sel_actions = (
            ("Mejorar redacción académica", "Mejora la claridad, fluidez y estilo académico del fragmento seleccionado manteniendo todos los comandos LaTeX y devolviendo solo el código listo para reemplazar."),
            ("Convertir a ecuación / tabla LaTeX", "Convierte el texto seleccionado en una ecuación o tabla LaTeX bien formateada (usa booktabs si es tabla) lista para insertar."),
            ("Explicar este código LaTeX", "Explica de forma breve y clara qué hace este fragmento de código LaTeX."),
            ("Traducir al inglés académico", "Traduce el texto seleccionado al inglés académico preservando intacta la sintaxis y los comandos LaTeX."),
            ("Revisar y corregir LaTeX", "Revisa el fragmento seleccionado en busca de errores de sintaxis LaTeX o mejores prácticas para LuaLaTeX y devuélvelo corregido."),
        )
        for label, prompt in sel_actions:
            act = ai_menu.addAction(label)
            act.setEnabled(has_sel)
            act.triggered.connect(lambda checked=False, p=prompt: self.ai_action_requested.emit("prompt", p))

        ai_menu.addSeparator()
        act_open = ai_menu.addAction("Abrir asistente Selene IA")
        act_open.triggered.connect(lambda checked=False: self.ai_action_requested.emit("open", ""))

        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData() if clipboard is not None else None
        if mime is not None and mime.hasImage():
            act_ocr = ai_menu.addAction("Transcribir imagen del portapapeles a LaTeX")
            act_ocr.triggered.connect(lambda checked=False: self.ai_action_requested.emit("ocr_clipboard", ""))

        menu.exec(event.globalPos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path:
                    self.file_dropped.emit(local_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
