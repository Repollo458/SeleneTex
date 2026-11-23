# This Python file uses the following encoding: utf-8
import re
from PySide6.QtCore import QRect, QSize, QStringListModel, Qt
from PySide6.QtGui import QColor, QPainter, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget, QCompleter

from templates import LATEX_COMMANDS

class LineNumberArea(QWidget):
    def __init__(self,editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.dark_mode = True
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        self.completer_model = QStringListModel(sorted(set(LATEX_COMMANDS)), self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)

    def line_number_area_width(self):
        digits = max(2, len(str(max(1,self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0,0,0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0,dy)
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
        bg_color = QColor("#252526") if self.dark_mode else QColor("#f3f3f3")
        fg_color = QColor("#858585") if self.dark_mode else QColor("#6e7781")
        painter.fillRect(event.rect(), bg_color)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(fg_color)
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2a2d2e") if self.dark_mode else QColor("#f0f6ff")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def set_dark_mode(self, dark: bool):
        self.dark_mode = dark
        self.highlight_current_line()
        self.line_number_area.update()

    def go_to_line(self, line_number: int):
        block = self.document().findBlockByLineNumber(line_number - 1)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()
            self.setFocus()

    def current_command_prefix(self):
        cursor = self.textCursor()
        line_text = cursor.block().text()[:cursor.positionInBlock()]
        match = re.search(r"\\[A-Za-z@]*$", line_text)
        return match.group(0) if match else ""

    def insert_completion(self, completion: str):
        prefix = self.current_command_prefix()
        cursor = self.textCursor()

        if prefix:
            cursor.movePosition(
                cursor.MoveOperation.Left,
                cursor.MoveMode.KeepAnchor,
                len(prefix),
            )
        cursor.insertText(completion)
        empty_brace = completion.find("{}")
        if empty_brace != -1:
            offset = len(completion) - empty_brace - 1
            cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, offset)
        self.setTextCursor(cursor)

    def update_custom_commands(self):
        text = self.toPlainText()
        custom = set()
        # Busca \newcommand{\nombre}[n_args opcional]
        pattern = re.compile(r"\\(?:newcommand|renewcommand)\*?\{(\\[A-Za-z@]+)\}(?:\[(\d)\])?")
        for match in pattern.finditer(text):
            cmd_name = match.group(1)
            num_args = int(match.group(2)) if match.group(2) else 0
            custom.add(cmd_name + ("{}" * num_args))

        all_commands = sorted(set(LATEX_COMMANDS) | custom)
        self.completer_model.setStringList(all_commands)


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

        super().keyPressEvent(event)

        prefix = self.current_command_prefix()
        if len(prefix) < 2:
            self.completer.popup().hide()
            return

        if prefix != self.completer.completionPrefix():
            self.update_custom_commands()
            self.completer.setCompletionPrefix(prefix)
            self.completer.popup().setCurrentIndex(
                self.completer.completionModel().index(0, 0)
            )

        cr = self.cursorRect()
        cr.setWidth(
            self.completer.popup().sizeHintForColumn(0)
            + self.completer.popup().verticalScrollBar().sizeHint().width()
            + 20
        )
        self.completer.complete(cr)




