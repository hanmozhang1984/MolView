from __future__ import annotations

import pandas as pd
from typing import Optional

from molview.models.column_schema import ColumnSchema


def load_excel(path: str) -> tuple[pd.DataFrame, Optional[dict[str, ColumnSchema]]]:
    """Load an Excel file. Returns (DataFrame, None) — schemas are auto-inferred."""
    df = pd.read_excel(path, engine="openpyxl")
    return df, None


def save_excel(path: str, df: pd.DataFrame):
    df.to_excel(path, index=False, engine="openpyxl")
