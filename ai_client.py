# This Python file uses the following encoding: utf-8
"""Cliente IA de SeleneTeX: streaming OpenAI-compatible, multimodal (Imagen a LaTeX),
detección automática de modelos Ollama, prueba de conexión y visor de diff."""

import difflib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QSettings, QSize, QThread, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from highlighter import SEMANTIC_TOKENS
from icons import svg_icon, svg_pixmap

PROVIDERS = {
    "Google Gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-3.8-flash",
        "needs_key": True,
        "env_var": "GEMINI_API_KEY",
    },
    "Ollama (Local)": {
        "url": "http://localhost:11434/v1/chat/completions",
        "default_model": "qwen2.5-coder:3b",
        "needs_key": False,
        "env_var": "",
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "needs_key": True,
        "env_var": "OPENAI_API_KEY",
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemini-2.5-flash",
        "needs_key": True,
        "env_var": "OPENROUTER_API_KEY",
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "needs_key": True,
        "env_var": "GROQ_API_KEY",
    },
    "Personalizado (OpenAI-compatible)": {
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "needs_key": False,
        "env_var": "",
    },
}

TEMPERATURE_PRESETS: list[tuple[str, float]] = [
    ("Preciso (LaTeX y correcciones)", 0.2),
    ("Equilibrado", 0.5),
    ("Creativo (Redacción)", 0.8),
]

SYSTEM_PROMPT = (
    "Eres Selene IA, el asistente experto en LaTeX integrado dentro de SeleneTeX, "
    "un editor de escritorio profesional (PySide6) con pestañas múltiples, visor PDF con SyncTeX, "
    "previsualización de fórmulas, autocompletado y panel de diagnósticos.\n"
    "Reglas de respuesta:\n"
    "- Responde siempre en español, de forma clara, directa y concisa.\n"
    "- Respeta el motor activo indicado en el contexto (LuaLaTeX/XeLaTeX usan `fontspec` y UTF-8 nativo; "
    "pdfLaTeX usa `inputenc`/`fontenc`).\n"
    "- Cuando te pidan código LaTeX, corregir un error o transcribir una imagen (ecuación, tabla o diagrama TikZ), "
    "entrega el fragmento listo para insertar dentro de un bloque ```latex ... ``` (sin \\documentclass ni "
    "\\begin{document} salvo que te pidan un documento completo).\n"
    "- Reutiliza las macros (\\newcommand), etiquetas (\\label) y claves BibTeX (\\cite) existentes en el contexto "
    "del proyecto cuando sean relevantes, en lugar de inventarlas.\n"
    "- Si tu solución requiere algún paquete que aún no está cargado, indícalo explícitamente como "
    "\\usepackage{nombre_paquete} para que el usuario pueda añadirlo al preámbulo con un clic."
)

_IGNORED_DOC_PACKAGES = {
    "article", "report", "book", "beamer", "letter", "standalone", "memoir",
    "inputenc", "fontenc", "utf8", "T1",
}


def resolve_ai_config(settings: QSettings) -> dict:
    """Resuelve proveedor, URL, modelo, API key (con respaldo en variable de entorno) y temperatura."""
    provider_name = settings.value("ai/provider", "Google Gemini", type=str)
    # Compatibilidad con nombre anterior
    if provider_name == "OpenAI / Custom":
        provider_name = "OpenAI"
    info = PROVIDERS.get(provider_name, PROVIDERS["Google Gemini"])
    url = (settings.value("ai/url", info["url"], type=str) or info["url"]).strip()
    model = (settings.value("ai/model", info["default_model"], type=str) or info["default_model"]).strip()
    if model == "gemini-2.5-flash" and provider_name == "Google Gemini":
        model = "gemini-3.8-flash"
        settings.setValue("ai/model", model)
    api_key = (settings.value("ai/api_key", "", type=str) or "").strip()
    env_var = info.get("env_var", "")
    if not api_key and env_var:
        api_key = os.environ.get(env_var, "").strip()

    try:
        temperature = float(settings.value("ai/temperature", 0.2))
    except (TypeError, ValueError):
        temperature = 0.2
    temperature = max(0.0, min(1.5, temperature))

    is_local = (
        provider_name == "Ollama (Local)"
        or "localhost" in url
        or "127.0.0.1" in url
    )
    return {
        "provider": provider_name,
        "url": url,
        "model": model,
        "api_key": api_key,
        "needs_key": bool(info.get("needs_key", False)),
        "env_var": env_var,
        "temperature": temperature,
        "is_local": is_local,
    }


def extract_latex_blocks(text: str) -> list[str]:
    """Extrae todos los bloques de código cercados (```latex / ```tex / ```) de una respuesta."""
    if not text:
        return []
    return [
        m.group(1).strip()
        for m in re.finditer(r"```(?:latex|tex|bibtex|bib)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m.group(1).strip()
    ]


def extract_recommended_packages(response_text: str, existing_packages: list[str]) -> list[str]:
    """Detecta paquetes \\usepackage{...} sugeridos por la IA que aún no están en el documento."""
    if not response_text:
        return []
    existing = {p.strip() for p in existing_packages} | _IGNORED_DOC_PACKAGES
    found: list[str] = []
    seen: set[str] = set()

    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", response_text):
        for raw in m.group(1).split(","):
            pkg = raw.strip()
            if (
                pkg
                and re.fullmatch(r"[A-Za-z0-9_-]+", pkg)
                and pkg not in existing
                and pkg not in seen
            ):
                seen.add(pkg)
                found.append(pkg)
    return found


class AIWorker(QThread):
    chunk_received = Signal(str)
    response_ready = Signal(str)
    error_occurred = Signal(str)
    cancelled = Signal(str)

    def __init__(
        self,
        prompt: str,
        settings: QSettings,
        parent=None,
        doc_context: str = "",
        history: list[dict] | None = None,
        image_data_url: str | None = None,
    ):
        super().__init__(parent)
        self.prompt = prompt
        self.settings = settings
        self.doc_context = doc_context
        self.history = list(history) if history else []
        self.image_data_url = image_data_url
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        cfg = resolve_ai_config(self.settings)
        provider_name = cfg["provider"]
        url = cfg["url"]
        model = cfg["model"]
        api_key = cfg["api_key"]
        is_local = cfg["is_local"]

        if cfg["needs_key"] and not api_key:
            env_hint = f" (o define {cfg['env_var']})" if cfg["env_var"] else ""
            self.error_occurred.emit(
                f"Falta la API Key para {provider_name}{env_hint}. Pulsa ⚙ para configurarla."
            )
            return

        timeout = 180 if is_local else 75

        system_content = SYSTEM_PROMPT
        if self.doc_context:
            system_content = f"{SYSTEM_PROMPT}\n\nContexto del documento actual en SeleneTeX:\n{self.doc_context}"

        messages: list[dict] = [{"role": "system", "content": system_content}]
        for turn in self.history[-12:]:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})

        if self.image_data_url:
            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.prompt},
                    {"type": "image_url", "image_url": {"url": self.image_data_url}},
                ],
            }
        else:
            user_message = {"role": "user", "content": self.prompt}
        messages.append(user_message)

        payload_dict = {
            "model": model,
            "stream": True,
            "temperature": cfg["temperature"],
            "messages": messages,
        }
        payload = json.dumps(payload_dict).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if api_key and not is_local:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        max_attempts = 3
        for attempt in range(max_attempts):
            if self._cancel_requested:
                self.cancelled.emit("")
                return
            try:
                full_text: list[str] = []
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    if "text/event-stream" in content_type or is_local:
                        for raw_line in resp:
                            if self._cancel_requested:
                                self.cancelled.emit("".join(full_text).strip())
                                return
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line:
                                continue
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue
                                choices = chunk_data.get("choices") or []
                                if not choices:
                                    continue
                                delta = choices[0].get("delta") or {}
                                piece = delta.get("content") or ""
                                if piece:
                                    full_text.append(piece)
                                    self.chunk_received.emit(piece)
                            elif line.startswith("{"):
                                data = json.loads(line)
                                piece = data["choices"][0]["message"]["content"]
                                full_text.append(piece)
                                self.chunk_received.emit(piece)
                                break
                    else:
                        data = json.loads(resp.read().decode("utf-8"))
                        full_text.append(data["choices"][0]["message"]["content"])

                if self._cancel_requested:
                    self.cancelled.emit("".join(full_text).strip())
                    return
                self.response_ready.emit("".join(full_text).strip())
                return
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code in (429, 503) and attempt < max_attempts - 1 and not self._cancel_requested:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if e.code == 503:
                    self.error_occurred.emit(
                        f"El modelo '{model}' está temporalmente saturado (HTTP 503).\n"
                        "Inténtalo de nuevo en unos segundos o cambia de modelo en ⚙."
                    )
                elif e.code == 401:
                    self.error_occurred.emit(
                        f"API Key rechazada por {provider_name} (HTTP 401). Revisa tu clave en ⚙."
                    )
                elif e.code == 400 and self.image_data_url:
                    self.error_occurred.emit(
                        f"El modelo '{model}' rechazó la imagen adjunta (HTTP 400).\n"
                        "Para Imagen a LaTeX usa un modelo multimodal (p. ej. Gemini o qwen2.5vl / llama3.2-vision en Ollama)."
                    )
                elif e.code == 404 and is_local:
                    self.error_occurred.emit(
                        f"Modelo '{model}' no encontrado en Ollama (HTTP 404).\n"
                        "Pulsa ⚙ → Detectar modelos para elegir uno instalado."
                    )
                else:
                    self.error_occurred.emit(f"Error HTTP {e.code}:\n{body[:300]}")
                return
            except TimeoutError:
                self.error_occurred.emit(
                    f"Tiempo de espera agotado ({timeout}s) esperando a '{model}'.\n"
                    "En local por CPU, prueba un modelo más ligero (p. ej. qwen2.5-coder:1.5b)."
                )
                return
            except Exception as e:
                if self._cancel_requested:
                    self.cancelled.emit("")
                    return
                self.error_occurred.emit(f"No se pudo conectar con la IA:\n{e}")
                return


class OllamaModelsWorker(QThread):
    """Consulta /api/tags en el servidor Ollama local para listar modelos instalados."""

    models_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, endpoint_url: str, parent=None):
        super().__init__(parent)
        self.endpoint_url = endpoint_url

    def run(self):
        parsed = urllib.parse.urlparse(self.endpoint_url or "http://localhost:11434")
        base = f"{parsed.scheme or 'http'}://{parsed.netloc or 'localhost:11434'}"
        tags_url = f"{base}/api/tags"
        try:
            with urllib.request.urlopen(tags_url, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            names = [m.get("name", "").strip() for m in data.get("models", []) if m.get("name")]
            if not names:
                self.error_occurred.emit("Ollama está activo, pero no tiene modelos descargados (`ollama pull qwen2.5-coder:3b`).")
                return
            self.models_ready.emit(names)
        except Exception as e:
            self.error_occurred.emit(f"No se pudo conectar con Ollama en {base}.\n¿Está iniciado el servicio? ({e})")


class AITestConnectionWorker(QThread):
    """Envía una petición mínima de comprobación al endpoint configurado."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, model: str, api_key: str, is_local: bool, parent=None):
        super().__init__(parent)
        self.url = url
        self.model = model
        self.api_key = api_key
        self.is_local = is_local

    def run(self):
        payload = json.dumps({
            "model": self.model,
            "stream": False,
            "max_tokens": 12,
            "messages": [{"role": "user", "content": "Responde solo: OK"}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key and not self.is_local:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            reply = data["choices"][0]["message"]["content"].strip()
            self.succeeded.emit(f"✓ Conexión verificada con «{self.model}» ({reply[:30]})")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            self.failed.emit(f"Error HTTP {e.code}: {body}")
        except Exception as e:
            self.failed.emit(f"No se pudo conectar: {e}")


class ChevronComboBox(QComboBox):
    """QComboBox con chevron SVG nítido adaptado al tema actual."""

    def __init__(self, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self._chevron_color = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])["text_muted"]

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pm = svg_pixmap("chevron_down", self._chevron_color, size=14, stroke_width=2.0)
        x = self.width() - 24
        y = (self.height() - 14) // 2
        painter.drawPixmap(x, y, pm)
        painter.end()


class AIDiffDialog(QDialog):
    """Visor visual de cambios (Diff) antes de reemplazar código seleccionado en el editor."""

    def __init__(self, original: str, proposed: str, theme_name: str = "dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisar cambios propuestos — Selene IA")
        self.setMinimumSize(600, 420)
        self.resize(680, 480)
        t = SEMANTIC_TOKENS.get(theme_name, SEMANTIC_TOKENS["dark"])

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("Revisar cambios antes de aplicar", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Las líneas en rojo se eliminarán y las líneas en verde se insertarán en lugar de tu selección.",
            self,
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        view = QTextBrowser(self)
        view.setObjectName("aiChatView")
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(),
                proposed.splitlines(),
                fromfile="Original",
                tofile="Selene IA",
                lineterm="",
                n=3,
            )
        )
        rows_html: list[str] = []
        if not diff_lines:
            rows_html.append(
                f"<div style='color:{t['text_muted']};padding:8px;'>El código propuesto es idéntico a tu selección.</div>"
            )
        else:
            for ln in diff_lines:
                if ln.startswith(("---", "+++")):
                    continue
                esc = html.escape(ln)
                if ln.startswith("@@"):
                    rows_html.append(
                        f"<div style='color:{t['accent_text']};background:{t['bg_surface_alt']};"
                        f"padding:2px 6px;margin-top:4px;font-weight:600;'>{esc}</div>"
                    )
                elif ln.startswith("+"):
                    rows_html.append(
                        f"<div style='color:{t['success_text']};background:{t['success_bg']};padding:1px 6px;'>{esc}</div>"
                    )
                elif ln.startswith("-"):
                    rows_html.append(
                        f"<div style='color:{t['danger_text']};background:{t['danger_bg']};padding:1px 6px;'>{esc}</div>"
                    )
                else:
                    rows_html.append(
                        f"<div style='color:{t['text_secondary']};padding:1px 6px;'>{esc}</div>"
                    )

        view.setHtml(
            "<html><body style=\"margin:0;font-family:'JetBrains Mono','Fira Code','DejaVu Sans Mono',monospace;"
            f"font-size:12px;white-space:pre-wrap;\">{''.join(rows_html)}</body></html>"
        )
        root.addWidget(view, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Aplicar cambios", self)
        btn_apply.setObjectName("primaryBtn")
        btn_apply.setDefault(True)
        btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply.clicked.connect(self.accept)

        btns.addWidget(btn_cancel)
        btns.addWidget(btn_apply)
        root.addLayout(btns)


class AISettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._theme = "dark" if settings.value("ui/dark_theme", True, type=bool) else "light"
        self._ollama_worker: OllamaModelsWorker | None = None
        self._test_worker: AITestConnectionWorker | None = None

        self.setWindowTitle("Configurar Asistente IA — SeleneTeX")
        self.setMinimumWidth(540)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Configuración de Selene IA", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Conecta Google Gemini, un modelo local con Ollama (100 % privado) o cualquier proveedor OpenAI-compatible.",
            self,
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        def add_field(label_text: str, widget, helper_text: str = ""):
            block = QVBoxLayout()
            block.setSpacing(6)
            lbl = QLabel(label_text, self)
            lbl.setObjectName("fieldLabel")
            if isinstance(widget, (QLineEdit, QComboBox)):
                lbl.setBuddy(widget)
            block.addWidget(lbl)
            if isinstance(widget, QHBoxLayout):
                block.addLayout(widget)
            else:
                block.addWidget(widget)
            if helper_text:
                hint = QLabel(helper_text, self)
                hint.setObjectName("fieldHint")
                hint.setWordWrap(True)
                hint.setContentsMargins(0, 2, 0, 0)
                block.addWidget(hint)
            root.addLayout(block)

        saved_provider = settings.value("ai/provider", "Google Gemini", type=str)
        if saved_provider == "OpenAI / Custom":
            saved_provider = "OpenAI"
        if saved_provider not in PROVIDERS:
            saved_provider = "Google Gemini"

        self.provider_combo = ChevronComboBox(self._theme, self)
        self.provider_combo.setAccessibleName("Proveedor de IA")
        self.provider_combo.addItems(list(PROVIDERS.keys()))
        self.provider_combo.setCurrentText(saved_provider)
        add_field("Proveedor", self.provider_combo)

        saved_model = settings.value("ai/model", PROVIDERS[saved_provider]["default_model"], type=str)
        if saved_model == "gemini-2.5-flash" and saved_provider == "Google Gemini":
            saved_model = "gemini-3.8-flash"
        self.model_input = QLineEdit(saved_model, self)
        self.model_input.setAccessibleName("Nombre del modelo")
        self.model_input.setPlaceholderText("Ej. gemini-3.8-flash o qwen2.5-coder:3b")

        self.btn_detect_ollama = QPushButton("Detectar modelos", self)
        self.btn_detect_ollama.setObjectName("aiCompactBtn")
        self.btn_detect_ollama.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detect_ollama.setToolTip("Detectar automáticamente los modelos descargados en Ollama local")
        self.btn_detect_ollama.clicked.connect(self._detect_ollama_models)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        model_row.addWidget(self.model_input, 1)
        model_row.addWidget(self.btn_detect_ollama)
        add_field("Modelo", model_row)

        self.temp_combo = ChevronComboBox(self._theme, self)
        for label, _ in TEMPERATURE_PRESETS:
            self.temp_combo.addItem(label)
        try:
            saved_temp = float(settings.value("ai/temperature", 0.2))
        except (TypeError, ValueError):
            saved_temp = 0.2
        best_idx = min(range(len(TEMPERATURE_PRESETS)), key=lambda i: abs(TEMPERATURE_PRESETS[i][1] - saved_temp))
        self.temp_combo.setCurrentIndex(best_idx)
        add_field(
            "Estilo de respuesta",
            self.temp_combo,
            "«Preciso» reduce errores de sintaxis LaTeX; «Creativo» es útil para redactar prosa.",
        )

        self.url_input = QLineEdit(settings.value("ai/url", PROVIDERS[saved_provider]["url"], type=str), self)
        self.url_input.setAccessibleName("Endpoint URL")
        self.url_input.setPlaceholderText("https://...")
        add_field("Endpoint URL", self.url_input)

        self.key_input = QLineEdit(settings.value("ai/api_key", "", type=str), self)
        self.key_input.setAccessibleName("Clave API")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Pega tu API Key (opcional para Ollama local o variable de entorno)")

        t = SEMANTIC_TOKENS.get(self._theme, SEMANTIC_TOKENS["dark"])
        self._icon_eye = svg_icon("eye", t["text_muted"], size=16)
        self._icon_eye_off = svg_icon("eye_off", t["accent_text"], size=16)

        self.btn_toggle_key = QPushButton(self)
        self.btn_toggle_key.setObjectName("iconBtn")
        self.btn_toggle_key.setIcon(self._icon_eye)
        self.btn_toggle_key.setIconSize(QSize(16, 16))
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_key.setAccessibleName("Mostrar u ocultar API Key")
        self.btn_toggle_key.setToolTip("Mostrar u ocultar la API Key")
        self.btn_toggle_key.toggled.connect(self._toggle_key_visibility)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.key_input, 1)
        key_row.addWidget(self.btn_toggle_key)
        add_field(
            "API Key",
            key_row,
            "Guardada solo en local. También lee GEMINI_API_KEY / OPENAI_API_KEY.",
        )

        # Banners de estado (error / éxito)
        self.error_banner = QLabel("", self)
        self.error_banner.setObjectName("fieldError")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        root.addWidget(self.error_banner)

        self.success_banner = QLabel("", self)
        self.success_banner.setObjectName("fieldSuccess")
        self.success_banner.setWordWrap(True)
        self.success_banner.hide()
        root.addWidget(self.success_banner)

        # Acciones del diálogo
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_test = QPushButton("Probar conexión", self)
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.clicked.connect(self._test_connection)
        btn_row.addWidget(self.btn_test)

        btn_row.addStretch(1)

        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Guardar configuración", self)
        btn_save.setObjectName("primaryBtn")
        btn_save.setDefault(True)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save_and_accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.model_input.textChanged.connect(self._clear_banners)
        self.url_input.textChanged.connect(self._on_url_changed)
        self.key_input.textChanged.connect(self._clear_banners)
        self._update_ollama_button_visibility()

    def _clear_banners(self, *_):
        self.error_banner.hide()
        self.success_banner.hide()

    def _update_ollama_button_visibility(self):
        provider = self.provider_combo.currentText()
        url = self.url_input.text()
        is_local = provider == "Ollama (Local)" or "localhost" in url or "127.0.0.1" in url
        self.btn_detect_ollama.setVisible(is_local)

    def _on_url_changed(self, *_):
        self._clear_banners()
        self._update_ollama_button_visibility()

    def _toggle_key_visibility(self, visible: bool):
        self.key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.btn_toggle_key.setIcon(self._icon_eye_off if visible else self._icon_eye)

    def _on_provider_changed(self, name: str):
        info = PROVIDERS[name]
        self.model_input.setText(info["default_model"])
        self.url_input.setText(info["url"])
        self._clear_banners()
        self._update_ollama_button_visibility()

    def _detect_ollama_models(self):
        if self._ollama_worker is not None and self._ollama_worker.isRunning():
            return
        self._clear_banners()
        self.btn_detect_ollama.setEnabled(False)
        self.btn_detect_ollama.setText("Buscando...")
        self._ollama_worker = OllamaModelsWorker(self.url_input.text().strip(), self)
        self._ollama_worker.models_ready.connect(self._on_ollama_models_ready)
        self._ollama_worker.error_occurred.connect(self._on_ollama_error)
        self._ollama_worker.start()

    def _on_ollama_models_ready(self, models: list[str]):
        self.btn_detect_ollama.setEnabled(True)
        self.btn_detect_ollama.setText("Detectar modelos")
        menu = QMenu(self)
        for name in models:
            act = menu.addAction(name)
            act.triggered.connect(lambda checked=False, m=name: self.model_input.setText(m))
        pos = self.btn_detect_ollama.mapToGlobal(self.btn_detect_ollama.rect().bottomLeft())
        menu.exec(pos)

    def _on_ollama_error(self, msg: str):
        self.btn_detect_ollama.setEnabled(True)
        self.btn_detect_ollama.setText("Detectar modelos")
        self.error_banner.setText(f"⚠ {msg}")
        self.error_banner.show()

    def _test_connection(self):
        if self._test_worker is not None and self._test_worker.isRunning():
            return
        self._clear_banners()
        provider = self.provider_combo.currentText()
        model = self.model_input.text().strip()
        url = self.url_input.text().strip()
        api_key = self.key_input.text().strip()
        env_var = PROVIDERS.get(provider, {}).get("env_var", "")
        if not api_key and env_var:
            api_key = os.environ.get(env_var, "").strip()
        is_local = provider == "Ollama (Local)" or "localhost" in url or "127.0.0.1" in url

        if not model or not url.startswith(("http://", "https://")):
            self.error_banner.setText("⚠ Completa primero un modelo y una URL válidos.")
            self.error_banner.show()
            return
        if PROVIDERS.get(provider, {}).get("needs_key", False) and not api_key:
            self.error_banner.setText(f"⚠ Falta la API Key para {provider}.")
            self.error_banner.show()
            return

        self.btn_test.setEnabled(False)
        self.btn_test.setText("Probando...")
        self._test_worker = AITestConnectionWorker(url, model, api_key, is_local, self)
        self._test_worker.succeeded.connect(self._on_test_ok)
        self._test_worker.failed.connect(self._on_test_fail)
        self._test_worker.start()

    def _on_test_ok(self, msg: str):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Probar conexión")
        self.success_banner.setText(msg)
        self.success_banner.show()

    def _on_test_fail(self, msg: str):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Probar conexión")
        self.error_banner.setText(f"⚠ {msg}")
        self.error_banner.show()

    def save_and_accept(self):
        provider = self.provider_combo.currentText()
        model = self.model_input.text().strip()
        url = self.url_input.text().strip()
        api_key = self.key_input.text().strip()
        env_var = PROVIDERS.get(provider, {}).get("env_var", "")
        effective_key = api_key or (os.environ.get(env_var, "").strip() if env_var else "")
        temp_val = TEMPERATURE_PRESETS[self.temp_combo.currentIndex()][1]

        if not model:
            self.error_banner.setText("⚠ Indica el nombre del modelo antes de guardar.")
            self.error_banner.show()
            self.model_input.setFocus()
            return
        if not url.startswith(("http://", "https://")):
            self.error_banner.setText("⚠ El Endpoint URL debe comenzar por http:// o https://.")
            self.error_banner.show()
            self.url_input.setFocus()
            return
        if PROVIDERS.get(provider, {}).get("needs_key", False) and not effective_key:
            self.error_banner.setText(
                f"⚠ {provider} requiere una API Key. Si prefieres trabajar sin clave, selecciona Ollama (Local)."
            )
            self.error_banner.show()
            self.key_input.setFocus()
            return

        self.settings.setValue("ai/provider", provider)
        self.settings.setValue("ai/model", model)
        self.settings.setValue("ai/url", url)
        self.settings.setValue("ai/api_key", api_key)
        self.settings.setValue("ai/temperature", temp_val)
        self.accept()
