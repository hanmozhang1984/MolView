from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QDialogButtonBox, QProgressBar, QGroupBox, QMessageBox,
    QDoubleSpinBox,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema
from molview.chem.property_calculator import (
    PROPERTY_REGISTRY, calculate_properties, set_logd_ph, get_logd_ph,
)


class CalcWorker(QThread):
    progress = Signal(int)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, smiles_series, property_names):
        super().__init__()
        self._smiles = smiles_series
        self._props = property_names

    def run(self):
        try:
            results = calculate_properties(
                self._smiles, self._props, self.progress.emit
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PropertyCalcDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculate Molecular Properties")
        self.setMinimumWidth(400)
        self._dataset = dataset
        self._worker = None

        layout = QVBoxLayout(self)

        # Source column selector
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

        # Auto-select SMILES-typed column if one exists
        for i in range(self._col_combo.count()):
            name = self._col_combo.itemText(i)
            schema = dataset.get_schema(name)
            if schema.col_type == ColumnType.SMILES:
                self._col_combo.setCurrentIndex(i)
                break

        # Property checkboxes
        group = QGroupBox("Properties")
        group_layout = QVBoxLayout()
        self._checkboxes = {}
        for key, (label, _) in PROPERTY_REGISTRY.items():
            if key == "LogD":
                # LogD with pH spinner on same row
                logd_row = QHBoxLayout()
                cb = QCheckBox(f"{label} ({key})")
                cb.setChecked(True)
                self._checkboxes[key] = cb
                logd_row.addWidget(cb)
                logd_row.addWidget(QLabel("pH:"))
                self._ph_spin = QDoubleSpinBox()
                self._ph_spin.setRange(0.0, 14.0)
                self._ph_spin.setSingleStep(0.1)
                self._ph_spin.setDecimals(1)
                self._ph_spin.setValue(get_logd_ph())
                self._ph_spin.setFixedWidth(70)
                logd_row.addWidget(self._ph_spin)
                logd_row.addStretch()
                group_layout.addLayout(logd_row)
            else:
                cb = QCheckBox(f"{label} ({key})")
                cb.setChecked(True)
                self._checkboxes[key] = cb
                group_layout.addWidget(cb)
        group.setLayout(group_layout)
        layout.addWidget(group)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._run_calculation)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _run_calculation(self):
        col_name = self._col_combo.currentText()
        if not col_name:
            return

        selected = [k for k, cb in self._checkboxes.items() if cb.isChecked()]
        if not selected:
            return

        # Set LogD pH before calculation
        if "LogD" in selected:
            set_logd_ph(self._ph_spin.value())

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._buttons.setEnabled(False)

        smiles_series = self._dataset.df[col_name]
        self._worker = CalcWorker(smiles_series, selected)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, results: dict):
        for prop_name, values in results.items():
            display_name, _ = PROPERTY_REGISTRY[prop_name]
            # Append pH to LogD column name
            if prop_name == "LogD":
                display_name = f"LogD (pH {self._ph_spin.value():.1f})"
            col_type = ColumnType.NUMERIC if prop_name != "MF" else ColumnType.TEXT
            if display_name not in self._dataset.df.columns:
                self._dataset.df[display_name] = values
                self._dataset.schemas[display_name] = ColumnSchema(
                    display_name, col_type
                )
            else:
                self._dataset.df[display_name] = values

        self._dataset.columns_changed.emit()
        self._dataset.modified = True
        self.accept()

    def _on_error(self, msg: str):
        self._buttons.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Calculation Error", msg)
