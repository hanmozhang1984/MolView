from __future__ import annotations

import numpy as np
from scipy import stats

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QCheckBox, QLineEdit,
)
from PySide6.QtCore import Signal
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import RectangleSelector
import matplotlib.cm as cm

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType


class ScatterPlotWidget(QWidget):
    # Emitted when user selects points on the plot; carries set of DataFrame row indices
    points_selected = Signal(set)

    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self._dataset = dataset
        self._point_indices = []  # maps scatter point index -> DataFrame row index
        self._scatter_collection = None
        self._annotation = None
        self._rect_selector = None
        self._pick_connected = False
        self._x_valid = None  # stored for rectangle selection
        self._y_valid = None

        layout = QVBoxLayout(self)

        # Column selectors
        selector_layout = QHBoxLayout()

        selector_layout.addWidget(QLabel("X:"))
        self._x_combo = QComboBox()
        selector_layout.addWidget(self._x_combo)

        selector_layout.addWidget(QLabel("Y:"))
        self._y_combo = QComboBox()
        selector_layout.addWidget(self._y_combo)

        selector_layout.addWidget(QLabel("Color by:"))
        self._color_combo = QComboBox()
        self._color_combo.addItem("(None)")
        selector_layout.addWidget(self._color_combo)

        self._regression_cb = QCheckBox("Regression Line")
        self._regression_cb.setChecked(True)
        selector_layout.addWidget(self._regression_cb)

        self._highlight_cb = QCheckBox("Highlight Selected")
        self._highlight_cb.setChecked(True)
        selector_layout.addWidget(self._highlight_cb)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self._do_plot)
        selector_layout.addWidget(plot_btn)

        layout.addLayout(selector_layout)

        # Axis range controls
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("X min:"))
        self._x_min = QLineEdit()
        self._x_min.setPlaceholderText("auto")
        self._x_min.setMaximumWidth(70)
        range_layout.addWidget(self._x_min)
        range_layout.addWidget(QLabel("X max:"))
        self._x_max = QLineEdit()
        self._x_max.setPlaceholderText("auto")
        self._x_max.setMaximumWidth(70)
        range_layout.addWidget(self._x_max)
        range_layout.addWidget(QLabel("Y min:"))
        self._y_min = QLineEdit()
        self._y_min.setPlaceholderText("auto")
        self._y_min.setMaximumWidth(70)
        range_layout.addWidget(self._y_min)
        range_layout.addWidget(QLabel("Y max:"))
        self._y_max = QLineEdit()
        self._y_max.setPlaceholderText("auto")
        self._y_max.setMaximumWidth(70)
        range_layout.addWidget(self._y_max)

        # Custom equation
        range_layout.addWidget(QLabel("Equation y="))
        self._custom_eq = QLineEdit()
        self._custom_eq.setPlaceholderText("e.g. 2*x + 1")
        self._custom_eq.setMaximumWidth(150)
        range_layout.addWidget(self._custom_eq)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # Matplotlib canvas
        self._figure = Figure(figsize=(8, 5), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)

        # Hover tooltip connection is deferred to _do_plot to avoid
        # setMouseTracking(True) interfering with QComboBox on macOS
        self._hover_connected = False

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

        # Skip rebuild if columns haven't changed (avoids destroying popup state)
        existing_numeric = [self._x_combo.itemText(i) for i in range(self._x_combo.count())]
        existing_color = [self._color_combo.itemText(i) for i in range(self._color_combo.count())]
        expected_color = ["(None)"] + all_cols
        if existing_numeric == numeric_cols and existing_color == expected_color:
            return

        current_x = self._x_combo.currentText()
        current_y = self._y_combo.currentText()
        current_color = self._color_combo.currentText()

        self._x_combo.blockSignals(True)
        self._y_combo.blockSignals(True)
        self._color_combo.blockSignals(True)

        self._x_combo.clear()
        self._y_combo.clear()
        self._color_combo.clear()
        self._color_combo.addItem("(None)")

        for name in numeric_cols:
            self._x_combo.addItem(name)
            self._y_combo.addItem(name)
        for name in all_cols:
            self._color_combo.addItem(name)

        # Restore selection if possible
        for combo, prev in [(self._x_combo, current_x), (self._y_combo, current_y),
                            (self._color_combo, current_color)]:
            if prev:
                idx = combo.findText(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        self._x_combo.blockSignals(False)
        self._y_combo.blockSignals(False)
        self._color_combo.blockSignals(False)

    def _do_plot(self):
        x_col = self._x_combo.currentText()
        y_col = self._y_combo.currentText()
        if not x_col or not y_col:
            return

        self._figure.clear()
        ax = self._figure.add_subplot(111)
        self._scatter_collection = None
        self._point_indices = []

        df = self._dataset.df
        hidden = self._dataset.hidden_rows
        selected = self._dataset.selected_rows
        color_col = self._color_combo.currentText()
        use_color = color_col and color_col != "(None)"

        # Filter visible rows
        visible_mask = ~df.index.isin(hidden)
        x_data = df.loc[visible_mask, x_col].astype(float)
        y_data = df.loc[visible_mask, y_col].astype(float)

        # Drop NaN
        valid = x_data.notna() & y_data.notna()
        x_valid = x_data[valid]
        y_valid = y_data[valid]
        indices = x_valid.index
        self._point_indices = list(indices)
        self._x_valid = x_valid
        self._y_valid = y_valid

        if len(x_valid) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes)
            self._canvas.draw()
            return

        # Color by column
        if use_color and color_col in df.columns:
            color_data = df.loc[indices, color_col]
            color_schema = self._dataset.get_schema(color_col)

            if color_schema.col_type == ColumnType.NUMERIC:
                # Numeric: continuous colormap
                color_vals = color_data.astype(float)
                valid_colors = color_vals.notna()
                sc = ax.scatter(
                    x_valid[valid_colors], y_valid[valid_colors],
                    c=color_vals[valid_colors], cmap='viridis',
                    alpha=0.7, s=30, edgecolors='none'
                )
                self._scatter_collection = sc
                self._figure.colorbar(sc, ax=ax, label=color_col, shrink=0.8)
                # Plot NaN-color points in gray
                if (~valid_colors).any():
                    ax.scatter(x_valid[~valid_colors], y_valid[~valid_colors],
                               c='#cccccc', alpha=0.4, s=20)
            else:
                # Categorical: discrete colors
                groups = color_data.fillna("(N/A)")
                unique_vals = sorted(groups.unique(), key=str)
                cmap = cm.get_cmap('tab10')
                for gi, gval in enumerate(unique_vals):
                    mask = groups == gval
                    color = cmap(gi % 10)
                    sc = ax.scatter(
                        x_valid[mask], y_valid[mask],
                        c=[color], alpha=0.7, s=30, label=str(gval),
                        edgecolors='none'
                    )
                if len(unique_vals) <= 20:
                    ax.legend(fontsize=7, loc='best', ncol=max(1, len(unique_vals) // 10))

        elif self._highlight_cb.isChecked() and selected:
            sel_mask = indices.isin(selected)
            # Plot non-selected
            sc = ax.scatter(x_valid[~sel_mask], y_valid[~sel_mask],
                       c="#4a90d9", alpha=0.6, s=30, label="Data")
            self._scatter_collection = sc
            # Plot selected
            if sel_mask.any():
                ax.scatter(x_valid[sel_mask], y_valid[sel_mask],
                           c="#e74c3c", alpha=0.9, s=50, edgecolors="black",
                           label="Selected")
        else:
            sc = ax.scatter(x_valid, y_valid, c="#4a90d9", alpha=0.6, s=30)
            self._scatter_collection = sc

        # Regression line
        if self._regression_cb.isChecked() and len(x_valid) >= 2:
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_valid, y_valid)
            x_line = np.linspace(x_valid.min(), x_valid.max(), 100)
            y_line = slope * x_line + intercept
            ax.plot(x_line, y_line, "r-", linewidth=1.5,
                    label=f"y = {slope:.4f}x + {intercept:.4f}\nR\u00b2 = {r_value**2:.4f}")

        # Custom equation
        eq_text = self._custom_eq.text().strip()
        if eq_text:
            try:
                x_line = np.linspace(x_valid.min(), x_valid.max(), 200)
                x = x_line  # for eval
                y_line = eval(eq_text)
                ax.plot(x_line, y_line, "g--", linewidth=1.5, label=f"y = {eq_text}")
            except Exception:
                pass

        # Axis ranges
        try:
            if self._x_min.text().strip():
                ax.set_xlim(left=float(self._x_min.text()))
            if self._x_max.text().strip():
                ax.set_xlim(right=float(self._x_max.text()))
            if self._y_min.text().strip():
                ax.set_ylim(bottom=float(self._y_min.text()))
            if self._y_max.text().strip():
                ax.set_ylim(top=float(self._y_max.text()))
        except ValueError:
            pass

        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        if not use_color or (use_color and self._dataset.get_schema(color_col).col_type != ColumnType.NUMERIC):
            ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Create annotation for hover tooltip
        self._annotation = ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="gray", alpha=0.9),
            fontsize=8,
        )
        self._annotation.set_visible(False)

        self._figure.tight_layout()
        self._canvas.draw()

        # Connect events after first plot so mouse tracking doesn't
        # interfere with QComboBox dropdowns before plotting
        if not self._hover_connected:
            self._canvas.mpl_connect('motion_notify_event', self._on_hover)
            self._hover_connected = True
        if not self._pick_connected:
            self._canvas.mpl_connect('button_press_event', self._on_click)
            self._pick_connected = True

        # Rectangle selector for multi-point selection (right-drag or shift-drag)
        self._rect_selector = RectangleSelector(
            ax, self._on_rect_select,
            useblit=True,
            button=[1],  # left mouse button
            minspanx=5, minspany=5,
            spancoords='pixels',
            interactive=False,
            props=dict(facecolor='blue', alpha=0.15, edgecolor='blue', linewidth=1),
        )

    def _on_hover(self, event):
        """Show tooltip with row info when hovering over a data point."""
        if self._annotation is None or event.inaxes is None:
            if self._annotation is not None and self._annotation.get_visible():
                self._annotation.set_visible(False)
                self._canvas.draw_idle()
            return
        if self._scatter_collection is None:
            return

        cont, ind = self._scatter_collection.contains(event)
        if cont and len(ind["ind"]) > 0:
            point_idx = ind["ind"][0]
            if point_idx < len(self._point_indices):
                df_row = self._point_indices[point_idx]

                # Build tooltip text
                lines = [f"Row: {df_row + 1}"]
                x_col = self._x_combo.currentText()
                y_col = self._y_combo.currentText()
                if x_col:
                    lines.append(f"{x_col}: {self._dataset.df.at[df_row, x_col]}")
                if y_col:
                    lines.append(f"{y_col}: {self._dataset.df.at[df_row, y_col]}")
                # Show first SMILES column if any
                for i in range(self._dataset.column_count):
                    cn = self._dataset.column_name(i)
                    if self._dataset.get_schema(cn).col_type == ColumnType.SMILES:
                        smiles = self._dataset.df.at[df_row, cn]
                        if smiles and str(smiles).strip():
                            s = str(smiles)
                            if len(s) > 40:
                                s = s[:37] + "..."
                            lines.append(f"SMILES: {s}")
                        break

                new_text = "\n".join(lines)
                # Only redraw if annotation content changed
                if not self._annotation.get_visible() or self._annotation.get_text() != new_text:
                    self._annotation.xy = (event.xdata, event.ydata)
                    self._annotation.set_text(new_text)
                    self._annotation.set_visible(True)
                    self._canvas.draw_idle()
        else:
            if self._annotation.get_visible():
                self._annotation.set_visible(False)
                self._canvas.draw_idle()

    def _on_click(self, event):
        """Handle single click to select a point. Shift+click adds to selection."""
        if event.inaxes is None or self._scatter_collection is None:
            return
        # Don't interfere with toolbar pan/zoom
        if self._toolbar.mode:
            return

        cont, ind = self._scatter_collection.contains(event)
        if cont and len(ind["ind"]) > 0:
            # Find the closest point
            point_idx = ind["ind"][0]
            if point_idx < len(self._point_indices):
                df_row = self._point_indices[point_idx]

                from PySide6.QtWidgets import QApplication
                from PySide6.QtCore import Qt
                modifiers = QApplication.keyboardModifiers()

                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    # Add to / remove from existing selection
                    current = set(self._dataset.selected_rows)
                    if df_row in current:
                        current.discard(df_row)
                    else:
                        current.add(df_row)
                    self._apply_selection(current)
                else:
                    # Replace selection with single point
                    self._apply_selection({df_row})
        else:
            # Click on empty space: clear selection (unless shift held)
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                self._apply_selection(set())

    def _on_rect_select(self, eclick, erelease):
        """Handle rectangle drag to select all points within the rectangle."""
        if self._x_valid is None or self._y_valid is None:
            return
        # Don't interfere with toolbar pan/zoom
        if self._toolbar.mode:
            return

        x1, x2 = sorted([eclick.xdata, erelease.xdata])
        y1, y2 = sorted([eclick.ydata, erelease.ydata])

        # Find all points inside the rectangle
        selected = set()
        for i, df_row in enumerate(self._point_indices):
            if df_row < len(self._x_valid.index):
                idx = self._x_valid.index[i] if i < len(self._x_valid) else None
                if idx is not None:
                    xv = self._x_valid.iloc[i]
                    yv = self._y_valid.iloc[i]
                    if x1 <= xv <= x2 and y1 <= yv <= y2:
                        selected.add(df_row)

        if selected:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                # Add to existing selection
                selected |= self._dataset.selected_rows
            self._apply_selection(selected)

    def _apply_selection(self, rows: set):
        """Apply selection to dataset, highlight on plot, and emit signal."""
        self._dataset.select_rows(rows)
        self._dataset.data_changed.emit()
        self._draw_selection_highlight(rows)
        self.points_selected.emit(rows)

    def _draw_selection_highlight(self, rows: set):
        """Draw bold rings around selected points on the plot."""
        # Remove previous highlight layer
        if hasattr(self, '_highlight_scatter') and self._highlight_scatter is not None:
            self._highlight_scatter.remove()
            self._highlight_scatter = None

        if not rows or self._x_valid is None or self._y_valid is None:
            self._canvas.draw_idle()
            return

        # Find x, y of selected points
        sel_x = []
        sel_y = []
        for i, df_row in enumerate(self._point_indices):
            if df_row in rows and i < len(self._x_valid):
                sel_x.append(self._x_valid.iloc[i])
                sel_y.append(self._y_valid.iloc[i])

        if sel_x:
            ax = self._figure.axes[0] if self._figure.axes else None
            if ax is not None:
                # Preserve current axis limits so the highlight doesn't rescale
                xlim = ax.get_xlim()
                ylim = ax.get_ylim()
                self._highlight_scatter = ax.scatter(
                    sel_x, sel_y,
                    s=120, facecolors='none', edgecolors='#e74c3c',
                    linewidths=2.5, zorder=10, label='_nolegend_'
                )
                ax.set_xlim(xlim)
                ax.set_ylim(ylim)
        self._canvas.draw_idle()
