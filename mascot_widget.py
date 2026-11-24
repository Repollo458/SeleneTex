import base64
import html
import pathlib
import re
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ai_client import extract_latex_blocks
from highlighter import SEMANTIC_TOKENS
from icons import svg_icon, svg_pixmap

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DEFAULT_OCR_PROMPT = (
    "Transcribe el contenido de esta imagen (ecuaciones, tabla o diagrama) "
    "a código LaTeX limpio listo para LuaLaTeX."
)


def encode_qimage_to_data_url(image: QImage, max_dim: int = 1600) -> tuple[str, QPixmap] | None:
    """Redimensiona si es necesario y codifica una QImage como data URL PNG/JPEG base64."""
    if image.isNull():
        return None
    img = image
    if max(img.width(), img.height()) > max_dim:
        img = img.scaled(
            max_dim,
            max_dim,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    # Usar PNG para nitidez en fórmulas matemáticas (si es muy pesado, caer a JPEG)
    ok = img.save(buf, "PNG")
    mime = "image/png"
    if not ok or ba.size() > 2_500_000:
        ba.clear()
        buf.seek(0)
        ok = img.save(buf, "JPEG", 88)
        mime = "image/jpeg"
    buf.close()
    if not ok or ba.isEmpty():
        return None

    b64 = base64.b64encode(bytes(ba.data())).decode("ascii")
    thumb = QPixmap.fromImage(img).scaled(
        36,
        36,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return f"data:{mime};base64,{b64}", thumb


def _render_inline_md(text: str, t: dict) -> str:
    """Convierte formato Markdown en línea (`code`, **bold**, *italic*) a HTML seguro."""
    # Proteger fragmentos `inline code` antes de aplicar negrita/cursiva
    code_slots: list[str] = []

    def _stash_code(m):
        idx = len(code_slots)
        code_html = (
            f"<code style=\"background:{t['bg_elevated']};color:{t['accent_text']};"
            f"font-family:'JetBrains Mono','Fira Code','DejaVu Sans Mono',monospace;"
            f"font-size:11.5px;padding:1px 4px;border-radius:4px;\">{html.escape(m.group(1))}</code>"
        )
        code_slots.append(code_html)
        return f"\x00CODE{idx}\x00"

    escaped = html.escape(text)
    escaped = re.sub(r"`([^`\n]+)`", lambda m: _stash_code(m), escaped)
    escaped = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"<i>\1</i>", escaped)
    for i, slot in enumerate(code_slots):
        escaped = escaped.replace(f"\x00CODE{i}\x00", slot)
    return escaped


def _markdown_to_html(md_text: str, t: dict, code_blocks_registry: list[str]) -> str:
    """Convierte Markdown con bloques cercados ```latex ... ``` en HTML con botones Insertar/Copiar."""
    parts: list[str] = []
    fence_re = re.compile(r"```([A-Za-z0-9_-]*)[ \t]*\n(.*?)```", re.DOTALL)
    pos = 0

    def _append_prose(chunk: str):
        if not chunk.strip():
            return
        lines = chunk.splitlines()
        in_list = False
        for line in lines:
            s = line.strip()
            if not s:
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                continue
            m_h = re.match(r"^(#{1,3})\s+(.+)$", s)
            if m_h:
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                parts.append(
                    f"<div style=\"font-weight:700;color:{t['text_primary']};margin:6px 0 3px 0;\">"
                    f"{_render_inline_md(m_h.group(2), t)}</div>"
                )
                continue
            m_li = re.match(r"^[-*•]\s+(.+)$", s)
            if m_li:
                if not in_list:
                    parts.append("<ul style=\"margin:3px 0 4px 16px;padding:0;\">")
                    in_list = True
                parts.append(f"<li style=\"margin:2px 0;\">{_render_inline_md(m_li.group(1), t)}</li>")
                continue
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<div style=\"margin:3px 0;\">{_render_inline_md(s, t)}</div>")
        if in_list:
            parts.append("</ul>")

    for m in fence_re.finditer(md_text):
        _append_prose(md_text[pos : m.start()])
        lang = (m.group(1) or "latex").strip()
        code = m.group(2).strip("\n")
        block_idx = len(code_blocks_registry)
        code_blocks_registry.append(code)
        code_esc = html.escape(code)
        parts.append(
            f"<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
            f"style=\"margin:6px 0;background:{t['bg_chrome']};border:1px solid {t['border_default']};"
            f"border-radius:8px;\">"
            f"<tr><td style=\"padding:4px 8px;background:{t['bg_surface_alt']};"
            f"border-bottom:1px solid {t['border_subtle']};font-size:10.5px;color:{t['text_muted']};\">"
            f"<b>{html.escape(lang)}</b> &nbsp;&middot;&nbsp; "
            f"<a href=\"action:insert:{block_idx}\" style=\"color:{t['accent_text']};text-decoration:none;font-weight:600;\">Insertar</a>"
            f" &nbsp;&middot;&nbsp; "
            f"<a href=\"action:replace:{block_idx}\" style=\"color:{t['text_secondary']};text-decoration:none;\">Reemplazar</a>"
            f" &nbsp;&middot;&nbsp; "
            f"<a href=\"action:copy:{block_idx}\" style=\"color:{t['text_secondary']};text-decoration:none;\">Copiar</a>"
            f"</td></tr>"
            f"<tr><td style=\"padding:7px 9px;\">"
            f"<pre style=\"margin:0;white-space:pre-wrap;font-family:'JetBrains Mono','Fira Code','DejaVu Sans Mono',monospace;"
            f"font-size:11.5px;color:{t['text_primary']};\">{code_esc}</pre>"
            f"</td></tr></table>"
        )
        pos = m.end()

    # Resto tras el último bloque (o bloque sin cerrar durante streaming)
    tail = md_text[pos:]
    if "```" in tail:
        before_fence, after_fence = tail.split("```", 1)
        _append_prose(before_fence)
        after_lines = after_fence.split("\n", 1)
        stream_code = after_lines[1] if len(after_lines) > 1 else ""
        parts.append(
            f"<div style=\"margin:6px 0;padding:7px 9px;background:{t['bg_chrome']};"
            f"border:1px solid {t['border_default']};border-radius:8px;\">"
            f"<pre style=\"margin:0;white-space:pre-wrap;font-family:'JetBrains Mono','Fira Code','DejaVu Sans Mono',monospace;"
            f"font-size:11.5px;color:{t['text_primary']};\">{html.escape(stream_code)}</pre></div>"
        )
    else:
        _append_prose(tail)

    return "".join(parts)


class SeleneMascot(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("Asistente Selene IA")
        self.setToolTip("Asistente IA de SeleneTeX (Ctrl+Shift+A)")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.state = "idle"  # "idle", "thinking", "happy"
        self.hovered = False
        self.phase = 0.0
        self.blink_counter = 0

        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(33)  # ~30 FPS
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start()

    def set_state(self, state: str):
        self.state = state
        if state == "happy":
            QTimer.singleShot(1800, lambda: self.set_state("idle") if self.state == "happy" else None)
        self.update()

    def _tick(self):
        speed = 0.22 if self.state == "thinking" else 0.06
        self.phase += speed
        self.blink_counter = (self.blink_counter + 1) % 140
        self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Anillo de foco accesible cuando se navega por teclado
        if self.hasFocus():
            p.setPen(QPen(QColor("#38bdf8"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)

        p.setPen(Qt.PenStyle.NoPen)

        # Mascota original de SeleneTeX: Búho Lunar en pixel art minimalista (4x4 px por bloque)
        px = 4
        ox = 4
        oy = 8

        # Paleta lunar de SeleneTeX (azul cielo/índigo + pecho plateado + pico/patas doradas)
        if self.state == "happy":
            feather = QColor("#38bdf8")
            wing_c = QColor("#0284c7")
            belly = QColor("#fef9c3")
            gold = QColor("#fbbf24")
        elif self.hovered or self.state == "thinking":
            feather = QColor("#7dd3fc")
            wing_c = QColor("#0ea5e9")
            belly = QColor("#f1f5f9")
            gold = QColor("#fde047")
        else:
            feather = QColor("#60a5fa")
            wing_c = QColor("#2563eb")
            belly = QColor("#e2e8f0")
            gold = QColor("#fbbf24")

        eye_bg = QColor("#f8fafc")
        pupil = QColor("#0f172a")

        def draw_px(col: int, row: int, color: QColor):
            p.fillRect(ox + col * px, oy + row * px, px, px, color)

        hop = -1 if (self.state == "happy" and int(self.phase * 1.5) % 2 == 0) else 0

        # 1. Orejitas / mechones de búho (fila 1)
        for c in (2, 3, 8, 9):
            draw_px(c, 1 + hop, wing_c if c in (2, 9) else feather)

        # 2. Cabeza y cuerpo ovalado en pixel art (filas 2..7)
        for c in range(2, 10):
            draw_px(c, 2 + hop, feather)
        for r in (3, 4):
            for c in range(1, 11):
                draw_px(c, r + hop, feather)
        for c in range(1, 11):
            draw_px(c, 5 + hop, belly if 4 <= c <= 7 else feather)
        for c in range(2, 10):
            draw_px(c, 6 + hop, belly if 4 <= c <= 7 else feather)
        for c in range(3, 9):
            draw_px(c, 7 + hop, wing_c if c in (3, 8) else belly)

        # 3. Alitas laterales con animación (hover / thinking / happy)
        flap = False
        if self.state == "happy":
            flap = True
        elif self.state == "thinking":
            flap = (int(self.phase * 1.6) % 2 == 0)
        elif self.hovered:
            flap = True
        elif self.state == "idle" and self.blink_counter > 118:
            flap = True

        if flap:
            for c in (0, 11):
                draw_px(c, 4 + hop, wing_c)
                draw_px(c, 5 + hop, wing_c)
        else:
            for c in (1, 10):
                draw_px(c, 5 + hop, wing_c)
                draw_px(c, 6 + hop, wing_c)

        # 4. Ojos grandes de búho + pico dorado
        blinking = (self.state == "idle" and self.blink_counter > 134)
        look = 0
        if self.state == "thinking":
            look = -1 if (int(self.phase * 0.7) % 2 == 0) else 0

        if blinking:
            for c in (3, 4, 7, 8):
                draw_px(c, 4 + hop, pupil)
        else:
            for ec in (3, 7):
                draw_px(ec, 3 + hop, eye_bg)
                draw_px(ec + 1, 3 + hop, eye_bg)
                draw_px(ec, 4 + hop, eye_bg)
                draw_px(ec + 1, 4 + hop, eye_bg)
            if self.state == "happy":
                draw_px(3, 3 + hop, pupil)
                draw_px(4, 3 + hop, pupil)
                draw_px(7, 3 + hop, pupil)
                draw_px(8, 3 + hop, pupil)
            else:
                draw_px(4 + look, 3 + hop, pupil)
                draw_px(4 + look, 4 + hop, pupil)
                draw_px(8 + look, 3 + hop, pupil)
                draw_px(8 + look, 4 + hop, pupil)

        # Pico dorado en el centro (cols 5..6, fila 4)
        draw_px(5, 4 + hop, gold)
        draw_px(6, 4 + hop, gold)

        # 5. Patitas doradas (fila 8)
        draw_px(4, 8 + hop, gold)
        draw_px(7, 8 + hop, gold)

        # 6. Indicadores pixel según estado (puntos de pensamiento / destellos lunares)
        if self.state == "thinking":
            active = int(self.phase * 1.2) % 3
            for i, dc in enumerate((4, 6, 8)):
                c = QColor("#fef08a") if i == active else QColor(254, 240, 138, 85)
                draw_px(dc, -1, c)
        elif self.state == "happy":
            spark = QColor("#fef08a")
            draw_px(1, 0, spark)
            draw_px(10, 0, spark)
            if int(self.phase * 2) % 2 == 0:
                draw_px(6, -1, spark)

        p.end()


class AIPromptLineEdit(QLineEdit):
    """Campo de consulta que detecta Ctrl+V con imagen en el portapapeles (Imagen a LaTeX)."""

    image_pasted = Signal(QImage)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime is not None and mime.hasImage():
                img = clipboard.image()
                if not img.isNull():
                    self.image_pasted.emit(img)
                    event.accept()
                    return
        super().keyPressEvent(event)


class QuickAIBubble(QFrame):
    prompt_submitted = Signal(str, object)  # (prompt, image_data_url | None)
    fix_error_requested = Signal()
    insert_code_requested = Signal(str)
    replace_code_requested = Signal(str)
    add_packages_requested = Signal(list)
    new_chat_requested = Signal()
    stop_requested = Signal()
    retry_requested = Signal()
    expand_toggled = Signal(bool)
    settings_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(304, 240)
        self.resize(456, 420)
        self.setObjectName("aiBubble")
        self.setAccessibleName("Panel del asistente Selene IA")
        self.setAcceptDrops(True)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(32)
        self.shadow.setOffset(0, 10)
        self.shadow.setColor(QColor(0, 0, 0, 130))
        self.setGraphicsEffect(self.shadow)

        self._theme = "dark"
        self._messages: list[dict] = []  # [{"role": "user"|"assistant"|"error", "text": str, "image_label": str}]
        self._code_blocks_registry: list[str] = []
        self._recommended_packages: list[str] = []
        self._pending_image_data_url: str | None = None
        self._pending_image_label: str = ""
        self._has_editor_selection: bool = False
        self._streaming: bool = False
        self._is_busy: bool = False
        self._expanded: bool = False
        self._last_was_error: bool = False
        self.last_response = ""
        self._has_valid_response = False

        self._stream_render_timer = QTimer(self)
        self._stream_render_timer.setSingleShot(True)
        self._stream_render_timer.setInterval(55)
        self._stream_render_timer.timeout.connect(self._render_chat)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)

        # Cabecera con acciones (Contexto, Expandir, Nueva conversación, Configurar, Cerrar)
        header = QHBoxLayout()
        header.setSpacing(5)
        self.title_icon = QLabel(self)
        title = QLabel("Selene IA", self)
        title.setObjectName("aiTitle")

        self.btn_doc_ctx = QPushButton("Contexto", self)
        self.btn_doc_ctx.setObjectName("aiCtxBtn")
        self.btn_doc_ctx.setCheckable(True)
        self.btn_doc_ctx.setChecked(True)
        self.btn_doc_ctx.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_doc_ctx.setToolTip(
            "Incluir contexto inteligente del documento (líneas cercanas al cursor, macros, \\label y \\cite)"
        )

        self.btn_expand = QPushButton(self)
        self.btn_expand.setObjectName("iconBtn")
        self.btn_expand.setIconSize(QSize(14, 14))
        self.btn_expand.setCheckable(True)
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setAccessibleName("Expandir o contraer panel IA")
        self.btn_expand.setToolTip("Expandir / contraer ventana del asistente")
        self.btn_expand.toggled.connect(self._on_expand_toggled)

        self.btn_new_chat = QPushButton(self)
        self.btn_new_chat.setObjectName("iconBtn")
        self.btn_new_chat.setIconSize(QSize(15, 15))
        self.btn_new_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_chat.setAccessibleName("Nueva conversación")
        self.btn_new_chat.setToolTip("Nueva conversación (limpiar historial)")
        self.btn_new_chat.clicked.connect(self._on_new_chat_clicked)

        self.btn_cfg = QPushButton(self)
        self.btn_cfg.setObjectName("iconBtn")
        self.btn_cfg.setIconSize(QSize(15, 15))
        self.btn_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cfg.setAccessibleName("Configurar IA")
        self.btn_cfg.setToolTip("Configurar proveedor, modelo y API Key")
        self.btn_cfg.clicked.connect(self.settings_requested.emit)

        self.btn_close = QPushButton(self)
        self.btn_close.setObjectName("iconBtn")
        self.btn_close.setIconSize(QSize(15, 15))
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setAccessibleName("Cerrar asistente IA")
        self.btn_close.setToolTip("Cerrar (Esc)")
        self.btn_close.clicked.connect(self.close_bubble)

        header.addWidget(self.title_icon)
        header.addWidget(title)
        header.addSpacing(4)
        header.addWidget(self.btn_doc_ctx)
        header.addStretch()
        header.addWidget(self.btn_expand)
        header.addWidget(self.btn_new_chat)
        header.addWidget(self.btn_cfg)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        # Barra de progreso sutil durante la generación
        self.progress = QProgressBar(self)
        self.progress.setObjectName("compileProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Área de chat multi-turno con Markdown y botones por bloque
        self.output = QTextBrowser(self)
        self.output.setObjectName("aiChatView")
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        self.output.setAccessibleName("Historial de conversación de Selene IA")
        self.output.anchorClicked.connect(self._on_chat_anchor_clicked)
        layout.addWidget(self.output, 1)

        # Chips de inicio rápido (se ocultan al comenzar a conversar)
        self.quick_chips_widget = QWidget(self)
        chips_lay = QHBoxLayout(self.quick_chips_widget)
        chips_lay.setContentsMargins(0, 0, 0, 0)
        chips_lay.setSpacing(5)
        for chip_label, starter_prompt in (
            ("Ecuación", "Escribe en LaTeX la ecuación de "),
            ("Tabla", "Crea una tabla profesional con booktabs sobre "),
            ("TikZ", "Genera un diagrama TikZ limpio de "),
            ("Resumir", "Resume y mejora la redacción académica del texto seleccionado."),
        ):
            chip = QPushButton(chip_label, self.quick_chips_widget)
            chip.setObjectName("aiChipBtn")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda checked=False, p=starter_prompt: self._use_starter_chip(p))
            chips_lay.addWidget(chip)
        chips_lay.addStretch(1)
        layout.addWidget(self.quick_chips_widget)

        # Barra sugerida de paquetes faltantes (auto-inserción en preámbulo)
        self.btn_add_pkgs = QPushButton(self)
        self.btn_add_pkgs.setObjectName("aiPkgBtn")
        self.btn_add_pkgs.setIconSize(QSize(14, 14))
        self.btn_add_pkgs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_pkgs.setToolTip("Insertar los paquetes recomendados automáticamente en el preámbulo")
        self.btn_add_pkgs.clicked.connect(self._emit_add_packages)
        self.btn_add_pkgs.hide()
        layout.addWidget(self.btn_add_pkgs)

        # Chip de vista previa de imagen adjunta (Imagen a LaTeX / OCR)
        self.image_chip = QFrame(self)
        self.image_chip.setObjectName("aiImageChip")
        chip_layout = QHBoxLayout(self.image_chip)
        chip_layout.setContentsMargins(8, 5, 6, 5)
        chip_layout.setSpacing(8)

        self.lbl_img_thumb = QLabel(self.image_chip)
        self.lbl_img_thumb.setFixedSize(36, 36)
        self.lbl_img_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_img_info = QLabel("", self.image_chip)
        self.lbl_img_info.setObjectName("aiImageLabel")

        self.btn_remove_img = QPushButton(self.image_chip)
        self.btn_remove_img.setObjectName("dockCloseBtn")
        self.btn_remove_img.setIconSize(QSize(12, 12))
        self.btn_remove_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_img.setToolTip("Quitar imagen adjunta")
        self.btn_remove_img.clicked.connect(self.clear_attached_image)

        chip_layout.addWidget(self.lbl_img_thumb)
        chip_layout.addWidget(self.lbl_img_info, 1)
        chip_layout.addWidget(self.btn_remove_img)
        self.image_chip.hide()
        layout.addWidget(self.image_chip)

        # Acciones rápidas
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_fix = QPushButton("Arreglar log", self)
        self.btn_fix.setObjectName("aiCompactBtn")
        self.btn_fix.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fix.setToolTip("Analizar el último error de LuaLaTeX con la IA")
        self.btn_fix.clicked.connect(self.fix_error_requested.emit)

        self.btn_insert = QPushButton("Insertar", self)
        self.btn_insert.setObjectName("aiCompactBtn")
        self.btn_insert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_insert.setToolTip("Insertar el último bloque LaTeX en la posición del cursor")
        self.btn_insert.setEnabled(False)
        self.btn_insert.clicked.connect(self._emit_insert)

        self.btn_replace = QPushButton("Reemplazar", self)
        self.btn_replace.setObjectName("aiCompactBtn")
        self.btn_replace.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_replace.setToolTip("Reemplazar el texto seleccionado en el editor por el bloque LaTeX")
        self.btn_replace.setEnabled(False)
        self.btn_replace.clicked.connect(self._emit_replace)

        self.btn_retry = QPushButton("Reintentar", self)
        self.btn_retry.setObjectName("aiCompactBtn")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.setToolTip("Reenviar la última consulta")
        self.btn_retry.clicked.connect(self.retry_requested.emit)
        self.btn_retry.hide()

        self.btn_copy = QPushButton(self)
        self.btn_copy.setObjectName("iconBtn")
        self.btn_copy.setIconSize(QSize(14, 14))
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setAccessibleName("Copiar código LaTeX")
        self.btn_copy.setToolTip("Copiar el último bloque LaTeX al portapapeles")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_latest_code)

        actions.addWidget(self.btn_fix)
        actions.addWidget(self.btn_insert)
        actions.addWidget(self.btn_replace)
        actions.addWidget(self.btn_retry)
        actions.addStretch(1)
        actions.addWidget(self.btn_copy)
        layout.addLayout(actions)

        # Entrada de consulta + botón adjuntar imagen
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.btn_attach_img = QPushButton(self)
        self.btn_attach_img.setObjectName("iconBtn")
        self.btn_attach_img.setIconSize(QSize(16, 16))
        self.btn_attach_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_attach_img.setAccessibleName("Adjuntar imagen para OCR a LaTeX")
        self.btn_attach_img.setToolTip("Adjuntar imagen (o pega una captura con Ctrl+V / arrástrala aquí)")
        self.btn_attach_img.clicked.connect(self._pick_image_file)

        self.input = AIPromptLineEdit(self)
        self.input.setAccessibleName("Consulta rápida para Selene IA")
        self.input.setPlaceholderText("Pregunta o pega una captura (Ctrl+V)...")
        self.input.returnPressed.connect(self._submit)
        self.input.image_pasted.connect(lambda img: self.attach_qimage(img, "Captura pegada"))

        self.btn_send = QPushButton("Enviar", self)
        self.btn_send.setObjectName("primaryBtn")
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._on_send_or_stop)

        input_row.addWidget(self.btn_attach_img)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.btn_send)
        layout.addLayout(input_row)

        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.activated.connect(self.close_bubble)

        self.set_theme("dark")
        self._render_chat()
        self.hide()

    # ------------------------------------------------------------------
    # Tema y tamaño adaptativo
    # ------------------------------------------------------------------
    def set_theme(self, theme_name: str):
        self._theme = theme_name
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])
        self.title_icon.setPixmap(svg_pixmap("sparkles", t["accent_icon"], size=16))
        self.btn_expand.setIcon(svg_icon("minimize" if self._expanded else "maximize", t["text_muted"], size=14))
        self.btn_new_chat.setIcon(svg_icon("new_chat", t["text_muted"], size=15))
        self.btn_cfg.setIcon(svg_icon("settings", t["text_muted"], size=15))
        self.btn_close.setIcon(svg_icon("close", t["text_muted"], size=15))
        self.btn_attach_img.setIcon(svg_icon("file_image", t["text_secondary"], size=16))
        self.btn_copy.setIcon(svg_icon("copy", t["text_secondary"], size=14))
        self.btn_remove_img.setIcon(svg_icon("close", t["text_muted"], size=12))
        self.btn_add_pkgs.setIcon(svg_icon("package", t["success_text"], size=14))
        self.shadow.setColor(QColor(15, 23, 42, 135 if theme_name == "dark" else 42))
        self._render_chat()

    def include_doc_context(self) -> bool:
        return self.btn_doc_ctx.isChecked()

    def _on_expand_toggled(self, expanded: bool):
        self._expanded = bool(expanded)
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        self.btn_expand.setIcon(svg_icon("minimize" if self._expanded else "maximize", t["text_muted"], size=14))
        self.expand_toggled.emit(self._expanded)

    def _use_starter_chip(self, prompt: str):
        if prompt.endswith("."):
            self.input.setText(prompt)
            self._submit()
        else:
            self.input.setText(prompt)
            self.input.setFocus()
            self.input.end(False)

    def adapt_to_parent(self, parent_width: int, parent_height: int, max_height: int | None = None):
        """Adapta el tamaño de la burbuja de forma fluida al contenedor disponible."""
        max_w = 680 if self._expanded else 468
        max_h = 580 if self._expanded else 432
        target_w = max(304, min(max_w, parent_width - 24))
        avail_h = (parent_height - 96) if max_height is None else max_height
        target_h = max(240, min(max_h, avail_h))
        if self.width() != target_w or self.height() != target_h:
            self.resize(target_w, target_h)

    def close_bubble(self):
        self.hide()
        self.closed.emit()

    # ------------------------------------------------------------------
    # Adjuntar / Pegar / Arrastrar imágenes (Imagen a LaTeX)
    # ------------------------------------------------------------------
    def _pick_image_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen para convertir a LaTeX",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_name:
            self.attach_image_file(pathlib.Path(file_name))

    def attach_image_file(self, path: pathlib.Path) -> bool:
        img = QImage(str(path))
        if img.isNull():
            return False
        return self.attach_qimage(img, path.name)

    def attach_qimage(self, image: QImage, label: str = "Imagen") -> bool:
        encoded = encode_qimage_to_data_url(image)
        if encoded is None:
            return False
        data_url, thumb = encoded
        self._pending_image_data_url = data_url
        self._pending_image_label = f"{label} ({image.width()}×{image.height()})"
        self.lbl_img_thumb.setPixmap(thumb)
        self.lbl_img_info.setText(self._pending_image_label)
        self.image_chip.show()
        self.input.setPlaceholderText("Instrucción opcional (Enter para transcribir a LaTeX)...")
        self.input.setFocus()
        return True

    def clear_attached_image(self):
        self._pending_image_data_url = None
        self._pending_image_label = ""
        self.lbl_img_thumb.clear()
        self.lbl_img_info.clear()
        self.image_chip.hide()
        self.input.setPlaceholderText("Pregunta o pega una captura (Ctrl+V)...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = pathlib.Path(url.toLocalFile())
                if p.suffix.lower() in IMAGE_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        elif event.mimeData().hasImage():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = pathlib.Path(url.toLocalFile())
                if p.suffix.lower() in IMAGE_EXTENSIONS and self.attach_image_file(p):
                    event.acceptProposedAction()
                    return
        elif event.mimeData().hasImage():
            img = event.mimeData().imageData()
            if isinstance(img, QImage) and self.attach_qimage(img, "Imagen arrastrada"):
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    # ------------------------------------------------------------------
    # Historial multi-turno y renderizado Markdown
    # ------------------------------------------------------------------
    def _on_new_chat_clicked(self):
        self.clear_chat()
        self.new_chat_requested.emit()

    def clear_chat(self):
        self._messages.clear()
        self._code_blocks_registry.clear()
        self._streaming = False
        self._last_was_error = False
        self.btn_retry.hide()
        self.last_response = ""
        self._has_valid_response = False
        self.clear_attached_image()
        self.set_recommended_packages([])
        self._update_action_buttons()
        self._render_chat()

    def add_user_message(self, display_text: str, image_label: str = ""):
        self._messages.append({
            "role": "user",
            "text": display_text,
            "image_label": image_label,
        })
        self._render_chat()

    def set_has_editor_selection(self, has_selection: bool):
        self._has_editor_selection = has_selection
        self._update_action_buttons()

    def set_recommended_packages(self, packages: list[str]):
        self._recommended_packages = list(packages)
        if self._recommended_packages:
            pkg_str = ", ".join(self._recommended_packages)
            self.btn_add_pkgs.setText(f" + Añadir \\usepackage{{{pkg_str}}} al preámbulo")
            self.btn_add_pkgs.show()
        else:
            self.btn_add_pkgs.hide()

    def _emit_add_packages(self):
        if not self._recommended_packages:
            return
        pkgs = list(self._recommended_packages)
        self.set_recommended_packages([])
        self.add_packages_requested.emit(pkgs)

    def _update_action_buttons(self):
        can_use = self._has_valid_response and not self._is_busy
        self.btn_insert.setEnabled(can_use)
        self.btn_copy.setEnabled(can_use)
        self.btn_replace.setEnabled(can_use and self._has_editor_selection)

    def _extract_latest_code(self) -> str:
        blocks = extract_latex_blocks(self.last_response)
        if blocks:
            return blocks[-1]
        return self.last_response.strip()

    def _submit(self):
        if self._is_busy:
            return
        text = self.input.text().strip()
        image_url = self._pending_image_data_url
        image_label = self._pending_image_label

        if not text and not image_url:
            return
        if not text and image_url:
            text = DEFAULT_OCR_PROMPT

        self.input.clear()
        self.clear_attached_image()
        self.add_user_message(text, image_label=image_label)
        self.prompt_submitted.emit(text, image_url)

    def _emit_insert(self):
        if not self.last_response or not self._has_valid_response:
            return
        self.insert_code_requested.emit(self._extract_latest_code())

    def _emit_replace(self):
        if not self.last_response or not self._has_valid_response:
            return
        self.replace_code_requested.emit(self._extract_latest_code())

    def _copy_latest_code(self):
        if not self.last_response or not self._has_valid_response:
            return
        QApplication.clipboard().setText(self._extract_latest_code())

    def _on_send_or_stop(self):
        if self._is_busy:
            self.stop_requested.emit()
        else:
            self._submit()

    def _on_chat_anchor_clicked(self, url):
        target = url.toString()
        if not target.startswith("action:"):
            return
        parts = target.split(":")
        if len(parts) != 3:
            return
        kind, idx_str = parts[1], parts[2]
        try:
            idx = int(idx_str)
            code = self._code_blocks_registry[idx]
        except (ValueError, IndexError):
            return
        if kind == "insert":
            self.insert_code_requested.emit(code)
        elif kind == "replace":
            self.replace_code_requested.emit(code)
        elif kind == "copy":
            QApplication.clipboard().setText(code)

    def set_busy(self, busy: bool):
        self._is_busy = busy
        self.btn_fix.setEnabled(not busy)
        self.btn_attach_img.setEnabled(not busy)
        self.btn_new_chat.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self._streaming = False
            self._last_was_error = False
            self.btn_retry.hide()
            self.last_response = ""
            self._has_valid_response = False
            self.set_recommended_packages([])
            self.btn_send.setText("Detener")
            self.btn_send.setObjectName("stopBtn")
            self.btn_send.style().unpolish(self.btn_send)
            self.btn_send.style().polish(self.btn_send)
            self._messages.append({"role": "assistant", "text": "_Generando respuesta…_", "image_label": ""})
            self._render_chat()
        else:
            self.btn_send.setText("Enviar")
            self.btn_send.setObjectName("primaryBtn")
            self.btn_send.style().unpolish(self.btn_send)
            self.btn_send.style().polish(self.btn_send)
        self._update_action_buttons()

    def append_chunk(self, chunk: str):
        if not self._streaming:
            self._streaming = True
            self.last_response = ""
            if self._messages and self._messages[-1]["role"] == "assistant":
                self._messages[-1]["text"] = ""
            else:
                self._messages.append({"role": "assistant", "text": "", "image_label": ""})
        self.last_response += chunk
        self._messages[-1]["text"] = self.last_response
        if not self._stream_render_timer.isActive():
            self._stream_render_timer.start()

    def set_response(self, text: str, is_error: bool = False):
        self._stream_render_timer.stop()
        self._streaming = False
        self._last_was_error = is_error
        self.btn_retry.setVisible(is_error)
        self.last_response = text
        self._has_valid_response = bool(text.strip()) and not is_error
        role = "error" if is_error else "assistant"
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages[-1]["role"] = role
            self._messages[-1]["text"] = text
        else:
            self._messages.append({"role": role, "text": text, "image_label": ""})
        self._render_chat()
        self._update_action_buttons()

    def _render_chat(self):
        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        self._code_blocks_registry = []
        if hasattr(self, "quick_chips_widget"):
            self.quick_chips_widget.setVisible(len(self._messages) == 0)

        if not self._messages:
            empty_html = (
                f"<div style=\"color:{t['text_muted']};font-size:12.5px;padding:8px 6px;line-height:1.45;\">"
                f"<p style=\"font-weight:600;color:{t['text_secondary']};margin:0 0 8px 0;\">"
                f"¿En qué te ayudo con tu documento LaTeX?</p>"
                f"<p style=\"margin:0 0 5px 0;\">• Escribe una consulta o sigue una conversación multi-turno.</p>"
                f"<p style=\"margin:0 0 5px 0;\">• <b>Imagen a LaTeX</b>: pega una captura (<code>Ctrl+V</code>), arrastra una foto o pulsa el icono de imagen.</p>"
                f"<p style=\"margin:0;\">• Selecciona texto en el editor y haz <b>clic derecho → Selene IA</b> para reescribir, explicar o traducir.</p>"
                f"</div>"
            )
            self.output.setHtml(empty_html)
            return

        blocks: list[str] = []
        for msg in self._messages:
            role = msg["role"]
            text = msg["text"]
            img_label = msg.get("image_label", "")
            if role == "user":
                img_badge = ""
                if img_label:
                    img_badge = (
                        f"<div style=\"font-size:11px;color:{t['accent_text']};margin-bottom:3px;\">"
                        f"🖼 {html.escape(img_label)}</div>"
                    )
                blocks.append(
                    f"<div style=\"margin:6px 0 8px 18px;padding:7px 10px;"
                    f"background:{t['accent_soft_bg']};border-radius:9px;"
                    f"color:{t['text_primary']};font-size:12.5px;\">"
                    f"{img_badge}{html.escape(text).replace(chr(10), '<br>')}"
                    f"</div>"
                )
            elif role == "error":
                blocks.append(
                    f"<div style=\"margin:6px 0;padding:8px 10px;"
                    f"background:{t['danger_bg']};border:1px solid {t['danger_border']};"
                    f"border-radius:9px;color:{t['danger_text']};font-size:12px;\">"
                    f"{html.escape(text).replace(chr(10), '<br>')}"
                    f"</div>"
                )
            else:
                rendered = _markdown_to_html(text, t, self._code_blocks_registry)
                blocks.append(
                    f"<div style=\"margin:4px 6px 10px 0;color:{t['text_primary']};"
                    f"font-size:12.5px;line-height:1.45;\">{rendered}</div>"
                )

        body = (
            f"<html><body style=\"margin:0;padding:2px;font-family:'Inter','Segoe UI','Ubuntu',sans-serif;\">"
            f"{''.join(blocks)}</body></html>"
        )
        self.output.setHtml(body)
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())
