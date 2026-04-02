from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional
from PySide6.QtCore import QObject, Signal

from molview.models.column_schema import ColumnSchema, ColumnType


class DataSet(QObject):
    """Central data model wrapping a pandas DataFrame with column metadata and selection state."""

    data_changed = Signal()
    columns_changed = Signal()
    rows_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame()
        self._schemas: dict[str, ColumnSchema] = {}
        self._hidden_rows: set[int] = set()
        self._selected_rows: set[int] = set()
        self._file_path: Optional[str] = None
        self._modified = False

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def schemas(self) -> dict[str, ColumnSchema]:
        return self._schemas

    @property
    def hidden_rows(self) -> set[int]:
        return self._hidden_rows

    @property
    def selected_rows(self) -> set[int]:
        return self._selected_rows

    @property
    def file_path(self) -> Optional[str]:
        return self._file_path

    @file_path.setter
    def file_path(self, path: Optional[str]):
        self._file_path = path

    @property
    def modified(self) -> bool:
        return self._modified

    @modified.setter
    def modified(self, value: bool):
        self._modified = value

    @property
    def row_count(self) -> int:
        return len(self._df)

    @property
    def column_count(self) -> int:
        return len(self._df.columns)

    def load_dataframe(self, df: pd.DataFrame, schemas: Optional[dict[str, ColumnSchema]] = None):
        self._df = df.reset_index(drop=True)
        self._hidden_rows.clear()
        self._selected_rows.clear()
        self._modified = False

        if schemas:
            self._schemas = schemas
        else:
            self._schemas = {}
            for col in df.columns:
                self._schemas[col] = self._infer_schema(col)

        self.columns_changed.emit()

    def _infer_schema(self, col_name: str) -> ColumnSchema:
        series = self._df[col_name]
        if series.dtype in (np.float64, np.float32, np.int64, np.int32, float, int):
            return ColumnSchema(col_name, ColumnType.NUMERIC)
        # Try to detect numeric strings
        if series.dtype == object:
            sample = series.dropna().head(20)
            if len(sample) > 0:
                numeric_count = 0
                for val in sample:
                    try:
                        float(val)
                        numeric_count += 1
                    except (ValueError, TypeError):
                        pass
                if numeric_count > len(sample) * 0.8:
                    return ColumnSchema(col_name, ColumnType.NUMERIC)
        return ColumnSchema(col_name, ColumnType.TEXT)

    def get_value(self, row: int, col: int):
        return self._df.iloc[row, col]

    def set_value(self, row: int, col: int, value):
        col_name = self._df.columns[col]
        schema = self._schemas.get(col_name)
        if schema and schema.col_type == ColumnType.NUMERIC:
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass
        self._df.iloc[row, col] = value
        self._modified = True
        self.data_changed.emit()

    def column_name(self, col: int) -> str:
        return self._df.columns[col]

    def get_schema(self, col_name: str) -> ColumnSchema:
        if col_name not in self._schemas:
            self._schemas[col_name] = ColumnSchema(col_name, ColumnType.TEXT)
        return self._schemas[col_name]

    def set_schema(self, col_name: str, schema: ColumnSchema):
        self._schemas[col_name] = schema
        self.data_changed.emit()

    def add_column(self, name: str, col_type: ColumnType = ColumnType.TEXT,
                   default_value=None):
        if name in self._df.columns:
            return False
        if default_value is None:
            default_value = np.nan if col_type == ColumnType.NUMERIC else ""
        self._df[name] = default_value
        self._schemas[name] = ColumnSchema(name, col_type)
        self._modified = True
        self.columns_changed.emit()
        return True

    def delete_column(self, col_index: int):
        col_name = self._df.columns[col_index]
        self._df.drop(columns=[col_name], inplace=True)
        self._schemas.pop(col_name, None)
        self._modified = True
        self.columns_changed.emit()

    def add_row(self, position: Optional[int] = None):
        new_row = {}
        for col in self._df.columns:
            schema = self._schemas.get(col)
            if schema and schema.col_type == ColumnType.NUMERIC:
                new_row[col] = np.nan
            else:
                new_row[col] = ""
        new_df = pd.DataFrame([new_row])
        if position is None or position >= len(self._df):
            self._df = pd.concat([self._df, new_df], ignore_index=True)
        else:
            top = self._df.iloc[:position]
            bottom = self._df.iloc[position:]
            self._df = pd.concat([top, new_df, bottom], ignore_index=True)
        self._hidden_rows.clear()
        self._selected_rows.clear()
        self._modified = True
        self.rows_changed.emit()

    def delete_rows(self, row_indices: list[int]):
        self._df.drop(index=row_indices, inplace=True)
        self._df.reset_index(drop=True, inplace=True)
        self._hidden_rows -= set(row_indices)
        self._selected_rows -= set(row_indices)
        self._modified = True
        self.rows_changed.emit()

    def toggle_row_hidden(self, row: int):
        if row in self._hidden_rows:
            self._hidden_rows.discard(row)
        else:
            self._hidden_rows.add(row)
        self.rows_changed.emit()

    def hide_rows(self, rows: set[int]):
        self._hidden_rows |= rows
        self.rows_changed.emit()

    def show_all_rows(self):
        self._hidden_rows.clear()
        self.rows_changed.emit()

    def toggle_row_selected(self, row: int):
        if row in self._selected_rows:
            self._selected_rows.discard(row)
        else:
            self._selected_rows.add(row)

    def select_rows(self, rows: set[int]):
        self._selected_rows = rows

    def clear_selection(self):
        self._selected_rows.clear()

    def is_empty(self) -> bool:
        return self._df.empty
