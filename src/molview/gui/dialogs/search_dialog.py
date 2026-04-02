from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QRadioButton, QButtonGroup, QDoubleSpinBox, QDialogButtonBox,
    QProgressBar, QLineEdit, QGroupBox, QMessageBox, QPushButton,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema
from molview.chem.search import substructure_search, similarity_search


class SearchWorker(QThread):
    progress = Signal(int)
    finished_sub = Signal(list)  # bool list
    finished_sim = Signal(list)  # float list
    error = Signal(str)

    def __init__(self, smiles_series, query, search_type, threshold=0.7):
        super().__init__()
        self._smiles = smiles_series
        self._query = query
        self._type = search_type
        self._threshold = threshold

    def run(self):
        try:
            if self._type == "substructure":
                result = substructure_search(self._smiles, self._query, self.progress.emit)
                self.finished_sub.emit(result)
            else:
                result = similarity_search(
                    self._smiles, self._query, self._threshold, self.progress.emit
                )
                self.finished_sim.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SearchDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Structure Search")
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

        # Auto-select SMILES-typed column
        for i in range(self._col_combo.count()):
            name = self._col_combo.itemText(i)
            schema = dataset.get_schema(name)
            if schema.col_type == ColumnType.SMILES:
                self._col_combo.setCurrentIndex(i)
                break

        # Query input
        query_group = QGroupBox("Query")
        query_layout = QVBoxLayout()

        smiles_layout = QHBoxLayout()
        smiles_layout.addWidget(QLabel("SMILES/SMARTS:"))
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Enter SMILES or SMARTS pattern...")
        smiles_layout.addWidget(self._query_input)
        query_layout.addLayout(smiles_layout)

        # Draw button (will open JSME in Phase 3)
        self._draw_btn = QPushButton("Draw Structure...")
        self._draw_btn.clicked.connect(self._open_structure_editor)
        query_layout.addWidget(self._draw_btn)

        query_group.setLayout(query_layout)
        layout.addWidget(query_group)

        # Search type
        type_layout = QHBoxLayout()
        self._sub_radio = QRadioButton("Substructure")
        self._sub_radio.setChecked(True)
        self._sim_radio = QRadioButton("Similarity")
        type_group = QButtonGroup(self)
        type_group.addButton(self._sub_radio)
        type_group.addButton(self._sim_radio)
        type_layout.addWidget(self._sub_radio)
        type_layout.addWidget(self._sim_radio)

        type_layout.addWidget(QLabel("Threshold:"))
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.0, 1.0)
        self._threshold_spin.setValue(0.7)
        self._threshold_spin.setSingleStep(0.05)
        type_layout.addWidget(self._threshold_spin)
        layout.addLayout(type_layout)

        # Action: filter or highlight
        action_layout = QHBoxLayout()
        self._filter_radio = QRadioButton("Filter (hide non-matching)")
        self._filter_radio.setChecked(True)
        self._highlight_radio = QRadioButton("Highlight matches")
        action_group = QButtonGroup(self)
        action_group.addButton(self._filter_radio)
        action_group.addButton(self._highlight_radio)
        action_layout.addWidget(self._filter_radio)
        action_layout.addWidget(self._highlight_radio)
        layout.addLayout(action_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._run_search)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _open_structure_editor(self):
        try:
            from molview.gui.structure_editor.editor_dialog import StructureEditorDialog
        except ImportError:
            QMessageBox.information(
                self, "Info", "Structure editor not yet available. Enter SMILES/SMARTS manually."
            )
            return

        # Try to get a pre-loaded Ketcher view from the main window
        preloaded = None
        main_win = self.parent()
        if main_win and hasattr(main_win, '_take_preloaded_ketcher'):
            preloaded = main_win._take_preloaded_ketcher()

        # Use open() instead of exec() — QWebEngineView deadlocks in nested event loops
        self._editor_dlg = StructureEditorDialog(self, preloaded_view=preloaded)
        self._editor_dlg.finished.connect(self._on_editor_finished)
        self._editor_dlg.open()

    def _on_editor_finished(self, result: int):
        dlg = self._editor_dlg
        self._editor_dlg = None
        if dlg and result == QDialog.DialogCode.Accepted:
            smiles = dlg.get_smiles()
            if smiles:
                self._query_input.setText(smiles)
        if dlg:
            dlg.deleteLater()

    def _run_search(self):
        query = self._query_input.text().strip()
        col_name = self._col_combo.currentText()
        if not query or not col_name:
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._buttons.setEnabled(False)

        search_type = "substructure" if self._sub_radio.isChecked() else "similarity"
        smiles_series = self._dataset.df[col_name]

        self._worker = SearchWorker(
            smiles_series, query, search_type, self._threshold_spin.value()
        )
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished_sub.connect(self._on_substructure_done)
        self._worker.finished_sim.connect(self._on_similarity_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_substructure_done(self, mask: list[bool]):
        matching = {i for i, v in enumerate(mask) if v}
        non_matching = {i for i, v in enumerate(mask) if not v}

        if self._filter_radio.isChecked():
            self._dataset.show_all_rows()
            self._dataset.hide_rows(non_matching)
        else:
            self._dataset.select_rows(matching)
            self._dataset.data_changed.emit()

        self.accept()
        self._show_result_count(len(matching))

    def _on_similarity_done(self, scores: list[float]):
        matching = {i for i, s in enumerate(scores) if s > 0}
        non_matching = {i for i, s in enumerate(scores) if s == 0}

        # Add similarity score column
        col_name = "Similarity"
        self._dataset.df[col_name] = scores
        self._dataset.schemas[col_name] = ColumnSchema(
            col_name, ColumnType.NUMERIC, decimal_places=4
        )

        if self._filter_radio.isChecked():
            self._dataset.show_all_rows()
            self._dataset.hide_rows(non_matching)
        else:
            self._dataset.select_rows(matching)

        self._dataset.columns_changed.emit()
        self._dataset.modified = True
        self.accept()
        self._show_result_count(len(matching))

    def _show_result_count(self, count: int):
        total = self._dataset.row_count
        msg = f"Search complete: {count}/{total} matching molecules"
        # Show in parent's status bar if available, otherwise message box
        parent = self.parent()
        if parent and hasattr(parent, 'statusBar'):
            parent.statusBar().showMessage(msg, 8000)
        else:
            QMessageBox.information(self, "Search Results", msg)

    def _on_error(self, msg: str):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Search Error", msg)
