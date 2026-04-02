from __future__ import annotations

import pandas as pd
from typing import Optional

from molview.models.column_schema import ColumnSchema


def load_csv(path: str) -> tuple[pd.DataFrame, Optional[dict[str, ColumnSchema]]]:
    """Load a CSV file. Returns (DataFrame, None) — schemas are auto-inferred by DataSet."""
    df = pd.read_csv(path, sep=None, engine="python")  # auto-detect delimiter
    return df, None


def save_csv(path: str, df: pd.DataFrame):
    df.to_csv(path, index=False)
