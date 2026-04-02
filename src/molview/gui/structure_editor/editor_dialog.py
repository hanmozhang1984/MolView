from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QDialogButtonBox,
    QLabel, QLineEdit, QStackedWidget, QProgressBar, QWidget,
)
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


# Path to the local Ketcher build
_KETCHER_DIR = Path(__file__).parent / "ketcher"
_KETCHER_INDEX = _KETCHER_DIR / "index.html"


def create_ketcher_webview(parent=None) -> QWebEngineView:
    """Create and configure a QWebEngineView that loads Ketcher.

    Can be used to pre-load Ketcher in the background at app startup.
    """
    view = QWebEngineView(parent)
    settings = view.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    view.setUrl(QUrl.fromLocalFile(str(_KETCHER_INDEX)))
    return view


class StructureEditorDialog(QDialog):
    """Dialog with embedded Ketcher molecule editor.

    IMPORTANT: Do NOT use exec() with this dialog — QWebEngineView deadlocks
    in nested event loops. Use open() + finished signal instead.
    """

    def __init__(self, parent=None, initial_smiles: str = "",
                 preloaded_view: QWebEngineView | None = None):
        super().__init__(parent)
        self.setWindowTitle("Draw Structure")
        self.setMinimumSize(900, 650)
        self.setModal(True)
        self._smiles = ""
        self._initial_smiles = initial_smiles
        self._request_id = ""
        self._poll_timer = None
        self._closing = False
        self._ketcher_ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Stacked widget: loading overlay (index 0) and web view (index 1)
        self._stack = QStackedWidget()
        self._stack.setMinimumSize(880, 530)

        # Loading overlay
        loading_widget = QWidget()
        loading_layout = QVBoxLayout(loading_widget)
        loading_layout.addStretch()
        self._loading_label = QLabel("Loading structure editor...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet("font-size: 16px; color: #555;")
        loading_layout.addWidget(self._loading_label)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)  # indeterminate
        self._loading_bar.setFixedWidth(300)
        self._loading_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_container = QHBoxLayout()
        bar_container.addStretch()
        bar_container.addWidget(self._loading_bar)
        bar_container.addStretch()
        loading_layout.addLayout(bar_container)
        loading_layout.addStretch()
        self._stack.addWidget(loading_widget)  # index 0

        # Web view for Ketcher — reuse pre-loaded or create new
        if preloaded_view is not None:
            self._web_view = preloaded_view
            self._web_view.setParent(self)
        else:
            self._web_view = create_ketcher_webview(self)

        self._web_view.setMinimumSize(880, 530)
        self._stack.addWidget(self._web_view)  # index 1
        self._stack.setCurrentIndex(0)  # show loading initially

        layout.addWidget(self._stack)

        # SMILES display row
        smiles_layout = QHBoxLayout()
        smiles_layout.addWidget(QLabel("SMILES:"))
        self._smiles_display = QLineEdit()
        self._smiles_display.setPlaceholderText(
            "Draw a structure, then click Get SMILES (or type SMILES directly)"
        )
        smiles_layout.addWidget(self._smiles_display)

        get_btn = QPushButton("Get SMILES")
        get_btn.clicked.connect(self._fetch_smiles)
        smiles_layout.addWidget(get_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        smiles_layout.addWidget(clear_btn)

        layout.addLayout(smiles_layout)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self._on_reject)
        layout.addWidget(buttons)

        # Start polling for Ketcher readiness
        self._ready_timer = QTimer(self)
        self._ready_poll_count = 0
        self._ready_timer.timeout.connect(self._poll_ready)
        self._ready_timer.start(150)

    def _poll_ready(self):
        """Poll until Ketcher's isReady() returns true, then show the editor."""
        self._ready_poll_count += 1
        if self._ready_poll_count > 100:  # ~15 seconds timeout
            self._ready_timer.stop()
            # Show web view anyway even if not fully ready
            self._show_editor()
            return
        if self._web_view:
            self._web_view.page().runJavaScript("typeof isReady === 'function' && isReady()", self._on_ready_poll)

    def _on_ready_poll(self, ready):
        if ready:
            self._ready_timer.stop()
            self._show_editor()

    def _show_editor(self):
        """Switch from loading overlay to Ketcher web view."""
        self._ketcher_ready = True
        self._stack.setCurrentIndex(1)
        # Inject initial SMILES if provided
        if self._initial_smiles and self._web_view:
            escaped = self._initial_smiles.replace("\\", "\\\\").replace("'", "\\'")
            self._web_view.page().runJavaScript(f"injectMolecule('{escaped}')")

    def _kick_fetch(self, callback):
        """Start async SMILES fetch with unique request ID, then poll."""
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()

        req_id = uuid.uuid4().hex[:8]
        self._request_id = req_id
        self._result_callback = callback
        self._poll_count = 0

        if not self._web_view:
            callback("")
            return

        self._web_view.page().runJavaScript(
            f"window._reqId = '{req_id}'; window._reqDone = false; "
            "window.ketcher.getSmiles().then(function(s) {"
            "  window._reqResult = s || '';"
            "  window._reqDone = true;"
            "}).catch(function() {"
            "  window._reqResult = '';"
            "  window._reqDone = true;"
            "})"
        )

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._do_poll)
        self._poll_timer.start(200)

    def _do_poll(self):
        self._poll_count += 1
        if self._poll_count > 25 or not self._web_view:
            self._poll_timer.stop()
            self._result_callback("")
            return
        req_id = self._request_id
        self._web_view.page().runJavaScript(
            f"(window._reqDone && window._reqId === '{req_id}') ? window._reqResult : null",
            self._check_poll,
        )

    def _check_poll(self, val):
        if val is not None and self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
            self._result_callback(str(val))

    def _fetch_smiles(self):
        self._kick_fetch(self._on_smiles_fetched)

    def _on_smiles_fetched(self, smiles: str):
        self._smiles = smiles
        self._smiles_display.setText(smiles)

    def _clear(self):
        if self._web_view:
            self._web_view.page().runJavaScript(
                "window.ketcher.setMolecule('').catch(function(){})"
            )
        self._smiles = ""
        self._smiles_display.clear()

    def _destroy_webview(self):
        """Remove and destroy the web view to release Chromium resources."""
        if self._ready_timer.isActive():
            self._ready_timer.stop()
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
        if self._web_view:
            self._web_view.setParent(None)  # detach from layout
            self._web_view.deleteLater()     # schedule destruction
            self._web_view = None

    def _on_accept(self):
        if self._closing:
            return
        self._closing = True

        # Capture SMILES from text field or stored value
        text = self._smiles_display.text().strip()
        if text:
            self._smiles = text
        # Destroy web view first, then close dialog on next event loop tick
        self._destroy_webview()
        QTimer.singleShot(100, self.accept)

    def _on_reject(self):
        if self._closing:
            return
        self._closing = True
        self._destroy_webview()
        QTimer.singleShot(100, self.reject)

    def get_smiles(self) -> str:
        return self._smiles
