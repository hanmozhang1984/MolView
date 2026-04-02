from __future__ import annotations

from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex

from molview.models.dataset import DataSet


class FilterProxyModel(QSortFilterProxyModel):
    """Proxy model that hides rows, supports column text filters,
    multi-column sorting, and pinning selected/highlighted rows."""

    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self._dataset = dataset
        self._selected_pin = 0  # 0=off, 1=top, -1=bottom
        self._highlighted_pin = 0  # 0=off, 1=top, -1=bottom
        self._column_filters: dict[int, str] = {}  # col_index -> filter text
        self._sort_keys: list[tuple[int, Qt.SortOrder]] = []  # multi-column sort
        dataset.rows_changed.connect(self.invalidateFilter)

    @property
    def selected_pin(self) -> int:
        return self._selected_pin

    # ── Pin by table selection (existing) ──

    def pin_selected_top(self):
        self._selected_pin = 1
        self.invalidate()

    def pin_selected_bottom(self):
        self._selected_pin = -1
        self.invalidate()

    def clear_pin(self):
        self._selected_pin = 0
        self._highlighted_pin = 0
        self.invalidate()

    # ── Pin by dataset highlighted rows ──

    def pin_highlighted_top(self):
        self._highlighted_pin = 1
        self._selected_pin = 0
        self.invalidate()

    def pin_highlighted_bottom(self):
        self._highlighted_pin = -1
        self._selected_pin = 0
        self.invalidate()

    # ── Column text filters ──

    def set_column_filter(self, col: int, text: str):
        """Set a text filter for a specific column. Empty string clears the filter."""
        if text:
            self._column_filters[col] = text.lower()
        else:
            self._column_filters.pop(col, None)
        self.invalidateFilter()

    def clear_all_column_filters(self):
        self._column_filters.clear()
        self.invalidateFilter()

    # ── Multi-column sorting ──

    def set_sort_key(self, col: int, order: Qt.SortOrder):
        """Set a single sort key (replaces all existing keys)."""
        self._sort_keys = [(col, order)]
        self.invalidate()

    def add_sort_key(self, col: int, order: Qt.SortOrder):
        """Add an additional sort key (for Shift+click)."""
        # Remove if this column is already a sort key
        self._sort_keys = [(c, o) for c, o in self._sort_keys if c != col]
        self._sort_keys.append((col, order))
        self.invalidate()

    def clear_sort_keys(self):
        self._sort_keys.clear()
        self.invalidate()

    @property
    def sort_keys(self) -> list[tuple[int, Qt.SortOrder]]:
        return list(self._sort_keys)

    # ── Overrides ──

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if source_row in self._dataset.hidden_rows:
            return False

        # Check column text filters
        if self._column_filters:
            model = self.sourceModel()
            for col, filter_text in self._column_filters.items():
                idx = model.index(source_row, col)
                value = model.data(idx, Qt.ItemDataRole.EditRole)
                if value is None:
                    value = ""
                if filter_text not in str(value).lower():
                    return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_row = left.row()
        right_row = right.row()

        # Highlighted pin (dataset.selected_rows — the light-blue highlighted rows)
        if self._highlighted_pin != 0:
            left_hl = left_row in self._dataset.selected_rows
            right_hl = right_row in self._dataset.selected_rows
            if left_hl != right_hl:
                if self._highlighted_pin == 1:
                    return left_hl
                else:
                    return right_hl

        # Selected pin (table view selection)
        if self._selected_pin != 0:
            left_sel = left_row in self._dataset.selected_rows
            right_sel = right_row in self._dataset.selected_rows
            if left_sel != right_sel:
                if self._selected_pin == 1:
                    return left_sel
                else:
                    return right_sel

        # Multi-column sort
        if self._sort_keys:
            model = self.sourceModel()
            for col, order in self._sort_keys:
                left_idx = model.index(left_row, col)
                right_idx = model.index(right_row, col)
                cmp = self._compare_values(
                    model.data(left_idx), model.data(right_idx)
                )
                if cmp != 0:
                    # If descending, flip the comparison
                    if order == Qt.SortOrder.DescendingOrder:
                        return cmp > 0
                    return cmp < 0
            return False

        # Default single-column sort
        left_data = self.sourceModel().data(left)
        right_data = self.sourceModel().data(right)
        return self._compare_values(left_data, right_data) < 0

    @staticmethod
    def _compare_values(left, right) -> int:
        """Compare two values, returning -1, 0, or 1. Handles numeric and string types."""
        try:
            lf, rf = float(left), float(right)
            if lf < rf:
                return -1
            elif lf > rf:
                return 1
            return 0
        except (ValueError, TypeError):
            ls = str(left) if left is not None else ""
            rs = str(right) if right is not None else ""
            if ls < rs:
                return -1
            elif ls > rs:
                return 1
            return 0
