from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QUndoStack

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType
from molview.models.undo_commands import CellEditCommand

# Custom role for identifying SMILES columns
SMILES_ROLE = Qt.ItemDataRole.UserRole + 1
COLUMN_TYPE_ROLE = Qt.ItemDataRole.UserRole + 2


class DataFrameTableModel(QAbstractTableModel):
    """QAbstractTableModel backed by a DataSet (pandas DataFrame wrapper).

    Reads directly from the DataFrame — no per-cell object creation.
    """

    def __init__(self, dataset: DataSet, undo_stack: QUndoStack | None = None, parent=None):
        super().__init__(parent)
        self._dataset = dataset
        self._undo_stack = undo_stack
        dataset.data_changed.connect(self._on_data_changed)
        dataset.columns_changed.connect(self._on_structure_changed)
        dataset.rows_changed.connect(self._on_structure_changed)

    @property
    def dataset(self) -> DataSet:
        return self._dataset

    def set_dataset(self, dataset: DataSet):
        self.beginResetModel()
        self._dataset.data_changed.disconnect(self._on_data_changed)
        self._dataset.columns_changed.disconnect(self._on_structure_changed)
        self._dataset.rows_changed.disconnect(self._on_structure_changed)
        self._dataset = dataset
        dataset.data_changed.connect(self._on_data_changed)
        dataset.columns_changed.connect(self._on_structure_changed)
        dataset.rows_changed.connect(self._on_structure_changed)
        self.endResetModel()

    def _on_data_changed(self):
        top_left = self.index(0, 0)
        bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def _on_structure_changed(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return self._dataset.row_count

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return self._dataset.column_count

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row, col = index.row(), index.column()

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self._dataset.get_value(row, col)
            col_name = self._dataset.column_name(col)
            schema = self._dataset.get_schema(col_name)
            if schema.col_type == ColumnType.SMILES and role == Qt.ItemDataRole.DisplayRole:
                return None  # Structure delegate will paint this
            if role == Qt.ItemDataRole.DisplayRole:
                return schema.format_value(value)
            return value  # Raw value for editing

        if role == SMILES_ROLE:
            col_name = self._dataset.column_name(col)
            schema = self._dataset.get_schema(col_name)
            if schema.col_type == ColumnType.SMILES:
                return self._dataset.get_value(row, col)
            return None

        if role == COLUMN_TYPE_ROLE:
            col_name = self._dataset.column_name(col)
            return self._dataset.get_schema(col_name).col_type

        if role == Qt.ItemDataRole.BackgroundRole:
            if row in self._dataset.selected_rows:
                return QColor(200, 220, 255)
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < self._dataset.column_count:
                name = self._dataset.column_name(section)
                if name == "_MolBlock":
                    return "Structure\n(MOL)"
                # Insert newline at spaces in long names to allow wrapping
                if len(name) > 12 and " " in name:
                    mid = len(name) // 2
                    # Find the space closest to the middle
                    best = name.index(" ")
                    for i, ch in enumerate(name):
                        if ch == " " and abs(i - mid) < abs(best - mid):
                            best = i
                    return name[:best] + "\n" + name[best + 1:]
                return name
        else:
            return str(section + 1)
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        col_name = self._dataset.column_name(index.column())
        if col_name != "_MolBlock":
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        if self._undo_stack is not None:
            old_value = self._dataset.get_value(row, col)
            if old_value == value:
                return False
            cmd = CellEditCommand(self._dataset, row, col, old_value, value)
            self._undo_stack.push(cmd)
        else:
            self._dataset.set_value(row, col, value)
        self.dataChanged.emit(index, index)
        return True
