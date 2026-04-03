"""Dialog for creating custom calculated columns via Python expressions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QDialogButtonBox, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema


# Safe namespace for expression evaluation
_SAFE_BUILTINS = {
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'len': len, 'sum': sum, 'int': int, 'float': float, 'str': str,
    'True': True, 'False': False, 'None': None,
}


class CustomColumnDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Calculated Column")
        self.setMinimumSize(550, 400)
        self._dataset = dataset

        layout = QVBoxLayout(self)

        # Column name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Column Name:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Efficiency_Index")
        name_layout.addWidget(self._name_input)
        layout.addLayout(name_layout)

        # Expression
        expr_group = QGroupBox("Expression")
        expr_layout = QVBoxLayout()
        expr_layout.addWidget(QLabel(
            "Use column names as variables. Available: df['ColName'], np.log(), np.sqrt(), etc."
        ))
        self._expr_input = QTextEdit()
        self._expr_input.setPlaceholderText(
            "Examples:\n"
            "  df['Molecular Weight'] / df['TPSA']\n"
            "  np.log10(df['Crippen LogP'] + 1)\n"
            "  df['HBD'] + df['HBA']\n"
            "  df['Crippen LogP'].clip(-5, 5)"
        )
        self._expr_input.setMaximumHeight(100)
        expr_layout.addWidget(self._expr_input)
        expr_group.setLayout(expr_layout)
        layout.addWidget(expr_group)

        # Available columns reference
        cols_group = QGroupBox("Available Columns")
        cols_layout = QVBoxLayout()
        cols_text = ", ".join(
            f"'{dataset.column_name(i)}'"
            for i in range(dataset.column_count)
        )
        cols_label = QLabel(cols_text)
        cols_label.setWordWrap(True)
        cols_label.setStyleSheet("font-size: 11px; color: #555;")
        cols_layout.addWidget(cols_label)
        cols_group.setLayout(cols_layout)
        layout.addWidget(cols_group)

        # Preview
        preview_btn = QLabel("Preview (first 5 rows):")
        layout.addWidget(preview_btn)
        self._preview_table = QTableWidget(5, 2)
        self._preview_table.setHorizontalHeaderLabels(["Row", "Value"])
        self._preview_table.setMaximumHeight(150)
        self._preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._preview_table)

        preview_action = self._expr_input.textChanged
        # Debounce: preview on focus-out or button click
        from PySide6.QtWidgets import QPushButton
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._update_preview)
        layout.addWidget(preview_btn)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._apply)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _evaluate_expression(self, expr: str):
        """Evaluate expression in a restricted namespace. Returns a Series."""
        namespace = {
            '__builtins__': _SAFE_BUILTINS,
            'df': self._dataset.df,
            'np': np,
            'pd': pd,
        }
        result = eval(expr, namespace)
        if isinstance(result, pd.Series):
            return result
        elif isinstance(result, (np.ndarray, list)):
            return pd.Series(result, index=self._dataset.df.index)
        else:
            # Scalar — broadcast
            return pd.Series(result, index=self._dataset.df.index)

    def _update_preview(self):
        expr = self._expr_input.toPlainText().strip()
        if not expr:
            return

        self._preview_table.clearContents()
        try:
            result = self._evaluate_expression(expr)
            for i in range(min(5, len(result))):
                self._preview_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                val = result.iloc[i]
                self._preview_table.setItem(i, 1, QTableWidgetItem(str(val)))
        except Exception as e:
            self._preview_table.setItem(0, 0, QTableWidgetItem("Error"))
            self._preview_table.setItem(0, 1, QTableWidgetItem(str(e)))

    def _apply(self):
        name = self._name_input.text().strip()
        expr = self._expr_input.toPlainText().strip()

        if not name:
            QMessageBox.warning(self, "Error", "Please enter a column name.")
            return
        if not expr:
            QMessageBox.warning(self, "Error", "Please enter an expression.")
            return
        if name in self._dataset.df.columns:
            QMessageBox.warning(self, "Error", f"Column '{name}' already exists.")
            return

        try:
            result = self._evaluate_expression(expr)
        except Exception as e:
            QMessageBox.critical(self, "Expression Error", str(e))
            return

        # Determine column type
        col_type = ColumnType.NUMERIC
        try:
            result.astype(float)
        except (ValueError, TypeError):
            col_type = ColumnType.TEXT

        self._dataset.df[name] = result
        self._dataset.schemas[name] = ColumnSchema(name, col_type)
        self._dataset.columns_changed.emit()
        self._dataset.modified = True
        self.accept()
