"""Dialog for PubChem compound lookup."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDialogButtonBox, QProgressBar, QGroupBox, QMessageBox,
    QRadioButton, QButtonGroup, QLineEdit, QCheckBox, QPushButton,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema
from molview.chem.external_lookup import batch_lookup_by_smiles, lookup_by_name, lookup_by_cid


class SingleLookupWorker(QThread):
    finished = Signal(object)  # dict or None
    error = Signal(str)

    def __init__(self, query, lookup_type):
        super().__init__()
        self._query = query
        self._type = lookup_type

    def run(self):
        try:
            if self._type == "name":
                result = lookup_by_name(self._query)
            elif self._type == "cid":
                result = lookup_by_cid(int(self._query))
            else:
                from molview.chem.external_lookup import lookup_by_smiles
                result = lookup_by_smiles(self._query)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BatchLookupWorker(QThread):
    progress = Signal(int)
    finished = Signal(list)  # list of dicts
    error = Signal(str)

    def __init__(self, smiles_list):
        super().__init__()
        self._smiles = smiles_list

    def run(self):
        try:
            results = batch_lookup_by_smiles(self._smiles, progress_callback=self.progress.emit)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class LookupDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PubChem Lookup")
        self.setMinimumWidth(550)
        self._dataset = dataset
        self._worker = None

        layout = QVBoxLayout(self)

        # Mode selection
        mode_group = QGroupBox("Lookup Mode")
        mode_layout = QVBoxLayout()

        self._single_radio = QRadioButton("Single compound lookup")
        self._single_radio.setChecked(True)
        self._batch_radio = QRadioButton("Batch lookup (all rows in a SMILES column)")
        mode_btn_group = QButtonGroup(self)
        mode_btn_group.addButton(self._single_radio)
        mode_btn_group.addButton(self._batch_radio)
        mode_layout.addWidget(self._single_radio)
        mode_layout.addWidget(self._batch_radio)
        self._single_radio.toggled.connect(self._update_ui_mode)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Single lookup controls
        self._single_group = QGroupBox("Single Lookup")
        single_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Search by:"))
        self._search_type_combo = QComboBox()
        self._search_type_combo.addItems(["SMILES", "Name", "CID"])
        type_row.addWidget(self._search_type_combo)
        single_layout.addLayout(type_row)

        query_row = QHBoxLayout()
        query_row.addWidget(QLabel("Query:"))
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Enter SMILES, compound name, or CID...")
        query_row.addWidget(self._query_input)
        single_layout.addLayout(query_row)

        self._single_group.setLayout(single_layout)
        layout.addWidget(self._single_group)

        # Batch lookup controls
        self._batch_group = QGroupBox("Batch Lookup")
        batch_layout = QVBoxLayout()
        col_row = QHBoxLayout()
        col_row.addWidget(QLabel("SMILES Column:"))
        self._col_combo = QComboBox()
        for i in range(dataset.column_count):
            col_name = dataset.column_name(i)
            schema = dataset.get_schema(col_name)
            if schema.col_type in (ColumnType.SMILES, ColumnType.TEXT):
                self._col_combo.addItem(col_name)
        col_row.addWidget(self._col_combo)
        batch_layout.addLayout(col_row)

        # Auto-select SMILES column
        for i in range(self._col_combo.count()):
            name = self._col_combo.itemText(i)
            if dataset.get_schema(name).col_type == ColumnType.SMILES:
                self._col_combo.setCurrentIndex(i)
                break

        batch_layout.addWidget(QLabel(
            "Note: Batch lookup queries PubChem for each row. "
            "This may take a while for large datasets."
        ))

        self._batch_group.setLayout(batch_layout)
        self._batch_group.setVisible(False)
        layout.addWidget(self._batch_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Lookup")
        self._buttons.accepted.connect(self._run)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _update_ui_mode(self, single_checked):
        self._single_group.setVisible(single_checked)
        self._batch_group.setVisible(not single_checked)

    def _run(self):
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._buttons.setEnabled(False)

        if self._single_radio.isChecked():
            self._run_single()
        else:
            self._run_batch()

    def _run_single(self):
        query = self._query_input.text().strip()
        if not query:
            self._buttons.setEnabled(True)
            self._progress.setVisible(False)
            return

        search_type = self._search_type_combo.currentText().lower()
        self._worker = SingleLookupWorker(query, search_type)
        self._worker.finished.connect(self._on_single_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_single_done(self, result):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)

        if result is None:
            QMessageBox.information(self, "PubChem Lookup", "No compound found.")
            return

        # Show results in a message box
        lines = []
        for key, val in result.items():
            lines.append(f"{key}: {val}")
        QMessageBox.information(
            self, "PubChem Result",
            "\n".join(lines)
        )

    def _run_batch(self):
        col_name = self._col_combo.currentText()
        if not col_name:
            self._buttons.setEnabled(True)
            self._progress.setVisible(False)
            return

        smiles_list = self._dataset.df[col_name].tolist()
        self._worker = BatchLookupWorker(smiles_list)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_batch_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_batch_done(self, results: list):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)

        if not results:
            QMessageBox.information(self, "PubChem Lookup", "No results returned.")
            return

        # Collect all property keys from results
        all_keys = set()
        for r in results:
            if r:
                all_keys.update(r.keys())

        if not all_keys:
            QMessageBox.information(self, "PubChem Lookup", "No properties found for any compound.")
            return

        # Add columns for each property
        added = 0
        for key in sorted(all_keys):
            col_name = f"PubChem_{key}"
            values = []
            for r in results:
                if r and key in r:
                    values.append(r[key])
                else:
                    values.append(None)

            self._dataset.df[col_name] = values
            # Determine type
            col_type = ColumnType.NUMERIC
            for v in values:
                if v is not None:
                    try:
                        float(v)
                    except (ValueError, TypeError):
                        col_type = ColumnType.TEXT
                        break
            self._dataset.schemas[col_name] = ColumnSchema(col_name, col_type)
            added += 1

        self._dataset.columns_changed.emit()
        self._dataset.modified = True
        self.accept()

        parent = self.parent()
        found = sum(1 for r in results if r is not None)
        if parent and hasattr(parent, 'statusBar'):
            parent.statusBar().showMessage(
                f"PubChem lookup: {found}/{len(results)} compounds found, {added} columns added",
                8000
            )

    def _on_error(self, msg: str):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Lookup Error", msg)
