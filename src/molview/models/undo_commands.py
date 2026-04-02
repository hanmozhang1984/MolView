"""QUndoCommand subclasses for all DataSet mutation operations."""

from __future__ import annotations

import pandas as pd
import numpy as np
from PySide6.QtGui import QUndoCommand

from molview.models.column_schema import ColumnSchema, ColumnType


class CellEditCommand(QUndoCommand):
    """Undo/redo a single cell edit."""

    def __init__(self, dataset, row: int, col: int, old_value, new_value):
        super().__init__(f"Edit cell ({row}, {col})")
        self._dataset = dataset
        self._row = row
        self._col = col
        self._old_value = old_value
        self._new_value = new_value

    def redo(self):
        self._dataset.set_value(self._row, self._col, self._new_value)

    def undo(self):
        self._dataset.set_value(self._row, self._col, self._old_value)


class AddRowCommand(QUndoCommand):
    """Undo/redo adding a row."""

    def __init__(self, dataset, position: int | None = None):
        super().__init__("Add row")
        self._dataset = dataset
        self._position = position

    def redo(self):
        self._dataset.add_row(self._position)

    def undo(self):
        # The row was added at _position (or end). Remove it.
        if self._position is None or self._position >= self._dataset.row_count:
            idx = self._dataset.row_count - 1
        else:
            idx = self._position
        self._dataset.delete_rows([idx])


class DeleteRowsCommand(QUndoCommand):
    """Undo/redo deleting rows. Snapshots the deleted rows for restore."""

    def __init__(self, dataset, row_indices: list[int]):
        super().__init__(f"Delete {len(row_indices)} row(s)")
        self._dataset = dataset
        self._row_indices = sorted(row_indices)
        # Snapshot the rows before deletion
        self._snapshot = dataset.df.iloc[self._row_indices].copy()
        # Snapshot hidden/selected state for these rows
        self._were_hidden = set(r for r in self._row_indices if r in dataset.hidden_rows)
        self._were_selected = set(r for r in self._row_indices if r in dataset.selected_rows)

    def redo(self):
        self._dataset.delete_rows(self._row_indices)

    def undo(self):
        # Re-insert rows at their original positions
        df = self._dataset.df
        for i, orig_idx in enumerate(self._row_indices):
            row_data = self._snapshot.iloc[i]
            new_row = pd.DataFrame([row_data.to_dict()])
            if orig_idx >= len(df):
                self._dataset._df = pd.concat([df, new_row], ignore_index=True)
            else:
                top = df.iloc[:orig_idx]
                bottom = df.iloc[orig_idx:]
                self._dataset._df = pd.concat([top, new_row, bottom], ignore_index=True)
            df = self._dataset._df

        # Restore hidden/selected state
        self._dataset._hidden_rows |= self._were_hidden
        self._dataset._selected_rows |= self._were_selected
        self._dataset._modified = True
        self._dataset.rows_changed.emit()


class AddColumnCommand(QUndoCommand):
    """Undo/redo adding a column."""

    def __init__(self, dataset, name: str, col_type: ColumnType = ColumnType.TEXT,
                 default_value=None):
        super().__init__(f"Add column '{name}'")
        self._dataset = dataset
        self._name = name
        self._col_type = col_type
        self._default_value = default_value

    def redo(self):
        self._dataset.add_column(self._name, self._col_type, self._default_value)

    def undo(self):
        if self._name in self._dataset.df.columns:
            col_idx = list(self._dataset.df.columns).index(self._name)
            self._dataset.delete_column(col_idx)


class DeleteColumnCommand(QUndoCommand):
    """Undo/redo deleting a column. Snapshots the column data and schema."""

    def __init__(self, dataset, col_index: int):
        super().__init__(f"Delete column '{dataset.column_name(col_index)}'")
        self._dataset = dataset
        self._col_index = col_index
        self._col_name = dataset.column_name(col_index)
        # Snapshot column data and schema
        self._col_data = dataset.df[self._col_name].copy()
        self._schema = dataset.get_schema(self._col_name)

    def redo(self):
        if self._col_name in self._dataset.df.columns:
            col_idx = list(self._dataset.df.columns).index(self._col_name)
            self._dataset.delete_column(col_idx)

    def undo(self):
        # Re-insert column at original position
        self._dataset._df.insert(self._col_index, self._col_name, self._col_data)
        self._dataset._schemas[self._col_name] = self._schema
        self._dataset._modified = True
        self._dataset.columns_changed.emit()


class RenameColumnCommand(QUndoCommand):
    """Undo/redo renaming a column."""

    def __init__(self, dataset, old_name: str, new_name: str):
        super().__init__(f"Rename '{old_name}' to '{new_name}'")
        self._dataset = dataset
        self._old_name = old_name
        self._new_name = new_name

    def redo(self):
        self._do_rename(self._old_name, self._new_name)

    def undo(self):
        self._do_rename(self._new_name, self._old_name)

    def _do_rename(self, from_name: str, to_name: str):
        self._dataset.df.rename(columns={from_name: to_name}, inplace=True)
        if from_name in self._dataset.schemas:
            schema = self._dataset.schemas.pop(from_name)
            schema.name = to_name
            self._dataset.schemas[to_name] = schema
        self._dataset._modified = True
        self._dataset.columns_changed.emit()


class SetColumnFormatCommand(QUndoCommand):
    """Undo/redo changing a column's type or decimal places."""

    def __init__(self, dataset, col_name: str, old_schema: ColumnSchema, new_schema: ColumnSchema):
        super().__init__(f"Change format of '{col_name}'")
        self._dataset = dataset
        self._col_name = col_name
        self._old_schema = ColumnSchema(old_schema.name, old_schema.col_type, old_schema.decimal_places)
        self._new_schema = ColumnSchema(new_schema.name, new_schema.col_type, new_schema.decimal_places)

    def redo(self):
        self._dataset.set_schema(self._col_name, self._new_schema)

    def undo(self):
        self._dataset.set_schema(self._col_name, self._old_schema)
