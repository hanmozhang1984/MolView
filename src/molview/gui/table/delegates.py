from __future__ import annotations

import io
from functools import lru_cache

from PySide6.QtCore import QRect, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from molview.gui.table.table_model import SMILES_ROLE

# Structure size presets: (cell_width, cell_height, row_height)
STRUCTURE_SIZES = {
    "Small": (100, 70, 75),
    "Medium": (150, 100, 105),
    "Large": (200, 140, 145),
}

# Current setting (module-level, shared across delegates)
_current_size = "Medium"


def get_structure_size() -> str:
    return _current_size


def set_structure_size(size: str):
    global _current_size
    if size in STRUCTURE_SIZES:
        _current_size = size
        _smiles_to_pixmap.cache_clear()


def get_structure_cell_size() -> QSize:
    w, h, _ = STRUCTURE_SIZES[_current_size]
    return QSize(w, h)


def get_structure_row_height() -> int:
    _, _, rh = STRUCTURE_SIZES[_current_size]
    return rh


@lru_cache(maxsize=2000)
def _smiles_to_pixmap(smiles: str, width: int, height: int) -> QPixmap | None:
    """Render a SMILES string to a QPixmap via RDKit. Cached by SMILES."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        img = Draw.MolToImage(mol, size=(width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage()
        qimg.loadFromData(buf.getvalue())
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


class StructureDelegate(QStyledItemDelegate):
    """Renders 2D molecular structure depictions in SMILES columns."""

    def paint(self, painter, option: QStyleOptionViewItem, index):
        smiles = index.data(SMILES_ROLE)
        if smiles and isinstance(smiles, str) and smiles.strip():
            rect: QRect = option.rect
            pixmap = _smiles_to_pixmap(smiles, rect.width(), rect.height())
            if pixmap is not None:
                # Always use white background for structures (even in dark mode)
                painter.fillRect(rect, Qt.GlobalColor.white)
                # Center the pixmap
                scaled = pixmap.scaled(
                    rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                x = rect.x() + (rect.width() - scaled.width()) // 2
                y = rect.y() + (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
                return
        # Fallback: default painting for non-SMILES or invalid
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        smiles = index.data(SMILES_ROLE)
        if smiles:
            return get_structure_cell_size()
        return super().sizeHint(option, index)
