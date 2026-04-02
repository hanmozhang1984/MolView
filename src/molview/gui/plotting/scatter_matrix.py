from __future__ import annotations

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QAbstractItemView, QComboBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
import matplotlib.cm as cm

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType


class ScatterMatrixWidget(QWidget):
    """Scatter matrix (paired plots) for 2-5 numeric columns."""

    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self._dataset = dataset

        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Select columns (2-5):"))

        self._col_list = QListWidget()
        self._col_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._col_list.setMaximumHeight(100)
        controls.addWidget(self._col_list)

        controls.addWidget(QLabel("Color by:"))
        self._color_combo = QComboBox()
        self._color_combo.addItem("(None)")
        controls.addWidget(self._color_combo)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self._do_plot)
        controls.addWidget(plot_btn)
        controls.addStretch()

        layout.addLayout(controls)

        # Canvas
        self._figure = Figure(figsize=(8, 8), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

        self.refresh_columns()

    def refresh_columns(self):
        # Build new column lists
        numeric_cols = []
        all_cols = []
        for i in range(self._dataset.column_count):
            col_name = self._dataset.column_name(i)
            schema = self._dataset.get_schema(col_name)
            all_cols.append(col_name)
            if schema.col_type == ColumnType.NUMERIC:
                numeric_cols.append(col_name)

        # Skip if unchanged
        existing = [self._col_list.item(i).text() for i in range(self._col_list.count())]
        if existing == numeric_cols:
            return

        self._col_list.clear()
        self._color_combo.blockSignals(True)
        self._color_combo.clear()
        self._color_combo.addItem("(None)")

        for name in numeric_cols:
            self._col_list.addItem(name)
        for name in all_cols:
            self._color_combo.addItem(name)
        self._color_combo.blockSignals(False)

    def _do_plot(self):
        selected_items = self._col_list.selectedItems()
        cols = [item.text() for item in selected_items]

        if len(cols) < 2:
            return
        if len(cols) > 5:
            cols = cols[:5]

        n = len(cols)
        self._figure.clear()

        df = self._dataset.df
        hidden = self._dataset.hidden_rows
        visible_mask = ~df.index.isin(hidden)
        vis_df = df[visible_mask]

        # Color setup
        color_col = self._color_combo.currentText()
        use_color = color_col and color_col != "(None)" and color_col in df.columns
        colors = None
        color_labels = None

        if use_color:
            color_schema = self._dataset.get_schema(color_col)
            color_data = vis_df[color_col]

            if color_schema.col_type == ColumnType.NUMERIC:
                color_vals = color_data.astype(float)
                norm = None
                if color_vals.notna().any():
                    vmin, vmax = color_vals.min(), color_vals.max()
                    if vmin == vmax:
                        colors = ['#4a90d9'] * len(vis_df)
                    else:
                        cmap_obj = cm.get_cmap('viridis')
                        normed = (color_vals.fillna(vmin) - vmin) / (vmax - vmin)
                        colors = [cmap_obj(v) for v in normed]
            else:
                groups = color_data.fillna("(N/A)")
                unique_vals = sorted(groups.unique(), key=str)
                cmap_obj = cm.get_cmap('tab10')
                color_map = {v: cmap_obj(i % 10) for i, v in enumerate(unique_vals)}
                colors = [color_map[v] for v in groups]
                color_labels = {v: cmap_obj(i % 10) for i, v in enumerate(unique_vals)}

        axes = self._figure.subplots(n, n, squeeze=False)

        for i in range(n):
            for j in range(n):
                ax = axes[i][j]
                y_data = vis_df[cols[i]].astype(float)
                x_data = vis_df[cols[j]].astype(float)

                valid = x_data.notna() & y_data.notna()
                xv = x_data[valid].values
                yv = y_data[valid].values

                if i == j:
                    # Diagonal: histogram
                    ax.hist(xv, bins=20, color='#4a90d9', alpha=0.7, edgecolor='white')
                else:
                    # Off-diagonal: scatter
                    if colors is not None:
                        c_valid = [colors[k] for k in range(len(valid)) if valid.iloc[k]]
                        ax.scatter(xv, yv, c=c_valid, alpha=0.5, s=10, edgecolors='none')
                    else:
                        ax.scatter(xv, yv, c='#4a90d9', alpha=0.5, s=10, edgecolors='none')

                # Labels on edges only
                if i == n - 1:
                    ax.set_xlabel(cols[j], fontsize=7)
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel(cols[i], fontsize=7)
                else:
                    ax.set_yticklabels([])

                ax.tick_params(labelsize=6)

        # Add legend for categorical coloring
        if color_labels and len(color_labels) <= 15:
            handles = [
                axes[0][0].scatter([], [], c=[c], label=str(v), s=20)
                for v, c in color_labels.items()
            ]
            self._figure.legend(
                handles=handles, loc='upper right', fontsize=6,
                ncol=max(1, len(color_labels) // 8)
            )

        self._figure.tight_layout()
        self._canvas.draw()
