from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QDialogButtonBox,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema


class ColumnFormatDialog(QDialog):
    def __init__(self, dataset: DataSet, col_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Format Column: {col_name}")
        self._dataset = dataset
        self._col_name = col_name

        schema = dataset.get_schema(col_name)

        layout = QVBoxLayout(self)

        # Type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        for ct in ColumnType:
            if ct != ColumnType.MOL_BLOCK:
                self._type_combo.addItem(ct.name, ct)
        idx = self._type_combo.findData(schema.col_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        type_layout.addWidget(self._type_combo)
        layout.addLayout(type_layout)

        # Decimal places
        dec_layout = QHBoxLayout()
        dec_layout.addWidget(QLabel("Decimal Places:"))
        self._decimals_spin = QSpinBox()
        self._decimals_spin.setRange(0, 10)
        self._decimals_spin.setValue(schema.decimal_places)
        dec_layout.addWidget(self._decimals_spin)
        layout.addLayout(dec_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self):
        col_type = self._type_combo.currentData()
        decimals = self._decimals_spin.value()
        schema = ColumnSchema(self._col_name, col_type, decimals)
        self._dataset.set_schema(self._col_name, schema)
        self.accept()
