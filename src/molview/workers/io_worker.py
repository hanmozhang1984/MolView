"""Background file I/O workers — used for large files."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class FileLoadWorker(QThread):
    """Load a file in a background thread with progress reporting."""
    progress = Signal(int)
    finished = Signal(object, object)  # (DataFrame, schemas)
    error = Signal(str)

    def __init__(self, path: str, loader_func):
        super().__init__()
        self._path = path
        self._loader = loader_func

    def run(self):
        try:
            df, schemas = self._loader(self._path, progress_callback=self.progress.emit)
            self.finished.emit(df, schemas)
        except Exception as e:
            self.error.emit(str(e))
