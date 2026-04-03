"""Dialog for R-group decomposition."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDialogButtonBox, QProgressBar, QLineEdit, QGroupBox,
    QMessageBox, QPushButton,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema
from molview.chem.rgroup import rgroup_decompose


class RGroupWorker(QThread):
    progress = Signal(int)
    finished = Signal(object)  # DataFrame or None
    error = Signal(str)

    def __init__(self, smiles_series, core_smiles):
        super().__init__()
        self._smiles = smiles_series
        self._core = core_smiles

    def run(self):
        try:
            result = rgroup_decompose(self._smiles, self._core, self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class RGroupDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("R-Group Decomposition")
        self.setMinimumWidth(500)
        self._dataset = dataset
        self._worker = None

        layout = QVBoxLayout(self)

        # Source column
        src_layout = QHBoxLayout()
        src_layout.addWidget(QLabel("SMILES Column:"))
        self._col_combo = QComboBox()
        for i in range(dataset.column_count):
            col_name = dataset.column_name(i)
            schema = dataset.get_schema(col_name)
            if schema.col_type in (ColumnType.SMILES, ColumnType.TEXT):
                self._col_combo.addItem(col_name)
        src_layout.addWidget(self._col_combo)
        layout.addLayout(src_layout)

        # Auto-select SMILES column
        for i in range(self._col_combo.count()):
            name = self._col_combo.itemText(i)
            if dataset.get_schema(name).col_type == ColumnType.SMILES:
                self._col_combo.setCurrentIndex(i)
                break

        # Core input
        core_group = QGroupBox("Core / Scaffold")
        core_layout = QVBoxLayout()

        smiles_row = QHBoxLayout()
        smiles_row.addWidget(QLabel("Core SMILES:"))
        self._core_input = QLineEdit()
        self._core_input.setPlaceholderText("Enter core SMILES (e.g. c1cnc2ncccc2c1 for naphthyridine)...")
        smiles_row.addWidget(self._core_input)
        core_layout.addLayout(smiles_row)

        core_layout.addWidget(QLabel(
            "Tip: Type the scaffold SMILES directly for best results. "
            "Ketcher-drawn R-groups may create non-aromatic forms that don't match your data."
        ))

        draw_btn = QPushButton("Draw Core...")
        draw_btn.clicked.connect(self._open_structure_editor)
        core_layout.addWidget(draw_btn)

        core_group.setLayout(core_layout)
        layout.addWidget(core_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._run)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _open_structure_editor(self):
        try:
            from molview.gui.structure_editor.editor_dialog import StructureEditorDialog
        except ImportError:
            QMessageBox.information(self, "Info", "Structure editor not available.")
            return

        preloaded = None
        main_win = self.parent()
        if main_win and hasattr(main_win, '_take_preloaded_ketcher'):
            preloaded = main_win._take_preloaded_ketcher()

        self._editor_dlg = StructureEditorDialog(self, preloaded_view=preloaded)
        self._editor_dlg.finished.connect(self._on_editor_finished)
        self._editor_dlg.open()

    def _on_editor_finished(self, result: int):
        dlg = self._editor_dlg
        self._editor_dlg = None
        if dlg and result == QDialog.DialogCode.Accepted:
            smiles = dlg.get_smiles()
            if smiles:
                self._core_input.setText(smiles)
        if dlg:
            dlg.deleteLater()

    def _run(self):
        core = self._core_input.text().strip()
        col_name = self._col_combo.currentText()
        if not core or not col_name:
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._buttons.setEnabled(False)

        self._worker = RGroupWorker(self._dataset.df[col_name], core)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, result):
        if result is None or result.empty:
            self._buttons.setEnabled(True)
            self._progress.setVisible(False)
            QMessageBox.warning(
                self, "No Results",
                "No molecules matched the core scaffold. "
                "Try a different core or check your SMILES/SMARTS."
            )
            return

        # Add R-group columns to dataset
        for col_name in result.columns:
            display_name = col_name
            self._dataset.df[display_name] = result[col_name]
            col_type = ColumnType.SMILES if col_name.startswith("R") else ColumnType.TEXT
            self._dataset.schemas[display_name] = ColumnSchema(display_name, col_type)

        self._dataset.columns_changed.emit()
        self._dataset.modified = True
        self.accept()

        parent = self.parent()
        n_rgroups = len([c for c in result.columns if c.startswith("R")])
        if parent and hasattr(parent, 'statusBar'):
            parent.statusBar().showMessage(
                f"R-group decomposition complete: {n_rgroups} R-group(s) found", 8000
            )

    def _on_error(self, msg: str):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "R-Group Error", msg)
