# This Python file uses the following encoding: utf-8

# if __name__ == "__main__":
#     pass
import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

MIN_ZOOM = 0.5
MAX_ZOOM = 4.0

class PdfViewer(QScrollArea):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        self.container = QWidget()
        self.pages_layout = QVBoxLayout(self.container)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self.container)

        self.current_pdf = None
        self.zoom = 1.5


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
            for page in doc:
                matrix = fitz.Matrix(self.zoom, self.zoom)
                pix = page.get_pixmap(matrix = matrix)
                image = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format.Format_RGB888,
                ).copy()
                label = QLabel()
                label.setPixmap(QPixmap.fromImage(image))
                self.pages_layout.addWidget(label)


        self.current_pdf = pdf_path
        self.verticalScrollBar().setValue(scroll_pos)

    def set_zoom(self, new_zoom):
        new_zoom = max(MIN_ZOOM,min(new_zoom,MAX_ZOOM))
        self.zoom = new_zoom
        if new_zoom == self.zoom:
            return
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

