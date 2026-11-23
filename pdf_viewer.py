# This Python file uses the following encoding: utf-8

# if __name__ == "__main__":
#     pass
import fitz
from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPen
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

MIN_ZOOM = 0.5
MAX_ZOOM = 4.0

class PdfPageLabel(QLabel):
    def __init__(self, page_num: int, viewer, dark_pdf: bool = False):
        super().__init__()
        self.page_num = page_num
        self.viewer = viewer
        border_color = "#282e45" if dark_pdf else "#334155"
        bg_color = "#1a1b26" if dark_pdf else "white"
        self.setStyleSheet(f"background-color: {bg_color}; border: 1px solid {border_color};")

        self.highlight_rect = None
        self.highlight_opacity = 0.0
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(40)
        self.flash_timer.timeout.connect(self._fade_highlight)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            x_pt = pos.x() / self.viewer.zoom
            y_pt = pos.y() / self.viewer.zoom

            self.viewer.page_clicked.emit(self.page_num, x_pt, y_pt)

    def flash_highlight(self, h_pt: float, v_pt: float, w_pt: float, height_pt:float):
        z = self.viewer.zoom
        x = h_pt * z - 4
        y = (v_pt - max(height_pt, 12.0)) * z - 3
        w = max(w_pt, 60.0) * z + 8
        h = max(height_pt, 12.0) * z + 6
        self.highlight_rect = QRectF(x, y, w, h)
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
        if self.highlight_rect is not None and self.highlight_opacity > 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            fill = QColor(56, 189, 248, int(95 * self.highlight_opacity))
            border = QColor(56, 189, 248, int(220 * self.highlight_opacity))
            painter.setBrush(fill)
            painter.setPen(QPen(border, 2))
            painter.drawRoundedRect(self.highlight_rect, 4, 4)
            painter.end()

class PdfViewer(QScrollArea):
    page_clicked = Signal(int, float, float)
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        self.container = QWidget()
        self.pages_layout = QVBoxLayout(self.container)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pages_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinAndMaxSize)
        self.pages_layout.setSpacing(14)
        self.pages_layout.setContentsMargins(16, 16, 16, 16)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.container)

        self.current_pdf = None
        self.zoom = 1.0
        self.dark_pdf = False



    def clear_pages(self):
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def load_pdf(self, pdf_path):
        scroll_pos = self.verticalScrollBar().value()
        self.clear_pages()

        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                matrix = fitz.Matrix(self.zoom, self.zoom)
                pix = page.get_pixmap(matrix = matrix)
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
                    painter.fillRect(image.rect(), QColor("#1a1b26"))
                    painter.end()
                label = PdfPageLabel(page_num, self, dark_pdf=self.dark_pdf)
                pixmap = QPixmap.fromImage(image)
                label.setPixmap(pixmap)
                label.setFixedSize(pixmap.size())
                self.pages_layout.addWidget(label)


        self.current_pdf = pdf_path
        self.verticalScrollBar().setValue(scroll_pos)

    def set_dark_pdf(self, enabled: bool):
        if self.dark_pdf == enabled:
            return
        self.dark_pdf = enabled
        if self.current_pdf is not None:
            self.load_pdf(self.current_pdf)

    def scroll_to_position(self, page_num: int, y_pt: float, box_pt=None):
        index = page_num - 1
        if 0 <= index < self.pages_layout.count():
            widget = self.pages_layout.itemAt(index).widget()
            if widget is not None:
                target_y = widget.y() + int(y_pt * self.zoom) - 100
                self.verticalScrollBar().setValue(max(0, target_y))
                if box_pt is not None:
                    widget.flash_highlight(*box_pt)

    def set_zoom(self, new_zoom):
        new_zoom = max(MIN_ZOOM, min(new_zoom, MAX_ZOOM))
        if new_zoom == self.zoom:
            return
        self.zoom = new_zoom
        if self.current_pdf is not None:
            self.load_pdf(self.current_pdf)

    def zoom_in(self): self.set_zoom(self.zoom + 0.25)
    def zoom_out(self): self.set_zoom(self.zoom - 0.25)
    def reset_zoom(self): self.set_zoom(1.5)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            elif event.angleDelta().y() < 0:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

