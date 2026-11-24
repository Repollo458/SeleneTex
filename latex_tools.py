# This Python file uses the following encoding: utf-8
"""Herramientas visuales de LaTeX para SeleneTeX:
- Generador visual de tablas (booktabs / CSV / Excel)
- Paleta rápida de símbolos matemáticos y griegos
- Gestor de bibliografía (.bib) con importación por DOI y creación manual
"""

import csv
import io
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_client import ChevronComboBox
from highlighter import SEMANTIC_TOKENS
from icons import svg_icon, svg_pixmap


class SeleneCheckBox(QCheckBox):
    """QCheckBox con marca de verificación SVG blanca nítida sobre el indicador."""

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            ind_rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
            pm = svg_pixmap("check", "#ffffff", size=12, stroke_width=2.6)
            painter = QPainter(self)
            x = ind_rect.x() + (ind_rect.width() - 12) // 2
            y = ind_rect.y() + (ind_rect.height() - 12) // 2
            painter.drawPixmap(x, y, pm)
            painter.end()


# ==============================================================================
# 1. GENERADOR VISUAL DE TABLAS LATEX (booktabs + CSV/Excel + vista previa)
# ==============================================================================
def _escape_latex_cell(text: str) -> str:
    """Escapa &, %, # y _ (respetando contenido dentro de $...$)."""
    parts = re.split(r"(\$[^$]*\$)", text)
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # Modo matemático intacto
            out.append(part)
        else:
            p = part.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#").replace("_", r"\_")
            out.append(p)
    return "".join(out)


def parse_tabular_clipboard(raw_text: str) -> list[list[str]]:
    """Convierte texto pegado desde Excel/Calc (TSV) o CSV en matriz de celdas."""
    cleaned = raw_text.strip("\r\n")
    if not cleaned:
        return []
    lines = [ln for ln in cleaned.splitlines() if ln.strip() != ""]
    if not lines:
        return []

    sample = "\n".join(lines[:5])
    if "\t" in sample:
        delimiter = "\t"
    elif sample.count(";") >= sample.count(",") and ";" in sample:
        delimiter = ";"
    elif "," in sample:
        delimiter = ","
    else:
        return [[ln.strip()] for ln in lines]

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    rows = [[cell.strip() for cell in row] for row in reader]
    if not rows:
        return []
    max_cols = max(len(r) for r in rows)
    return [r + [""] * (max_cols - len(r)) for r in rows]


class TableGeneratorDialog(QDialog):
    """Estudio visual intuitivo para construir tablas LaTeX (booktabs, CSV/Excel y vista previa)."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme_name
        self.setWindowTitle("Generador visual de tablas — SeleneTeX")
        self.setMinimumSize(760, 520)
        self.resize(900, 600)
        self.generated_code = ""
        self.needs_booktabs = True
        self._style_id = "booktabs"  # "booktabs", "grid", "simple"
        self._align_char = "c"       # "l", "c", "r"

        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Cabecera clara
        header = QHBoxLayout()
        header.setSpacing(12)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Generador visual de tablas", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Edita directamente las celdas o importa datos copiados desde Excel, Calc o CSV.",
            self,
        )
        subtitle.setObjectName("dialogSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        self.btn_paste_csv = QPushButton(" Pegar desde Excel / CSV", self)
        self.btn_paste_csv.setIcon(svg_icon("table", t["text_primary"], 14))
        self.btn_paste_csv.setIconSize(QSize(14, 14))
        self.btn_paste_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste_csv.setToolTip("Importa celdas copiadas en el portapapeles (TSV, CSV o punto y coma)")
        self.btn_paste_csv.clicked.connect(self.paste_from_clipboard)
        header.addWidget(self.btn_paste_csv, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # Barra superior de estilo y alineación con controles segmentados (intuitivos)
        bar_card = QFrame(self)
        bar_card.setObjectName("toolCard")
        bar_layout = QHBoxLayout(bar_card)
        bar_layout.setContentsMargins(12, 8, 12, 8)
        bar_layout.setSpacing(14)

        def make_segmented(label_text: str, options: list[tuple[str, str, str]], default_key: str, on_pick):
            wrap = QHBoxLayout()
            wrap.setSpacing(6)
            lbl = QLabel(label_text, bar_card)
            lbl.setObjectName("fieldLabel")
            wrap.addWidget(lbl)

            seg = QFrame(bar_card)
            seg.setObjectName("segmentedControl")
            seg_lay = QHBoxLayout(seg)
            seg_lay.setContentsMargins(2, 2, 2, 2)
            seg_lay.setSpacing(2)

            group = QButtonGroup(self)
            group.setExclusive(True)
            btns = {}
            for key, text, tip in options:
                b = QPushButton(text, seg)
                b.setObjectName("segBtn")
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setToolTip(tip)
                if key == default_key:
                    b.setChecked(True)
                b.clicked.connect(lambda checked=False, k=key: on_pick(k))
                group.addButton(b)
                seg_lay.addWidget(b)
                btns[key] = b
            wrap.addWidget(seg)
            return wrap, group, btns

        style_wrap, self._style_group, self._style_btns = make_segmented(
            "Estilo:",
            [
                ("booktabs", "Académico", "Líneas limpias profesionales con paquete booktabs (recomendado)"),
                ("grid", "Cuadrícula", "Bordes verticales y horizontales en todas las celdas"),
                ("simple", "Simple", "Solo líneas horizontales básicas sin paquetes extra"),
            ],
            "booktabs",
            self.set_table_style,
        )
        align_wrap, self._align_group, self._align_btns = make_segmented(
            "Alineación:",
            [
                ("l", "Izquierda", "Alinear texto a la izquierda (l)"),
                ("c", "Centro", "Centrar contenido de cada celda (c)"),
                ("r", "Derecha", "Alinear texto a la derecha (r)"),
            ],
            "c",
            self.set_table_alignment,
        )

        bar_layout.addLayout(style_wrap)
        bar_layout.addLayout(align_wrap)
        bar_layout.addStretch(1)
        root.addWidget(bar_card)

        # Cuerpo principal en 2 paneles: Editor visual (izquierda) + Opciones y código (derecha)
        body = QHBoxLayout()
        body.setSpacing(12)

        # --- Panel izquierdo: Editor visual de celdas ---
        left_card = QFrame(self)
        left_card.setObjectName("toolCard")
        left_lay = QVBoxLayout(left_card)
        left_lay.setContentsMargins(12, 10, 12, 12)
        left_lay.setSpacing(8)

        dim_row = QHBoxLayout()
        dim_row.setSpacing(6)
        lbl_grid = QLabel("Contenido de la tabla", left_card)
        lbl_grid.setObjectName("fieldLabel")
        dim_row.addWidget(lbl_grid)
        dim_row.addStretch(1)

        self._rows_count = 4
        self._cols_count = 3

        def make_stepper(label: str, initial: int, on_delta):
            dim_row.addWidget(QLabel(label, left_card))
            btn_m = QPushButton("−", left_card)
            btn_m.setObjectName("stepBtn")
            btn_m.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_m.clicked.connect(lambda checked=False: on_delta(-1))
            val_lbl = QLabel(str(initial), left_card)
            val_lbl.setObjectName("dimCountBadge")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_p = QPushButton("+", left_card)
            btn_p.setObjectName("stepBtn")
            btn_p.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_p.clicked.connect(lambda checked=False: on_delta(1))
            dim_row.addWidget(btn_m)
            dim_row.addWidget(val_lbl)
            dim_row.addWidget(btn_p)
            return val_lbl

        self.lbl_rows_val = make_stepper("Filas:", self._rows_count, lambda d: self._set_dimensions(self._rows_count + d, self._cols_count))
        dim_row.addSpacing(8)
        self.lbl_cols_val = make_stepper("Cols:", self._cols_count, lambda d: self._set_dimensions(self._rows_count, self._cols_count + d))
        left_lay.addLayout(dim_row)

        self.table = QTableWidget(4, 3, left_card)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setMinimumHeight(230)
        self._populate_default_cells()
        self.table.itemChanged.connect(lambda *_: self._update_preview())
        left_lay.addWidget(self.table, 1)

        table_actions = QHBoxLayout()
        table_actions.setSpacing(6)
        btn_add_row = QPushButton("+ Fila", left_card)
        btn_add_row.setObjectName("aiCompactBtn")
        btn_add_row.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_row.clicked.connect(lambda: self._set_dimensions(self._rows_count + 1, self._cols_count))

        btn_add_col = QPushButton("+ Columna", left_card)
        btn_add_col.setObjectName("aiCompactBtn")
        btn_add_col.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_col.clicked.connect(lambda: self._set_dimensions(self._rows_count, self._cols_count + 1))

        btn_clear = QPushButton("Vaciar celdas", left_card)
        btn_clear.setObjectName("aiCompactBtn")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_cells)

        table_actions.addWidget(btn_add_row)
        table_actions.addWidget(btn_add_col)
        table_actions.addStretch(1)
        table_actions.addWidget(btn_clear)
        left_lay.addLayout(table_actions)

        # --- Panel derecho: Opciones claras + Vista previa LaTeX ---
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        opts_card = QFrame(self)
        opts_card.setObjectName("toolCard")
        opts_lay = QVBoxLayout(opts_card)
        opts_lay.setContentsMargins(14, 12, 14, 12)
        opts_lay.setSpacing(10)

        lbl_opts = QLabel("Presentación", opts_card)
        lbl_opts.setObjectName("fieldLabel")
        opts_lay.addWidget(lbl_opts)

        self.chk_header = SeleneCheckBox("Primera fila como encabezado (negrita)", opts_card)
        self.chk_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_header.setChecked(True)
        self.chk_header.toggled.connect(self._on_visual_option_changed)
        opts_lay.addWidget(self.chk_header)

        self.chk_wrap_table = SeleneCheckBox("Incluir título y numeración", opts_card)
        self.chk_wrap_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_wrap_table.setToolTip("Envuelve la tabla en un bloque flotante con título (\\caption) y referencia (\\label)")
        self.chk_wrap_table.setChecked(True)
        self.chk_wrap_table.toggled.connect(self._on_wrap_toggled)
        opts_lay.addWidget(self.chk_wrap_table)

        # Campos de título y etiqueta en una fila limpia (solo visibles si "Incluir título y numeración" está activo)
        self.meta_container = QWidget(opts_card)
        meta_lay = QHBoxLayout(self.meta_container)
        meta_lay.setContentsMargins(24, 0, 0, 0)
        meta_lay.setSpacing(8)

        self.input_caption = QLineEdit("Resumen de resultados", self.meta_container)
        self.input_caption.setPlaceholderText("Título visible...")
        self.input_caption.setToolTip("Título de la tabla (\\caption)")
        self.input_caption.textChanged.connect(self._update_preview)

        self.input_label = QLineEdit("tab:resultados", self.meta_container)
        self.input_label.setPlaceholderText("tab:etiqueta")
        self.input_label.setToolTip("Etiqueta para referencias cruzadas (\\label)")
        self.input_label.textChanged.connect(self._update_preview)

        meta_lay.addWidget(self.input_caption, 3)
        meta_lay.addWidget(self.input_label, 2)
        opts_lay.addWidget(self.meta_container)

        self.chk_escape = SeleneCheckBox("Proteger símbolos de texto (%, &&, _)", opts_card)
        self.chk_escape.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_escape.setToolTip(
            "Convierte automáticamente %, &, # y _ en texto seguro para LaTeX.\n"
            "Las expresiones matemáticas entre $...$ no se modifican."
        )
        self.chk_escape.setChecked(True)
        self.chk_escape.toggled.connect(self._update_preview)
        opts_lay.addWidget(self.chk_escape)
        right_col.addWidget(opts_card)

        # Vista previa de código LaTeX con botón copiar
        prev_card = QFrame(self)
        prev_card.setObjectName("toolCard")
        prev_lay = QVBoxLayout(prev_card)
        prev_lay.setContentsMargins(14, 10, 14, 12)
        prev_lay.setSpacing(6)

        prev_hdr = QHBoxLayout()
        lbl_prev = QLabel("Código LaTeX generado", prev_card)
        lbl_prev.setObjectName("fieldLabel")
        self.btn_copy_latex = QPushButton(" Copiar", prev_card)
        self.btn_copy_latex.setObjectName("aiCompactBtn")
        self.btn_copy_latex.setIcon(svg_icon("copy", t["text_secondary"], 13))
        self.btn_copy_latex.setIconSize(QSize(13, 13))
        self.btn_copy_latex.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_latex.clicked.connect(self._copy_generated_code)
        prev_hdr.addWidget(lbl_prev)
        prev_hdr.addStretch(1)
        prev_hdr.addWidget(self.btn_copy_latex)
        prev_lay.addLayout(prev_hdr)

        self.preview = QPlainTextEdit(prev_card)
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont("JetBrains Mono", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.preview.setFont(mono)
        self.preview.setMinimumHeight(140)
        prev_lay.addWidget(self.preview, 1)
        right_col.addWidget(prev_card, 1)

        body.addWidget(left_card, 3)
        body.addLayout(right_col, 2)
        root.addLayout(body, 1)

        # Pie del diálogo
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_insert = QPushButton("Insertar tabla", self)
        btn_insert.setObjectName("primaryBtn")
        btn_insert.setDefault(True)
        btn_insert.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_insert.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_insert)
        root.addLayout(btn_row)

        self._apply_table_visual_formatting()
        self._update_preview()

    def set_table_style(self, style_id: str):
        if style_id not in ("booktabs", "grid", "simple"):
            return
        self._style_id = style_id
        if style_id in self._style_btns:
            self._style_btns[style_id].setChecked(True)
        self._update_preview()

    def set_table_alignment(self, align_char: str):
        if align_char not in ("l", "c", "r"):
            return
        self._align_char = align_char
        if align_char in self._align_btns:
            self._align_btns[align_char].setChecked(True)
        self._apply_table_visual_formatting()
        self._update_preview()

    def _on_visual_option_changed(self):
        self._apply_table_visual_formatting()
        self._update_preview()

    def _apply_table_visual_formatting(self):
        """Refleja negrita de encabezado y alineación en las celdas visibles de la tabla."""
        align_map = {
            "l": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "c": Qt.AlignmentFlag.AlignCenter,
            "r": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        }
        qt_align = align_map.get(self._align_char, Qt.AlignmentFlag.AlignCenter)
        bold_header = self.chk_header.isChecked()

        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.table.setItem(r, c, item)
                item.setTextAlignment(qt_align)
                f = item.font()
                f.setBold(r == 0 and bold_header)
                item.setFont(f)
        self.table.blockSignals(False)

    def _populate_default_cells(self):
        self.table.blockSignals(True)
        self.table.setHorizontalHeaderLabels([f"Columna {c + 1}" for c in range(self.table.columnCount())])
        defaults = [
            ["Parámetro", "Valor", "Unidad"],
            ["Masa", "1.25", "kg"],
            ["Velocidad", "9.81", "m/s"],
            ["Energía", "60.1", "J"],
        ]
        for r, row_vals in enumerate(defaults):
            for c, val in enumerate(row_vals):
                self.table.setItem(r, c, QTableWidgetItem(val))
        self.table.blockSignals(False)

    def _clear_cells(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                self.table.setItem(r, c, QTableWidgetItem(""))
        self.table.blockSignals(False)
        self._apply_table_visual_formatting()
        self._update_preview()

    def _set_dimensions(self, rows: int, cols: int):
        rows = max(1, min(30, rows))
        cols = max(1, min(15, cols))
        if rows == self._rows_count and cols == self._cols_count:
            return
        self._rows_count = rows
        self._cols_count = cols
        self.lbl_rows_val.setText(str(rows))
        self.lbl_cols_val.setText(str(cols))
        self.table.blockSignals(True)
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self.table.setHorizontalHeaderLabels([f"Columna {c + 1}" for c in range(cols)])
        self.table.blockSignals(False)
        self._apply_table_visual_formatting()
        self._update_preview()

    def _on_wrap_toggled(self, checked: bool):
        self.meta_container.setVisible(checked)
        self._update_preview()

    def _copy_generated_code(self):
        if not self.generated_code:
            return
        QApplication.clipboard().setText(self.generated_code)
        self.btn_copy_latex.setText(" ¡Copiado!")
        QTimer.singleShot(1400, lambda: self.btn_copy_latex.setText(" Copiar"))

    def load_matrix(self, matrix: list[list[str]]):
        if not matrix:
            return
        rows = min(30, len(matrix))
        cols = min(15, max(len(r) for r in matrix))
        self._rows_count = rows
        self._cols_count = cols
        self.lbl_rows_val.setText(str(rows))
        self.lbl_cols_val.setText(str(cols))

        self.table.blockSignals(True)
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self.table.setHorizontalHeaderLabels([f"Columna {c + 1}" for c in range(cols)])
        for r in range(rows):
            for c in range(cols):
                val = matrix[r][c] if c < len(matrix[r]) else ""
                self.table.setItem(r, c, QTableWidgetItem(val))
        self.table.blockSignals(False)
        self._apply_table_visual_formatting()
        self._update_preview()

    def paste_from_clipboard(self):
        raw = QApplication.clipboard().text() if QApplication.clipboard() is not None else ""
        matrix = parse_tabular_clipboard(raw)
        if not matrix:
            QMessageBox.information(
                self,
                "Portapapeles vacío",
                "Copia primero una tabla desde Excel, LibreOffice Calc o texto CSV y pulsa de nuevo.",
            )
            return
        self.load_matrix(matrix)

    def build_latex(self) -> tuple[str, bool]:
        rows = self.table.rowCount()
        cols = self.table.columnCount()
        is_booktabs = self._style_id == "booktabs"
        is_grid = self._style_id == "grid"
        align_char = self._align_char
        use_header = self.chk_header.isChecked()
        wrap_table = self.chk_wrap_table.isChecked()
        do_escape = self.chk_escape.isChecked()

        if is_grid:
            col_spec = "|" + "|".join([align_char] * cols) + "|"
        else:
            col_spec = align_char * cols

        indent = "    " if wrap_table else ""
        row_indent = indent + "    "
        lines: list[str] = []

        if wrap_table:
            lines.append("\\begin{table}[htbp]")
            lines.append("    \\centering")
            cap = self.input_caption.text().strip()
            if cap:
                lines.append(f"    \\caption{{{_escape_latex_cell(cap) if do_escape else cap}}}")
            lbl = self.input_label.text().strip()
            if lbl:
                lines.append(f"    \\label{{{lbl}}}")

        lines.append(f"{indent}\\begin{{tabular}}{{{col_spec}}}")
        lines.append(f"{row_indent}\\toprule" if is_booktabs else f"{row_indent}\\hline")

        for r in range(rows):
            cells: list[str] = []
            for c in range(cols):
                item = self.table.item(r, c)
                val = item.text().strip() if item is not None else ""
                if do_escape:
                    val = _escape_latex_cell(val)
                if r == 0 and use_header and val:
                    val = f"\\textbf{{{val}}}"
                cells.append(val)
            lines.append(f"{row_indent}{' & '.join(cells)} \\\\")
            if r == 0 and rows > 1:
                lines.append(f"{row_indent}\\midrule" if is_booktabs else f"{row_indent}\\hline")
            elif is_grid and r < rows - 1:
                lines.append(f"{row_indent}\\hline")

        lines.append(f"{row_indent}\\bottomrule" if is_booktabs else f"{row_indent}\\hline")
        lines.append(f"{indent}\\end{{tabular}}")

        if wrap_table:
            lines.append("\\end{table}")

        return "\n".join(lines) + "\n", is_booktabs

    def _update_preview(self):
        code, needs_bt = self.build_latex()
        self.generated_code = code
        self.needs_booktabs = needs_bt
        self.preview.setPlainText(code)


# ==============================================================================
# 2. PALETA RÁPIDA DE SÍMBOLOS MATEMÁTICOS Y GRIEGOS
# ==============================================================================
# Cada entrada: (glifo_visible, comando_latex, descripción_buscable)
SYMBOL_CATEGORIES: dict[str, list[tuple[str, str, str]]] = {
    "Griego": [
        ("α", r"\alpha", "alfa griego"),
        ("β", r"\beta", "beta griego"),
        ("γ", r"\gamma", "gamma griego"),
        ("δ", r"\delta", "delta griego"),
        ("ε", r"\varepsilon", "epsilon griego"),
        ("ζ", r"\zeta", "zeta griego"),
        ("η", r"\eta", "eta griego"),
        ("θ", r"\theta", "theta teta griego"),
        ("ι", r"\iota", "iota griego"),
        ("κ", r"\kappa", "kappa griego"),
        ("λ", r"\lambda", "lambda griego"),
        ("μ", r"\mu", "mu griego"),
        ("ν", r"\nu", "nu griego"),
        ("ξ", r"\xi", "xi griego"),
        ("π", r"\pi", "pi griego"),
        ("ρ", r"\rho", "rho ro griego"),
        ("σ", r"\sigma", "sigma griego"),
        ("τ", r"\tau", "tau griego"),
        ("φ", r"\varphi", "phi fi griego"),
        ("χ", r"\chi", "chi ji griego"),
        ("ψ", r"\psi", "psi griego"),
        ("ω", r"\omega", "omega griego"),
        ("Γ", r"\Gamma", "gamma mayuscula"),
        ("Δ", r"\Delta", "delta incremento mayuscula"),
        ("Θ", r"\Theta", "theta mayuscula"),
        ("Λ", r"\Lambda", "lambda mayuscula"),
        ("Π", r"\Pi", "pi productorio mayuscula"),
        ("Σ", r"\Sigma", "sigma sumatorio mayuscula"),
        ("Φ", r"\Phi", "phi mayuscula"),
        ("Ψ", r"\Psi", "psi mayuscula"),
        ("Ω", r"\Omega", "omega ohm mayuscula"),
    ],
    "Operadores": [
        ("±", r"\pm", "mas menos"),
        ("∓", r"\mp", "menos mas"),
        ("×", r"\times", "por producto cruz"),
        ("÷", r"\div", "division"),
        ("·", r"\cdot", "punto producto"),
        ("∘", r"\circ", "composicion circulo"),
        ("∑", r"\sum", "sumatorio suma"),
        ("∏", r"\prod", "productorio producto"),
        ("∫", r"\int", "integral"),
        ("∬", r"\iint", "integral doble"),
        ("∮", r"\oint", "integral cerrada contorno"),
        ("∂", r"\partial", "derivada parcial"),
        ("∇", r"\nabla", "nabla gradiente divergencia"),
        ("∞", r"\infty", "infinito"),
        ("√", r"\sqrt{}", "raiz cuadrada"),
        ("a/b", r"\frac{}{}", "fraccion division"),
        ("⊕", r"\oplus", "suma directa xor"),
        ("⊗", r"\otimes", "producto tensorial"),
        ("★", r"\star", "estrella convolucion"),
        ("…", r"\dots", "puntos suspensivos"),
    ],
    "Relaciones": [
        ("≤", r"\leq", "menor o igual"),
        ("≥", r"\geq", "mayor o igual"),
        ("≠", r"\neq", "distinto diferente no igual"),
        ("≈", r"\approx", "aproximado aproximadamente"),
        ("≡", r"\equiv", "equivalente congruente identico"),
        ("∼", r"\sim", "similar distribucion"),
        ("∝", r"\propto", "proporcional"),
        ("≪", r"\ll", "mucho menor"),
        ("≫", r"\gg", "mucho mayor"),
        ("∈", r"\in", "pertenece elemento"),
        ("∉", r"\notin", "no pertenece"),
        ("⊂", r"\subset", "subconjunto"),
        ("⊆", r"\subseteq", "subconjunto o igual"),
        ("∪", r"\cup", "union conjuntos"),
        ("∩", r"\cap", "interseccion conjuntos"),
        ("∅", r"\emptyset", "conjunto vacio"),
        ("∀", r"\forall", "para todo cuantificador"),
        ("∃", r"\exists", "existe cuantificador"),
        ("¬", r"\neg", "negacion no logico"),
        ("∧", r"\wedge", "y conjuncion"),
        ("∨", r"\vee", "o disyuncion"),
        ("⊥", r"\perp", "perpendicular ortogonal"),
        ("∥", r"\parallel", "paralelo"),
    ],
    "Flechas": [
        ("→", r"\to", "flecha derecha tiende"),
        ("←", r"\leftarrow", "flecha izquierda"),
        ("↔", r"\leftrightarrow", "flecha doble"),
        ("⇒", r"\Rightarrow", "implica entonces"),
        ("⇐", r"\Leftarrow", "implica inversa"),
        ("⇔", r"\Leftrightarrow", "si y solo si equivalencia"),
        ("↦", r"\mapsto", "mapea asigna funcion"),
        ("↑", r"\uparrow", "flecha arriba"),
        ("↓", r"\downarrow", "flecha abajo"),
        ("⟶", r"\longrightarrow", "flecha larga derecha"),
        ("⟹", r"\Longrightarrow", "implica larga"),
        ("⟺", r"\Longleftrightarrow", "equivalencia larga"),
    ],
    "Estructuras": [
        ("a/b", r"\frac{}{}", "fraccion"),
        ("√x", r"\sqrt{}", "raiz cuadrada"),
        ("ⁿ√x", r"\sqrt[]{}", "raiz enesima"),
        ("∑ᵢⁿ", r"\sum_{i=1}^{n} ", "sumatorio con limites"),
        ("∫ₐᵇ", r"\int_{a}^{b} ", "integral definida"),
        ("lim", r"\lim_{x \to \infty} ", "limite"),
        ("ℝ", r"\mathbb{R}", "numeros reales"),
        ("ℕ", r"\mathbb{N}", "numeros naturales"),
        ("ℤ", r"\mathbb{Z}", "numeros enteros"),
        ("ℂ", r"\mathbb{C}", "numeros complejos"),
        ("ℒ", r"\mathcal{}", "caligrafica laplace"),
        ("x⃗", r"\vec{}", "vector"),
        ("x̂", r"\hat{}", "sombrero estimador unitario"),
        ("x̄", r"\overline{}", "barra conjugado media"),
        ("()", r"\left(  \right)", "parentesis adaptables"),
        ("(::)", "\\begin{pmatrix}\n    a & b \\\\\n    c & d\n\\end{pmatrix}", "matriz parentesis"),
    ],
}


class _SymbolButton(QPushButton):
    """Botón de símbolo que notifica al pasar el ratón para actualizar la barra de vista previa."""

    hovered = Signal(str, str, str)

    def __init__(self, glyph: str, cmd: str, desc: str, parent=None):
        super().__init__(glyph, parent)
        self._glyph = glyph
        self._cmd = cmd
        self._desc = desc
        self.setObjectName("symbolBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{cmd} — {desc.capitalize()}")

    def enterEvent(self, event):
        self.hovered.emit(self._glyph, self._cmd, self._desc)
        super().enterEvent(event)


class SymbolPaletteWidget(QWidget):
    """Panel lateral denso y adaptativo con buscador, secciones completas y vista previa al pasar el ratón."""

    symbol_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_category = "Todos"
        self._last_cols = 5

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cabecera fija con buscador y 6 categorías simétricas (2x3)
        top_box = QWidget(self)
        top_box.setObjectName("symbolTopBar")
        top_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top_lay = QVBoxLayout(top_box)
        top_lay.setContentsMargins(8, 8, 8, 6)
        top_lay.setSpacing(6)

        self.search_input = QLineEdit(top_box)
        self.search_input.setPlaceholderText("Filtrar símbolo o comando...")
        self.search_input.setAccessibleName("Filtrar símbolos matemáticos")
        self.search_input.textChanged.connect(self._rebuild_grid)
        top_lay.addWidget(self.search_input)

        cat_grid = QGridLayout()
        cat_grid.setContentsMargins(0, 0, 0, 0)
        cat_grid.setSpacing(3)
        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)
        all_cats = ["Todos", *SYMBOL_CATEGORIES.keys()]
        for idx, cat_name in enumerate(all_cats):
            btn = QPushButton(cat_name, top_box)
            btn.setObjectName("symbolCatBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if cat_name == self._active_category:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, c=cat_name: self._set_category(c))
            self._cat_group.addButton(btn)
            cat_grid.addWidget(btn, idx // 3, idx % 3)
        top_lay.addLayout(cat_grid)
        layout.addWidget(top_box)

        # Área desplazable ocupando todo el ancho disponible (sin huecos en blanco)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("symbolScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_container = QFrame(self.scroll)
        self.grid_container.setObjectName("symbolScrollCanvas")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 2, 8, 8)
        self.grid_layout.setSpacing(4)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, 1)

        # Barra inferior de vista previa en vivo al pasar el ratón por cualquier símbolo
        self.preview_bar = QFrame(self)
        self.preview_bar.setObjectName("symbolPreviewBar")
        prev_lay = QHBoxLayout(self.preview_bar)
        prev_lay.setContentsMargins(10, 6, 10, 6)
        prev_lay.setSpacing(8)

        self.lbl_prev_glyph = QLabel("∑", self.preview_bar)
        self.lbl_prev_glyph.setObjectName("symbolPreviewGlyph")
        self.lbl_prev_glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prev_text_col = QVBoxLayout()
        prev_text_col.setContentsMargins(0, 0, 0, 0)
        prev_text_col.setSpacing(0)
        self.lbl_prev_cmd = QLabel(r"\sum", self.preview_bar)
        self.lbl_prev_cmd.setObjectName("symbolPreviewCmd")
        self.lbl_prev_desc = QLabel("Haz clic para insertar en el editor", self.preview_bar)
        self.lbl_prev_desc.setObjectName("symbolPreviewDesc")
        prev_text_col.addWidget(self.lbl_prev_cmd)
        prev_text_col.addWidget(self.lbl_prev_desc)

        prev_lay.addWidget(self.lbl_prev_glyph)
        prev_lay.addLayout(prev_text_col, 1)
        layout.addWidget(self.preview_bar)

        self._rebuild_grid()

    def _compute_columns(self) -> int:
        avail = max(180, self.scroll.viewport().width() - 16)
        return max(4, min(7, (avail + 4) // 46))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = self._compute_columns()
        if cols != self._last_cols:
            self._last_cols = cols
            self._rebuild_grid()

    def _on_symbol_hovered(self, glyph: str, cmd: str, desc: str):
        self.lbl_prev_glyph.setText(glyph)
        self.lbl_prev_cmd.setText(cmd.splitlines()[0])
        self.lbl_prev_desc.setText(desc.capitalize())

    def _set_category(self, category: str):
        self._active_category = category
        self.search_input.clear()
        self._rebuild_grid()

    def _rebuild_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        cols = self._compute_columns()
        self._last_cols = cols
        for c in range(8):
            self.grid_layout.setColumnStretch(c, 1 if c < cols else 0)

        query = self.search_input.text().strip().lower()
        sections: list[tuple[str | None, list[tuple[str, str, str]]]] = []

        if query:
            seen_cmds: set[str] = set()
            matched: list[tuple[str, str, str]] = []
            for items in SYMBOL_CATEGORIES.values():
                for glyph, cmd, desc in items:
                    if cmd in seen_cmds:
                        continue
                    if query in f"{glyph} {cmd} {desc}".lower():
                        seen_cmds.add(cmd)
                        matched.append((glyph, cmd, desc))
            if matched:
                sections.append((None, matched))
        elif self._active_category == "Todos":
            for cat_name, items in SYMBOL_CATEGORIES.items():
                sections.append((cat_name, items))
        else:
            items = SYMBOL_CATEGORIES.get(self._active_category, [])
            if items:
                sections.append((None, items))

        if not sections:
            lbl = QLabel("Sin símbolos coincidentes", self.grid_container)
            lbl.setObjectName("fieldHint")
            self.grid_layout.addWidget(lbl, 0, 0, 1, cols)
            return

        row = 0
        for sec_title, items in sections:
            if sec_title:
                hdr = QLabel(sec_title.upper(), self.grid_container)
                hdr.setObjectName("symbolSectionTitle")
                self.grid_layout.addWidget(hdr, row, 0, 1, cols)
                row += 1
            for idx, (glyph, cmd, desc) in enumerate(items):
                btn = _SymbolButton(glyph, cmd, desc, self.grid_container)
                btn.hovered.connect(self._on_symbol_hovered)
                btn.clicked.connect(lambda checked=False, c=cmd: self.symbol_selected.emit(c))
                self.grid_layout.addWidget(btn, row + idx // cols, idx % cols)
            row += (len(items) + cols - 1) // cols


# ==============================================================================
# 3. GESTOR DE BIBLIOGRAFÍA (.bib) + IMPORTACIÓN POR DOI
# ==============================================================================
def parse_bib_entries_detailed(bib_text: str, source_name: str = "") -> list[dict]:
    """Extrae entradas BibTeX completas (clave, tipo, autor, título, año) para el gestor."""
    results: list[dict] = []
    entry_re = re.compile(r"@([A-Za-z]+)\s*[\{\(]\s*([^,\s\}\)]+)\s*,", re.MULTILINE)
    matches = list(entry_re.finditer(bib_text))

    def _extract_field(body: str, field_name: str) -> str:
        m = re.search(
            rf"\b{field_name}\s*=\s*(?:\{{([^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*)\}}|\"([^\"]*)\"|(\d{{4}}))",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return ""
        raw = m.group(1) or m.group(2) or m.group(3) or ""
        return re.sub(r"\s+", " ", raw.replace("{", "").replace("}", "")).strip()

    for i, m in enumerate(matches):
        etype = m.group(1).lower()
        if etype in ("string", "preamble", "comment"):
            continue
        key = m.group(2).strip()
        if not key:
            continue
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(bib_text)
        body = bib_text[m.end() : end_pos]
        results.append({
            "key": key,
            "type": etype,
            "title": _extract_field(body, "title"),
            "author": _extract_field(body, "author") or _extract_field(body, "editor"),
            "year": _extract_field(body, "year"),
            "source": source_name,
        })
    return results


def normalize_doi(raw_doi: str) -> str:
    """Normaliza un DOI eliminando prefijos https://doi.org/ o doi:."""
    d = raw_doi.strip()
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    d = re.sub(r"^doi:\s*", "", d, flags=re.IGNORECASE)
    return d.strip()


class DoiFetchWorker(QThread):
    """Consulta https://doi.org/<doi> pidiendo formato application/x-bibtex."""

    entry_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, doi: str, parent=None):
        super().__init__(parent)
        self.doi = normalize_doi(doi)

    def run(self):
        if not self.doi or "/" not in self.doi:
            self.error_occurred.emit("Formato de DOI no válido (ejemplo: 10.1038/nature12373).")
            return
        url = f"https://doi.org/{urllib.parse.quote(self.doi, safe='/')}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/x-bibtex; charset=utf-8",
                "User-Agent": "SeleneTeX/1.0 (LaTeX Desktop Editor)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
            if "@" not in raw:
                self.error_occurred.emit("No se recibió una entrada BibTeX válida para ese DOI.")
                return
            self.entry_ready.emit(raw)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.error_occurred.emit(f"DOI no encontrado: {self.doi}")
            else:
                self.error_occurred.emit(f"Error HTTP {e.code} al consultar el DOI.")
        except Exception as e:
            self.error_occurred.emit(f"No se pudo consultar el DOI:\n{e}")


class AddBibEntryDialog(QDialog):
    """Diálogo rápido para crear una entrada BibTeX manual."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva referencia BibTeX — SeleneTeX")
        self.setMinimumWidth(420)
        self.bibtex_entry = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        title = QLabel("Añadir referencia BibTeX", self)
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        def add_row(label: str, widget):
            lbl = QLabel(label, self)
            lbl.setObjectName("fieldLabel")
            root.addWidget(lbl)
            root.addWidget(widget)

        self.combo_type = ChevronComboBox(theme_name, self)
        self.combo_type.addItems(["article", "book", "inproceedings", "misc", "phdthesis", "techreport"])
        add_row("Tipo de entrada", self.combo_type)

        self.input_key = QLineEdit(self)
        self.input_key.setPlaceholderText("Ej. knuth1984")
        add_row("Clave de cita", self.input_key)

        self.input_author = QLineEdit(self)
        self.input_author.setPlaceholderText("Ej. Donald E. Knuth")
        add_row("Autor(es)", self.input_author)

        self.input_title = QLineEdit(self)
        self.input_title.setPlaceholderText("Título de la obra")
        add_row("Título", self.input_title)

        row_meta = QHBoxLayout()
        row_meta.setSpacing(8)
        self.input_year = QLineEdit(self)
        self.input_year.setPlaceholderText("2025")
        self.input_year.setMaximumWidth(90)
        self.input_venue = QLineEdit(self)
        self.input_venue.setPlaceholderText("Revista / Editorial")
        row_meta.addWidget(QLabel("Año:", self))
        row_meta.addWidget(self.input_year)
        row_meta.addWidget(QLabel("Publicado en:", self))
        row_meta.addWidget(self.input_venue, 1)
        root.addLayout(row_meta)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Añadir al .bib", self)
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._validate_and_accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _validate_and_accept(self):
        key = re.sub(r"\s+", "", self.input_key.text().strip())
        if not key:
            QMessageBox.warning(self, "Falta la clave", "Indica una clave de cita (por ejemplo: einstein1905).")
            self.input_key.setFocus()
            return
        etype = self.combo_type.currentText()
        author = self.input_author.text().strip()
        title = self.input_title.text().strip()
        year = self.input_year.text().strip()
        venue = self.input_venue.text().strip()

        venue_field = "publisher" if etype == "book" else ("booktitle" if etype == "inproceedings" else "journal")
        fields = []
        if author:
            fields.append(f"  author = {{{author}}}")
        if title:
            fields.append(f"  title = {{{title}}}")
        if venue:
            fields.append(f"  {venue_field} = {{{venue}}}")
        if year:
            fields.append(f"  year = {{{year}}}")
        body = ",\n".join(fields)
        self.bibtex_entry = f"@{etype}{{{key},\n{body}\n}}"
        self.accept()


class BibliographyDockWidget(QWidget):
    """Panel lateral de bibliografía (.bib) con búsqueda, inserción de \\cite{} e importación DOI."""

    cite_requested = Signal(str)
    bibtex_entry_added = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._entries: list[dict] = []
        self._doi_worker: DoiFetchWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        # Buscador + refrescar
        top_row = QHBoxLayout()
        top_row.setSpacing(5)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Filtrar referencias (.bib)...")
        self.search_input.textChanged.connect(self._render_list)

        self.btn_refresh = QPushButton(self)
        self.btn_refresh.setObjectName("iconBtn")
        self.btn_refresh.setIconSize(QSize(14, 14))
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setToolTip("Reescanear archivos .bib del proyecto")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)

        top_row.addWidget(self.search_input, 1)
        top_row.addWidget(self.btn_refresh)
        layout.addLayout(top_row)

        # Importar por DOI
        doi_row = QHBoxLayout()
        doi_row.setSpacing(5)
        self.doi_input = QLineEdit(self)
        self.doi_input.setPlaceholderText("Importar DOI (ej. 10.1038/...)")
        self.doi_input.returnPressed.connect(self.fetch_doi)

        self.btn_doi = QPushButton("DOI", self)
        self.btn_doi.setObjectName("aiCompactBtn")
        self.btn_doi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_doi.setToolTip("Descargar entrada BibTeX automáticamente desde doi.org")
        self.btn_doi.clicked.connect(self.fetch_doi)

        doi_row.addWidget(self.doi_input, 1)
        doi_row.addWidget(self.btn_doi)
        layout.addLayout(doi_row)

        # Lista de referencias
        self.bib_list = QListWidget(self)
        self.bib_list.setObjectName("bibList")
        self.bib_list.setWordWrap(True)
        self.bib_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.bib_list, 1)

        # Acciones inferiores
        bot_row = QHBoxLayout()
        bot_row.setSpacing(6)
        self.btn_insert_cite = QPushButton("Insertar \\cite", self)
        self.btn_insert_cite.setObjectName("aiCompactBtn")
        self.btn_insert_cite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_insert_cite.clicked.connect(self._insert_selected_cite)

        self.btn_manual = QPushButton("+ Manual", self)
        self.btn_manual.setObjectName("aiCompactBtn")
        self.btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manual.clicked.connect(self._open_manual_dialog)

        bot_row.addWidget(self.btn_insert_cite, 1)
        bot_row.addWidget(self.btn_manual)
        layout.addLayout(bot_row)

        self.set_theme("dark")

    def set_theme(self, theme_name: str):
        self._theme = theme_name
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        self.btn_refresh.setIcon(svg_icon("refresh", t["text_secondary"], 14))

    def set_entries(self, entries: list[dict]):
        self._entries = list(entries)
        self._render_list()

    def _render_list(self):
        self.bib_list.clear()
        query = self.search_input.text().strip().lower()
        filtered = [
            e
            for e in self._entries
            if not query
            or query in f"{e['key']} {e['title']} {e['author']} {e['year']} {e['type']}".lower()
        ]
        if not filtered:
            placeholder = QListWidgetItem(
                "Sin referencias .bib encontradas.\nImporta un DOI o añade una entrada manual."
                if not self._entries
                else "Sin coincidencias para el filtro actual."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.bib_list.addItem(placeholder)
            return

        for entry in filtered:
            year_part = f" ({entry['year']})" if entry["year"] else ""
            header = f"@{entry['key']}{year_part} · {entry['type']}"
            detail_parts = []
            if entry["title"]:
                title_short = entry["title"][:64] + ("…" if len(entry["title"]) > 64 else "")
                detail_parts.append(title_short)
            if entry["author"]:
                auth_short = entry["author"][:44] + ("…" if len(entry["author"]) > 44 else "")
                detail_parts.append(auth_short)
            text = header + ("\n" + " — ".join(detail_parts) if detail_parts else "")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry["key"])
            if entry.get("source"):
                item.setToolTip(f"Archivo: {entry['source']}\nClave: {entry['key']}")
            self.bib_list.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.cite_requested.emit(key)

    def _insert_selected_cite(self):
        item = self.bib_list.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.cite_requested.emit(key)

    def _open_manual_dialog(self):
        dlg = AddBibEntryDialog(self._theme, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.bibtex_entry:
            self.bibtex_entry_added.emit(dlg.bibtex_entry)

    def fetch_doi(self):
        doi = self.doi_input.text().strip()
        if not doi:
            return
        if self._doi_worker is not None and self._doi_worker.isRunning():
            return
        self.btn_doi.setEnabled(False)
        self.btn_doi.setText("...")
        self._doi_worker = DoiFetchWorker(doi, self)
        self._doi_worker.entry_ready.connect(self._on_doi_ready)
        self._doi_worker.error_occurred.connect(self._on_doi_error)
        self._doi_worker.start()

    def _on_doi_ready(self, bibtex_text: str):
        self.btn_doi.setEnabled(True)
        self.btn_doi.setText("DOI")
        self.doi_input.clear()
        self.bibtex_entry_added.emit(bibtex_text)

    def _on_doi_error(self, msg: str):
        self.btn_doi.setEnabled(True)
        self.btn_doi.setText("DOI")
        QMessageBox.warning(self, "Error al importar DOI", msg)
