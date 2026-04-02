from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QStackedWidget, QFileDialog,
)

from molview.models.dataset import DataSet


class PlotPanel(QWidget):
    """Container widget for scatter, bar chart, and scatter matrix plotting.

    Plot widgets are created lazily — only when first selected — to avoid
    multiple FigureCanvasQTAgg instances interfering with Qt event handling.
    """

    # Emitted when user selects points on a plot
    points_selected = Signal(set)

    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self._dataset = dataset

        layout = QVBoxLayout(self)

        # Controls bar
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Plot Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Scatter Plot", "Bar Chart", "Scatter Matrix"])
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        controls.addWidget(self._type_combo)

        controls.addStretch()

        export_btn = QPushButton("Export Plot...")
        export_btn.clicked.connect(self._export_plot)
        controls.addWidget(export_btn)

        refresh_btn = QPushButton("Refresh Columns")
        refresh_btn.clicked.connect(self._refresh_active)
        controls.addWidget(refresh_btn)

        layout.addLayout(controls)

        # Stacked widget for plot types (lazy-loaded)
        self._plot_stack = QStackedWidget()
        layout.addWidget(self._plot_stack)

        # Placeholders — widgets created on first access
        self._scatter = None
        self._bar = None
        self._matrix = None
        self._placeholder_count = 3
        for _ in range(self._placeholder_count):
            self._plot_stack.addWidget(QWidget())  # empty placeholders

        # Create the initial widget (scatter)
        self._ensure_widget(0)
        self._plot_stack.setCurrentIndex(0)

        self._needs_refresh = True
        dataset.columns_changed.connect(self._mark_needs_refresh)

    def _mark_needs_refresh(self):
        self._needs_refresh = True
        if self.isVisible():
            self._refresh_active()

    def showEvent(self, event):
        super().showEvent(event)
        if self._needs_refresh:
            self._refresh_active()

    def _on_type_changed(self, index: int):
        self._ensure_widget(index)
        self._plot_stack.setCurrentIndex(index)
        self._refresh_active()

    def _ensure_widget(self, index: int):
        """Create the plot widget for the given index if not yet created."""
        if index == 0 and self._scatter is None:
            from molview.gui.plotting.scatter_plot import ScatterPlotWidget
            self._scatter = ScatterPlotWidget(self._dataset)
            self._scatter.points_selected.connect(self.points_selected)
            self._plot_stack.removeWidget(self._plot_stack.widget(0))
            self._plot_stack.insertWidget(0, self._scatter)
        elif index == 1 and self._bar is None:
            from molview.gui.plotting.bar_chart import BarChartWidget
            self._bar = BarChartWidget(self._dataset)
            self._plot_stack.removeWidget(self._plot_stack.widget(1))
            self._plot_stack.insertWidget(1, self._bar)
        elif index == 2 and self._matrix is None:
            from molview.gui.plotting.scatter_matrix import ScatterMatrixWidget
            self._matrix = ScatterMatrixWidget(self._dataset)
            self._plot_stack.removeWidget(self._plot_stack.widget(2))
            self._plot_stack.insertWidget(2, self._matrix)

    def _refresh_active(self):
        """Refresh columns only on the currently visible plot widget."""
        self._needs_refresh = False
        idx = self._plot_stack.currentIndex()
        widget = [self._scatter, self._bar, self._matrix][idx]
        if widget and hasattr(widget, 'refresh_columns'):
            widget.refresh_columns()

    def _export_plot(self):
        """Export the currently visible plot to PNG or SVG."""
        current = self._plot_stack.currentWidget()
        fig = getattr(current, '_figure', None)
        if fig is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plot",
            "",
            "PNG Image (*.png);;SVG Image (*.svg);;PDF Document (*.pdf);;All Files (*)"
        )
        if path:
            fig.savefig(path, dpi=150, bbox_inches='tight')
