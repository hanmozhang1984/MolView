from enum import Enum, auto


class ColumnType(Enum):
    TEXT = auto()
    NUMERIC = auto()
    SMILES = auto()
    MOL_BLOCK = auto()


class ColumnSchema:
    """Metadata for a single column: type, display format, etc."""

    def __init__(self, name: str, col_type: ColumnType = ColumnType.TEXT,
                 decimal_places: int = 2):
        self.name = name
        self.col_type = col_type
        self.decimal_places = decimal_places

    def format_value(self, value) -> str:
        if value is None or (isinstance(value, float) and __import__('math').isnan(value)):
            return ""
        if self.col_type == ColumnType.NUMERIC:
            try:
                return f"{float(value):.{self.decimal_places}f}"
            except (ValueError, TypeError):
                return str(value)
        return str(value)
