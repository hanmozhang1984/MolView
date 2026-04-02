from __future__ import annotations

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QSpinBox, QColorDialog, QLineEdit,
)
from PySide6.QtGui import QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType


class BarChartWidget(QWidget):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self._dataset = dataset
        self._bar_color = "#4a90d9"

        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Column:"))
        self._col_combo = QComboBox()
        controls.addWidget(self._col_combo)

        controls.addWidget(QLabel("Bins:"))
        self._bins_spin = QSpinBox()
        self._bins_spin.setRange(2, 200)
        self._bins_spin.setValue(20)
        controls.addWidget(self._bins_spin)

        controls.addWidget(QLabel("Custom bins:"))
        self._custom_bins = QLineEdit()
        self._custom_bins.setPlaceholderText("e.g. 0,100,200,300,500")
        self._custom_bins.setMaximumWidth(200)
        controls.addWidget(self._custom_bins)

        color_btn = QPushButton("Color")
        color_btn.clicked.connect(self._pick_color)
        controls.addWidget(color_btn)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self._do_plot)
        controls.addWidget(plot_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Canvas
        self._figure = Figure(figsize=(8, 5), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

        self.refresh_columns()

    def refresh_columns(self):
        # Build new column list
        numeric_cols = []
        for i in range(self._dataset.column_count):
            col_name = self._dataset.column_name(i)
            schema = self._dataset.get_schema(col_name)
            if schema.col_type == ColumnType.NUMERIC:
                numeric_cols.append(col_name)

        # Skip rebuild if columns haven't changed
        existing = [self._col_combo.itemText(i) for i in range(self._col_combo.count())]
        if existing == numeric_cols:
            return

        current = self._col_combo.currentText()
        self._col_combo.blockSignals(True)
        self._col_combo.clear()
        for name in numeric_cols:
            self._col_combo.addItem(name)
        if current:
            idx = self._col_combo.findText(current)
            if idx >= 0:
                self._col_combo.setCurrentIndex(idx)
        self._col_combo.blockSignals(False)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._bar_color), self, "Bar Color")
        if color.isValid():
            self._bar_color = color.name()

    def _do_plot(self):
        col = self._col_combo.currentText()
        if not col:
            return

        self._figure.clear()
        ax = self._figure.add_subplot(111)

        df = self._dataset.df
        hidden = self._dataset.hidden_rows
        visible_mask = ~df.index.isin(hidden)
        data = df.loc[visible_mask, col].astype(float).dropna()

        if len(data) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes)
            self._canvas.draw()
            return

        # Determine bins
        custom = self._custom_bins.text().strip()
        if custom:
            try:
                bins = [float(x.strip()) for x in custom.split(",")]
            except ValueError:
                bins = self._bins_spin.value()
        else:
            bins = self._bins_spin.value()

        counts, edges, patches = ax.hist(
            data, bins=bins, color=self._bar_color, edgecolor="white",
            alpha=0.85
        )

        ax.set_xlabel(col)
        ax.set_ylabel("Count")
        ax.set_title(f"Distribution of {col}")
        ax.grid(True, alpha=0.3, axis="y")

        self._figure.tight_layout()
        self._canvas.draw()
