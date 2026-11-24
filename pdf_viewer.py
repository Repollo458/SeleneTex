# This Python file uses the following encoding: utf-8

from collections import OrderedDict
import pathlib

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from highlighter import SEMANTIC_TOKENS
from icons import svg_icon, svg_pixmap

MIN_ZOOM = 0.5
MAX_ZOOM = 4.0
MAX_CACHE_PAGES = 24


class PdfPageLabel(QLabel):
    """Página individual del PDF con render diferido, SyncTeX, búsqueda y selección de texto."""

    def __init__(self, page_num: int, viewer, dark_pdf: bool = False):
        super().__init__()
        self.page_num = page_num
        self.viewer = viewer
        self._rendered_key = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.apply_page_chrome(dark_pdf)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 115 if dark_pdf else 46))
        self.setGraphicsEffect(shadow)

        # Destello SyncTeX
        self.highlight_rect: QRectF | None = None
        self.highlight_opacity = 0.0
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(40)
        self.flash_timer.timeout.connect(self._fade_highlight)

        # Selección de texto con ratón (arrastre)
        self._dragging = False
        self._drag_origin: QPoint | None = None
        self._drag_rect: QRectF | None = None
        self._selected_word_rects: list[QRectF] = []

    def apply_page_chrome(self, dark_pdf: bool):
        border_color = "#252e4d" if dark_pdf else "#cfd7e8"
        bg_color = "#121728" if dark_pdf else "white"
        self.setStyleSheet(f"background-color: {bg_color}; border: 1px solid {border_color};")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(QColor(0, 0, 0, 115 if dark_pdf else 46))

    def set_rendered_pixmap(self, pixmap: QPixmap, key):
        self._rendered_key = key
        self.setPixmap(pixmap)

    def clear_rendered(self):
        if self._rendered_key is not None:
            self._rendered_key = None
            self.setPixmap(QPixmap())

    def clear_selection(self):
        changed = bool(self._drag_rect or self._selected_word_rects)
        self._drag_rect = None
        self._selected_word_rects = []
        if changed:
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.viewer.clear_text_selection(except_page=self.page_num)
            self._dragging = True
            self._drag_origin = event.position().toPoint()
            self._drag_rect = None
            self._selected_word_rects = []
            self.viewer._selected_text = ""
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_origin is not None:
            cur = event.position().toPoint()
            if (cur - self._drag_origin).manhattanLength() >= 4:
                x1, y1 = self._drag_origin.x(), self._drag_origin.y()
                x2, y2 = cur.x(), cur.y()
                self._drag_rect = QRectF(
                    min(x1, x2),
                    min(y1, y2),
                    abs(x2 - x1),
                    abs(y2 - y1),
                )
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self._drag_rect is not None and (
                self._drag_rect.width() >= 4 or self._drag_rect.height() >= 4
            ):
                text, word_rects = self.viewer.extract_selection_on_page(
                    self.page_num, self._drag_rect
                )
                self._selected_word_rects = word_rects
                self.viewer._selected_text = text
                if word_rects:
                    self._drag_rect = None
            else:
                self._drag_rect = None
                self._selected_word_rects = []
                self.viewer._selected_text = ""
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_rect = None
            pos = event.position()
            x_pt, y_pt = self.viewer.widget_point_to_pdf(self.page_num, pos.x(), pos.y())
            self.viewer.page_clicked.emit(self.page_num, x_pt, y_pt)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_copy = menu.addAction("Copiar texto seleccionado")
        act_copy.setEnabled(bool(self.viewer.selected_text()))
        act_copy.triggered.connect(self.viewer.copy_selected_text)

        pos = event.pos()
        act_sync = menu.addAction("Ir al código aquí (SyncTeX)")
        act_sync.triggered.connect(
            lambda checked=False, p=pos: self._emit_synctex_at(p.x(), p.y())
        )

        menu.addSeparator()
        act_fit_w = menu.addAction("Ajustar al ancho")
        act_fit_w.triggered.connect(self.viewer.fit_width)
        act_fit_p = menu.addAction("Ajustar a página completa")
        act_fit_p.triggered.connect(self.viewer.fit_page)
        menu.exec(event.globalPos())

    def _emit_synctex_at(self, x: float, y: float):
        x_pt, y_pt = self.viewer.widget_point_to_pdf(self.page_num, x, y)
        self.viewer.page_clicked.emit(self.page_num, x_pt, y_pt)

    def flash_highlight(self, h_pt: float, v_pt: float, w_pt: float, height_pt: float):
        box_h = max(height_pt, 12.0)
        box_w = max(w_pt, 60.0)
        pdf_rect = fitz.Rect(h_pt, v_pt - box_h, h_pt + box_w, v_pt)
        wrect = self.viewer.pdf_rect_to_widget(self.page_num, pdf_rect)
        self.highlight_rect = wrect.adjusted(-4, -3, 4, 3)
        self.highlight_opacity = 1.0
        self.flash_timer.start()
        self.update()

    def _fade_highlight(self):
        self.highlight_opacity -= 0.04
        if self.highlight_opacity <= 0:
            self.highlight_opacity = 0.0
            self.highlight_rect = None
            self.flash_timer.stop()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        search_rects = self.viewer.search_widget_rects_for_page(self.page_num)
        active_rect = self.viewer.active_search_widget_rect_for_page(self.page_num)
        has_sel = bool(self._selected_word_rects or self._drag_rect)
        has_flash = self.highlight_rect is not None and self.highlight_opacity > 0

        if not (search_rects or active_rect or has_sel or has_flash):
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Coincidencias de búsqueda en el PDF
        if search_rects:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(250, 204, 21, 95))
            for r in search_rects:
                painter.drawRoundedRect(r, 2.5, 2.5)

        if active_rect is not None:
            painter.setBrush(QColor(249, 115, 22, 130))
            painter.setPen(QPen(QColor(249, 115, 22, 230), 1.5))
            painter.drawRoundedRect(active_rect.adjusted(-1, -1, 1, 1), 3.0, 3.0)

        # 2. Selección de texto (palabras resaltadas o rectángulo de arrastre)
        if self._selected_word_rects:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(56, 189, 248, 85))
            for r in self._selected_word_rects:
                painter.drawRoundedRect(r, 2.0, 2.0)

        if self._drag_rect is not None:
            painter.setBrush(QColor(56, 189, 248, 50))
            painter.setPen(QPen(QColor(56, 189, 248, 190), 1.2))
            painter.drawRect(self._drag_rect)

        # 3. Destello SyncTeX
        if has_flash and self.highlight_rect is not None:
            fill = QColor(99, 102, 241, int(85 * self.highlight_opacity))
            border = QColor(125, 211, 252, int(225 * self.highlight_opacity))
            painter.setBrush(fill)
            painter.setPen(QPen(border, 2))
            painter.drawRoundedRect(self.highlight_rect, 4, 4)

        painter.end()


class _PdfScrollArea(QScrollArea):
    """QScrollArea interna que delega Ctrl+Rueda al zoom del PdfViewer."""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.viewer.zoom_in()
            elif event.angleDelta().y() < 0:
                self.viewer.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewer._schedule_viewport_update()


class PdfViewer(QFrame):
    page_clicked = Signal(int, float, float)
    zoom_changed = Signal(float)
    compile_requested = Signal()
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pdfViewerFrame")
        self.setAccessibleName("Visor de documento PDF")

        self.current_pdf = None
        self._doc: fitz.Document | None = None
        self._page_sizes_pt: list[tuple[float, float]] = []
        self._page_widgets: list[PdfPageLabel] = []
        self._pixmap_cache: OrderedDict[tuple, QPixmap] = OrderedDict()

        self._last_page_width_pt = 595.0  # A4 por defecto
        self._last_page_height_pt = 842.0
        self.zoom = 1.0
        self.rotation = 0  # 0, 90, 180, 270
        self.two_page_mode = False
        self.dark_pdf = False
        self._theme = "dark"
        self._state_kind = "empty"  # "empty", "loading", "error", "pages"
        self._state_extra = ""
        self._current_page = 1

        # Estado de búsqueda y selección en PDF
        self._search_query = ""
        self._search_matches: list[tuple[int, fitz.Rect]] = []
        self._page_search_rects: dict[int, list[fitz.Rect]] = {}
        self._current_match_idx = -1
        self._selected_text = ""

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(20)
        self._render_timer.timeout.connect(self._on_viewport_changed)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._setup_toolbar(root_layout)
        self._setup_search_bar(root_layout)

        self.scroll_area = _PdfScrollArea(self)
        self.container = QWidget()
        self.container.setObjectName("pdfCanvas")
        self.pages_layout = QVBoxLayout(self.container)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pages_layout.setSpacing(16)
        self.pages_layout.setContentsMargins(20, 20, 20, 20)
        self.scroll_area.setWidget(self.container)
        root_layout.addWidget(self.scroll_area, 1)

        self.scroll_area.verticalScrollBar().valueChanged.connect(self._schedule_viewport_update)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._schedule_viewport_update)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._copy_shortcut.activated.connect(self.copy_selected_text)

        self._refresh_icons()
        self._update_toolbar_state()
        self._show_empty_state()

    # ------------------------------------------------------------------
    # Barra superior compacta + Barra de búsqueda en PDF
    # ------------------------------------------------------------------
    def _setup_toolbar(self, parent_layout: QVBoxLayout):
        self.pdf_toolbar = QFrame(self)
        self.pdf_toolbar.setObjectName("pdfToolBar")
        tb = QHBoxLayout(self.pdf_toolbar)
        tb.setContentsMargins(8, 4, 8, 4)
        tb.setSpacing(4)

        def make_icon_btn(tooltip: str, slot, checkable: bool = False):
            btn = QPushButton(self.pdf_toolbar)
            btn.setObjectName("iconBtn")
            btn.setIconSize(QSize(14, 14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setAccessibleName(tooltip)
            btn.setCheckable(checkable)
            if checkable:
                btn.toggled.connect(slot)
            else:
                btn.clicked.connect(slot)
            return btn

        self.btn_prev_page = make_icon_btn("Página anterior", self.prev_page)
        self.page_input = QLineEdit("0", self.pdf_toolbar)
        self.page_input.setObjectName("pdfPageInput")
        self.page_input.setFixedWidth(40)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.setValidator(QIntValidator(1, 99999, self))
        self.page_input.setToolTip("Ir a la página (pulsa Enter)")
        self.page_input.returnPressed.connect(self._on_page_input_submitted)

        self.lbl_total_pages = QLabel("/ 0", self.pdf_toolbar)
        self.lbl_total_pages.setObjectName("pdfMetaLabel")
        self.btn_next_page = make_icon_btn("Página siguiente", self.next_page)

        self.btn_fit_width = make_icon_btn("Ajustar al ancho (Ctrl+0)", self.fit_width)
        self.btn_fit_page = make_icon_btn("Ajustar a página completa", self.fit_page)
        self.btn_two_page = make_icon_btn("Vista de doble página", self.set_two_page_mode, checkable=True)
        self.btn_rotate = make_icon_btn("Rotar 90° en sentido horario", self.rotate_cw)
        self.btn_pdf_search = make_icon_btn(
            "Buscar texto en el PDF (Ctrl+Shift+F)",
            self.toggle_search_bar,
            checkable=True,
        )

        tb.addWidget(self.btn_prev_page)
        tb.addWidget(self.page_input)
        tb.addWidget(self.lbl_total_pages)
        tb.addWidget(self.btn_next_page)
        tb.addStretch(1)
        tb.addWidget(self.btn_fit_width)
        tb.addWidget(self.btn_fit_page)
        tb.addWidget(self.btn_two_page)
        tb.addWidget(self.btn_rotate)
        tb.addWidget(self.btn_pdf_search)

        parent_layout.addWidget(self.pdf_toolbar)

    def _setup_search_bar(self, parent_layout: QVBoxLayout):
        self.search_bar = QFrame(self)
        self.search_bar.setObjectName("pdfSearchBar")
        lay = QHBoxLayout(self.search_bar)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(6)

        self.search_input = QLineEdit(self.search_bar)
        self.search_input.setPlaceholderText("Buscar texto en el PDF...")
        self.search_input.setAccessibleName("Buscar texto en el PDF")
        self.search_input.returnPressed.connect(self.next_search_match)
        self.search_input.textChanged.connect(self.search_pdf)

        self.lbl_search_count = QLabel("", self.search_bar)
        self.lbl_search_count.setObjectName("matchCount")
        self.lbl_search_count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_search_prev = QPushButton(self.search_bar)
        self.btn_search_prev.setObjectName("iconBtn")
        self.btn_search_prev.setIconSize(QSize(14, 14))
        self.btn_search_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search_prev.setToolTip("Coincidencia anterior")
        self.btn_search_prev.clicked.connect(self.prev_search_match)

        self.btn_search_next = QPushButton(self.search_bar)
        self.btn_search_next.setObjectName("iconBtn")
        self.btn_search_next.setIconSize(QSize(14, 14))
        self.btn_search_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search_next.setToolTip("Coincidencia siguiente (Enter)")
        self.btn_search_next.clicked.connect(self.next_search_match)

        self.btn_search_close = QPushButton(self.search_bar)
        self.btn_search_close.setObjectName("iconBtn")
        self.btn_search_close.setIconSize(QSize(14, 14))
        self.btn_search_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search_close.setToolTip("Cerrar búsqueda en PDF (Esc)")
        self.btn_search_close.clicked.connect(self.hide_search_bar)

        lay.addWidget(self.search_input, 1)
        lay.addWidget(self.lbl_search_count)
        lay.addWidget(self.btn_search_prev)
        lay.addWidget(self.btn_search_next)
        lay.addWidget(self.btn_search_close)

        self._search_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_bar)
        self._search_esc.activated.connect(self.hide_search_bar)

        self.search_bar.hide()
        parent_layout.addWidget(self.search_bar)

    def _refresh_icons(self):
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        fg = t["text_secondary"]
        muted = t["text_muted"]
        accent = t["accent_text"]

        self.btn_prev_page.setIcon(svg_icon("chevron_up", fg, 14))
        self.btn_next_page.setIcon(svg_icon("chevron_down", fg, 14))
        self.btn_fit_width.setIcon(svg_icon("fit_width", fg, 14))
        self.btn_fit_page.setIcon(svg_icon("fit_page", fg, 14))
        self.btn_two_page.setIcon(svg_icon("book_open", fg, 14, active_color=accent))
        self.btn_rotate.setIcon(svg_icon("rotate_cw", fg, 14))
        self.btn_pdf_search.setIcon(svg_icon("search", fg, 14, active_color=accent))

        self.btn_search_prev.setIcon(svg_icon("arrow_up", fg, 14))
        self.btn_search_next.setIcon(svg_icon("arrow_down", fg, 14))
        self.btn_search_close.setIcon(svg_icon("close", muted, 14))

    def _update_toolbar_state(self):
        total = self.page_count()
        has_pages = total > 0
        for w in (
            self.btn_prev_page,
            self.page_input,
            self.btn_next_page,
            self.btn_fit_width,
            self.btn_fit_page,
            self.btn_two_page,
            self.btn_rotate,
            self.btn_pdf_search,
        ):
            w.setEnabled(has_pages)
        self.lbl_total_pages.setText(f"/ {total}")
        if has_pages:
            self._current_page = max(1, min(self._current_page, total))
            if not self.page_input.hasFocus():
                self.page_input.setText(str(self._current_page))
        else:
            self.page_input.setText("0")

    def verticalScrollBar(self):
        return self.scroll_area.verticalScrollBar()

    def viewport(self):
        return self.scroll_area.viewport()

    def set_theme(self, theme_name: str):
        self._theme = theme_name
        self._refresh_icons()
        if self._state_kind == "empty":
            self._show_empty_state()
        elif self._state_kind == "loading":
            self.show_loading_state(self._state_extra)
        elif self._state_kind == "error":
            self.show_error_state(self._state_extra)

    # ------------------------------------------------------------------
    # Estados visuales (Vacío / Carga / Error)
    # ------------------------------------------------------------------
    def _clear_layout(self):
        self._page_widgets = []
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    sw = sub_item.widget()
                    if sw is not None:
                        sw.hide()
                        sw.setParent(None)
                        sw.deleteLater()

    def _close_doc(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        self._page_sizes_pt = []
        self._pixmap_cache.clear()
        self._search_matches.clear()
        self._page_search_rects.clear()
        self._current_match_idx = -1
        self._selected_text = ""

    def _build_state_card(
        self,
        card_obj_name: str,
        icon_name: str,
        icon_color: str,
        title_text: str,
        desc_text: str,
        cta_text: str | None = None,
        cta_icon_name: str | None = None,
        show_progress: bool = False,
        title_obj_name: str = "pdfEmptyTitle",
    ):
        self._clear_layout()
        self.pages_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetDefaultConstraint)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame(self.container)
        card.setObjectName(card_obj_name)
        card.setMinimumWidth(300)
        card.setMaximumWidth(360)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(15, 23, 42, 90 if self._theme == "dark" else 28))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(card)
        icon_lbl.setPixmap(svg_pixmap(icon_name, icon_color, size=34, stroke_width=1.6))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel(title_text, card)
        title_lbl.setObjectName(title_obj_name)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc_text, card)
        desc_lbl.setObjectName("pdfEmptyDesc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setMinimumWidth(260)
        desc_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card_layout.addWidget(desc_lbl)

        if show_progress:
            bar = QProgressBar(card)
            bar.setObjectName("compileProgress")
            bar.setRange(0, 0)
            bar.setTextVisible(False)
            bar.setFixedWidth(220)
            card_layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignCenter)

        if cta_text:
            btn = QPushButton(cta_text, card)
            btn.setObjectName("primaryBtn")
            if cta_icon_name:
                btn.setIcon(svg_icon(cta_icon_name, "#ffffff", size=14, stroke_width=2.0))
                btn.setIconSize(QSize(14, 14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self.compile_requested.emit)
            card_layout.addSpacing(4)
            card_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.pages_layout.addStretch(1)
        self.pages_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        self.pages_layout.addStretch(1)
        self._update_toolbar_state()

    def _show_empty_state(self):
        self._state_kind = "empty"
        self._state_extra = ""
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        self._build_state_card(
            card_obj_name="pdfEmptyCard",
            icon_name="moon",
            icon_color=t["accent_icon"],
            title_text="Vista previa del PDF",
            desc_text="Compila tu documento con LuaLaTeX (F5) para previsualizar el resultado y navegar con SyncTeX.",
            cta_text=" Compilar ahora",
            cta_icon_name="play",
        )

    def show_loading_state(self, doc_name: str = "", engine_name: str = "LuaLaTeX"):
        if self.page_count() > 0:
            return
        self._state_kind = "loading"
        self._state_extra = doc_name
        self._state_engine = engine_name
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        subtitle = (
            f"Ejecutando {engine_name} sobre {doc_name}..."
            if doc_name
            else f"Ejecutando {engine_name} para generar el PDF..."
        )
        self._build_state_card(
            card_obj_name="pdfEmptyCard",
            icon_name="loader",
            icon_color=t["accent_icon"],
            title_text="Compilando documento",
            desc_text=subtitle,
            show_progress=True,
        )

    def show_error_state(self, message: str = ""):
        if self.page_count() > 0:
            return
        self._state_kind = "error"
        self._state_extra = message
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        desc = message or "Revisa el panel de salida inferior o usa Selene IA para corregir el error."
        self._build_state_card(
            card_obj_name="pdfErrorCard",
            icon_name="alert",
            icon_color=t["danger_text"],
            title_text="No se pudo generar el PDF",
            desc_text=desc,
            cta_text=" Reintentar compilación",
            cta_icon_name="refresh",
            title_obj_name="pdfErrorTitle",
        )

    def page_count(self) -> int:
        return len(self._page_widgets)

    def clear_pages(self, show_empty: bool = True):
        self._clear_layout()
        self._close_doc()
        self.hide_search_bar()
        if show_empty:
            self._show_empty_state()
        else:
            self._update_toolbar_state()

    # ------------------------------------------------------------------
    # Transformación de coordenadas (Zoom + Rotación)
    # ------------------------------------------------------------------
    def _page_transform(self, page_num: int):
        """Devuelve (matrix_1x, offset_x, offset_y) para convertir PDF <-> widget."""
        page = self._doc[page_num - 1]
        mat = fitz.Matrix(self.zoom, self.zoom).prerotate(self.rotation)
        transformed = page.rect * mat
        return mat, transformed.x0, transformed.y0

    def pdf_rect_to_widget(self, page_num: int, rect: fitz.Rect) -> QRectF:
        if self._doc is None or not (1 <= page_num <= len(self._doc)):
            return QRectF()
        mat, ox, oy = self._page_transform(page_num)
        tr = rect * mat
        return QRectF(tr.x0 - ox, tr.y0 - oy, tr.width, tr.height)

    def widget_point_to_pdf(self, page_num: int, x: float, y: float) -> tuple[float, float]:
        if self._doc is None or not (1 <= page_num <= len(self._doc)):
            return (x / self.zoom, y / self.zoom)
        mat, ox, oy = self._page_transform(page_num)
        inv = ~mat
        pt = fitz.Point(x + ox, y + oy) * inv
        return (float(pt.x), float(pt.y))

    def _widget_rect_to_pdf(self, page_num: int, qrect: QRectF) -> fitz.Rect:
        x0, y0 = self.widget_point_to_pdf(page_num, qrect.left(), qrect.top())
        x1, y1 = self.widget_point_to_pdf(page_num, qrect.right(), qrect.bottom())
        return fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def _rotated_page_size_px(self, page_idx: int) -> tuple[int, int]:
        w_pt, h_pt = self._page_sizes_pt[page_idx]
        if self.rotation in (90, 270):
            w_pt, h_pt = h_pt, w_pt
        return (max(1, int(round(w_pt * self.zoom))), max(1, int(round(h_pt * self.zoom))))

    # ------------------------------------------------------------------
    # Carga de PDF + Diseño de páginas (1 columna / 2 columnas) + Render diferido
    # ------------------------------------------------------------------
    def load_pdf(self, pdf_path):
        scroll_pos = self.verticalScrollBar().value()
        prev_query = self._search_query if self.search_bar.isVisible() else ""
        self._clear_layout()
        self._close_doc()

        try:
            pdf_bytes = pathlib.Path(pdf_path).read_bytes()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) == 0:
                doc.close()
                self.current_pdf = None
                self._show_empty_state()
                return
        except Exception as exc:
            self.current_pdf = None
            self.show_error_state(f"No se pudo abrir el archivo PDF:\n{exc}")
            return

        self._doc = doc
        self.current_pdf = pdf_path
        self._page_sizes_pt = [(float(p.rect.width) or 595.0, float(p.rect.height) or 842.0) for p in doc]
        self._last_page_width_pt, self._last_page_height_pt = self._page_sizes_pt[0]

        self._rebuild_page_placeholders()
        self._update_toolbar_state()

        if prev_query:
            self.search_pdf(prev_query, scroll_to_first=False)

        self.verticalScrollBar().setValue(scroll_pos)
        self._on_viewport_changed()
        QTimer.singleShot(0, self._on_viewport_changed)

    def _rebuild_page_placeholders(self):
        """Crea contenedores ligeros para cada página (sin rasterizar fuera de pantalla)."""
        self._clear_layout()
        if self._doc is None or not self._page_sizes_pt:
            return

        self._state_kind = "pages"
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pages_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinAndMaxSize)

        widgets: list[PdfPageLabel] = []
        for idx in range(len(self._page_sizes_pt)):
            lbl = PdfPageLabel(idx + 1, self, dark_pdf=self.dark_pdf)
            w_px, h_px = self._rotated_page_size_px(idx)
            lbl.setFixedSize(w_px, h_px)
            widgets.append(lbl)
        self._page_widgets = widgets

        if self.two_page_mode and len(widgets) > 1:
            for i in range(0, len(widgets), 2):
                row_widget = QWidget(self.container)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(14)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                row_layout.addWidget(widgets[i])
                if i + 1 < len(widgets):
                    row_layout.addWidget(widgets[i + 1])
                self.pages_layout.addWidget(row_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            for lbl in widgets:
                self.pages_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _update_placeholder_sizes(self):
        for idx, lbl in enumerate(self._page_widgets):
            w_px, h_px = self._rotated_page_size_px(idx)
            lbl.setFixedSize(w_px, h_px)
            lbl.apply_page_chrome(self.dark_pdf)
            lbl.clear_selection()
            lbl.clear_rendered()
        self._selected_text = ""

    def _schedule_viewport_update(self):
        if self._doc is not None and not self._render_timer.isActive():
            self._render_timer.start()

    def _render_page_pixmap(self, page_num: int) -> tuple[QPixmap, tuple]:
        dpr = max(1.0, min(2.5, float(self.devicePixelRatioF() or 1.0)))
        key = (page_num, round(self.zoom, 3), self.rotation, self.dark_pdf, round(dpr, 2))
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            self._pixmap_cache.move_to_end(key)
            return cached, key

        page = self._doc[page_num - 1]
        scale = self.zoom * dpr
        matrix = fitz.Matrix(scale, scale).prerotate(self.rotation)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888,
        ).copy()

        if self.dark_pdf:
            image.invertPixels(QImage.InvertMode.InvertRgb)
            image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            painter = QPainter(image)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            painter.fillRect(image.rect(), QColor("#121728"))
            painter.end()

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)

        self._pixmap_cache[key] = pixmap
        while len(self._pixmap_cache) > MAX_CACHE_PAGES:
            self._pixmap_cache.popitem(last=False)
        return pixmap, key

    def _page_y_in_container(self, lbl: PdfPageLabel) -> int:
        return lbl.mapTo(self.container, QPoint(0, 0)).y()

    def _on_viewport_changed(self):
        if self._doc is None or not self._page_widgets:
            return

        vbar = self.verticalScrollBar()
        view_top = vbar.value()
        view_h = max(300, self.viewport().height())
        view_bottom = view_top + view_h

        # Zona de renderizado anticipado (±1 pantalla) y zona de descarga en documentos largos
        render_top = view_top - view_h
        render_bottom = view_bottom + view_h
        evict_top = view_top - 3 * view_h
        evict_bottom = view_bottom + 3 * view_h
        evict_enabled = len(self._page_widgets) > MAX_CACHE_PAGES

        dpr = max(1.0, min(2.5, float(self.devicePixelRatioF() or 1.0)))
        target_key_suffix = (round(self.zoom, 3), self.rotation, self.dark_pdf, round(dpr, 2))

        focus_y = view_top + view_h // 3
        best_page = self._current_page
        best_dist = float("inf")

        for lbl in self._page_widgets:
            top = self._page_y_in_container(lbl)
            bottom = top + lbl.height()

            # Detectar página actual visible
            if top <= focus_y <= bottom:
                best_page = lbl.page_num
                best_dist = 0
            else:
                dist = min(abs(top - focus_y), abs(bottom - focus_y))
                if dist < best_dist:
                    best_dist = dist
                    best_page = lbl.page_num

            if bottom >= render_top and top <= render_bottom:
                expected_key = (lbl.page_num,) + target_key_suffix
                if lbl._rendered_key != expected_key:
                    pm, key = self._render_page_pixmap(lbl.page_num)
                    lbl.set_rendered_pixmap(pm, key)
            elif evict_enabled and (bottom < evict_top or top > evict_bottom):
                lbl.clear_rendered()

        if best_page != self._current_page:
            self._current_page = best_page
            if not self.page_input.hasFocus():
                self.page_input.setText(str(best_page))

    # ------------------------------------------------------------------
    # Navegación, zoom, rotación, doble página y modo noche
    # ------------------------------------------------------------------
    def go_to_page(self, page_num: int):
        total = self.page_count()
        if total == 0:
            return
        page_num = max(1, min(page_num, total))
        lbl = self._page_widgets[page_num - 1]
        y = max(0, self._page_y_in_container(lbl) - 16)
        self.verticalScrollBar().setValue(y)
        self._current_page = page_num
        if not self.page_input.hasFocus():
            self.page_input.setText(str(page_num))
        self._on_viewport_changed()

    def prev_page(self):
        self.go_to_page(self._current_page - 1)

    def next_page(self):
        self.go_to_page(self._current_page + 1)

    def _on_page_input_submitted(self):
        txt = self.page_input.text().strip()
        if txt.isdigit():
            self.go_to_page(int(txt))
        self.page_input.clearFocus()

    def set_dark_pdf(self, enabled: bool):
        if self.dark_pdf == enabled:
            return
        self.dark_pdf = enabled
        if self._doc is not None:
            for lbl in self._page_widgets:
                lbl.apply_page_chrome(enabled)
            self._on_viewport_changed()

    def set_two_page_mode(self, enabled: bool):
        if self.two_page_mode == enabled:
            return
        self.two_page_mode = enabled
        self.btn_two_page.blockSignals(True)
        self.btn_two_page.setChecked(enabled)
        self.btn_two_page.blockSignals(False)
        if self._doc is not None:
            cur = self._current_page
            self._rebuild_page_placeholders()
            QTimer.singleShot(0, lambda p=cur: self.go_to_page(p))

    def rotate_cw(self):
        self.rotation = (self.rotation + 90) % 360
        if self._doc is not None:
            self._update_placeholder_sizes()
            self._on_viewport_changed()

    def scroll_to_position(self, page_num: int, y_pt: float, box_pt=None):
        if 1 <= page_num <= len(self._page_widgets):
            lbl = self._page_widgets[page_num - 1]
            # Convertir punto SyncTeX a coordenada Y del widget (respetando rotación)
            ref_rect = fitz.Rect(0, y_pt, 10, y_pt + 10)
            wrect = self.pdf_rect_to_widget(page_num, ref_rect)
            target_y = self._page_y_in_container(lbl) + int(wrect.top()) - 100
            self.verticalScrollBar().setValue(max(0, target_y))
            self._on_viewport_changed()
            if box_pt is not None:
                lbl.flash_highlight(*box_pt)

    def set_zoom(self, new_zoom: float):
        new_zoom = round(max(MIN_ZOOM, min(new_zoom, MAX_ZOOM)), 2)
        if new_zoom == self.zoom:
            return
        ratio = new_zoom / self.zoom if self.zoom else 1.0
        old_scroll = self.verticalScrollBar().value()
        self.zoom = new_zoom
        self.zoom_changed.emit(self.zoom)
        if self._doc is not None:
            self._update_placeholder_sizes()
            self.verticalScrollBar().setValue(int(round(old_scroll * ratio)))
            self._on_viewport_changed()

    def zoom_in(self):
        self.set_zoom(self.zoom + 0.25)

    def zoom_out(self):
        self.set_zoom(self.zoom - 0.25)

    def reset_zoom(self):
        self.set_zoom(1.0)

    def fit_width(self):
        w_pt = self._last_page_height_pt if self.rotation in (90, 270) else self._last_page_width_pt
        avail = max(240, self.viewport().width() - 56)
        if self.two_page_mode and self.page_count() > 1:
            avail = max(200, (avail - 14) / 2.0)
        self.set_zoom(avail / max(1.0, w_pt))

    def fit_page(self):
        w_pt, h_pt = self._last_page_width_pt, self._last_page_height_pt
        if self.rotation in (90, 270):
            w_pt, h_pt = h_pt, w_pt
        avail_w = max(240, self.viewport().width() - 56)
        if self.two_page_mode and self.page_count() > 1:
            avail_w = max(200, (avail_w - 14) / 2.0)
        avail_h = max(240, self.viewport().height() - 48)
        self.set_zoom(min(avail_w / max(1.0, w_pt), avail_h / max(1.0, h_pt)))

    # ------------------------------------------------------------------
    # Búsqueda de texto dentro del PDF
    # ------------------------------------------------------------------
    def toggle_search_bar(self, show: bool):
        if show:
            self.show_search_bar()
        else:
            self.hide_search_bar()

    def show_search_bar(self):
        if self.page_count() == 0:
            self.btn_pdf_search.setChecked(False)
            return
        self.search_bar.show()
        self.btn_pdf_search.blockSignals(True)
        self.btn_pdf_search.setChecked(True)
        self.btn_pdf_search.blockSignals(False)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def hide_search_bar(self):
        self.search_bar.hide()
        self.btn_pdf_search.blockSignals(True)
        self.btn_pdf_search.setChecked(False)
        self.btn_pdf_search.blockSignals(False)
        self._search_query = ""
        self._search_matches.clear()
        self._page_search_rects.clear()
        self._current_match_idx = -1
        self.lbl_search_count.setText("")
        self._set_search_notfound_state(False)
        for lbl in self._page_widgets:
            lbl.update()

    def _set_search_notfound_state(self, not_found: bool):
        state = "notfound" if not_found else ""
        for w in (self.search_input, self.lbl_search_count):
            if w.property("findState") != state:
                w.setProperty("findState", state)
                w.style().unpolish(w)
                w.style().polish(w)

    def search_pdf(self, query: str, scroll_to_first: bool = True):
        self._search_query = query
        self._search_matches.clear()
        self._page_search_rects.clear()
        self._current_match_idx = -1

        q = query.strip()
        if not q or self._doc is None:
            self.lbl_search_count.setText("")
            self._set_search_notfound_state(False)
            for lbl in self._page_widgets:
                lbl.update()
            return

        for page_idx, page in enumerate(self._doc):
            rects = page.search_for(q)
            if rects:
                pnum = page_idx + 1
                self._page_search_rects[pnum] = rects
                for r in rects:
                    self._search_matches.append((pnum, r))

        total = len(self._search_matches)
        if total == 0:
            self.lbl_search_count.setText("0 / 0")
            self._set_search_notfound_state(True)
        else:
            self._current_match_idx = 0
            self.lbl_search_count.setText(f"1 / {total}")
            self._set_search_notfound_state(False)
            if scroll_to_first:
                self._scroll_to_match(0)

        for lbl in self._page_widgets:
            lbl.update()

    def _scroll_to_match(self, idx: int):
        if not (0 <= idx < len(self._search_matches)):
            return
        self._current_match_idx = idx
        total = len(self._search_matches)
        self.lbl_search_count.setText(f"{idx + 1} / {total}")
        page_num, rect = self._search_matches[idx]
        lbl = self._page_widgets[page_num - 1]
        wrect = self.pdf_rect_to_widget(page_num, rect)
        target_y = self._page_y_in_container(lbl) + int(wrect.top()) - max(80, self.viewport().height() // 3)
        self.verticalScrollBar().setValue(max(0, target_y))
        self._on_viewport_changed()
        for w in self._page_widgets:
            w.update()

    def next_search_match(self):
        if not self._search_matches:
            return
        nxt = (self._current_match_idx + 1) % len(self._search_matches)
        self._scroll_to_match(nxt)

    def prev_search_match(self):
        if not self._search_matches:
            return
        prv = (self._current_match_idx - 1) % len(self._search_matches)
        self._scroll_to_match(prv)

    def search_widget_rects_for_page(self, page_num: int) -> list[QRectF]:
        rects = self._page_search_rects.get(page_num)
        if not rects:
            return []
        return [self.pdf_rect_to_widget(page_num, r) for r in rects]

    def active_search_widget_rect_for_page(self, page_num: int) -> QRectF | None:
        if 0 <= self._current_match_idx < len(self._search_matches):
            pnum, rect = self._search_matches[self._current_match_idx]
            if pnum == page_num:
                return self.pdf_rect_to_widget(page_num, rect)
        return None

    # ------------------------------------------------------------------
    # Selección y copia de texto desde el PDF
    # ------------------------------------------------------------------
    def clear_text_selection(self, except_page: int | None = None):
        for lbl in self._page_widgets:
            if except_page is None or lbl.page_num != except_page:
                lbl.clear_selection()
        if except_page is None:
            self._selected_text = ""

    def extract_selection_on_page(self, page_num: int, widget_rect: QRectF) -> tuple[str, list[QRectF]]:
        if self._doc is None or not (1 <= page_num <= len(self._doc)):
            return ("", [])
        page = self._doc[page_num - 1]
        pdf_rect = self._widget_rect_to_pdf(page_num, widget_rect)
        text = page.get_text("text", clip=pdf_rect).strip()
        word_rects: list[QRectF] = []
        if text:
            for w in page.get_text("words", clip=pdf_rect):
                wr = fitz.Rect(w[0], w[1], w[2], w[3])
                if wr.intersects(pdf_rect):
                    word_rects.append(self.pdf_rect_to_widget(page_num, wr))
        return (text, word_rects)

    def selected_text(self) -> str:
        return self._selected_text

    def copy_selected_text(self):
        if not self._selected_text:
            return
        QApplication.clipboard().setText(self._selected_text)
        preview = self._selected_text.replace("\n", " ")[:48]
        self.status_message.emit(f"Texto copiado del PDF: «{preview}»")
