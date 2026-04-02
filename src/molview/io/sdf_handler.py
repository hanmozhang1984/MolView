from __future__ import annotations

import pandas as pd
from typing import Optional
from rdkit import Chem
from rdkit.Chem import AllChem

from molview.models.column_schema import ColumnSchema, ColumnType


def load_sdf(
    path: str,
    progress_callback=None,
) -> tuple[pd.DataFrame, Optional[dict[str, ColumnSchema]]]:
    """Load an SDF file into a DataFrame with SMILES and property columns.

    Args:
        path: Path to SDF file.
        progress_callback: Optional callable(int) receiving percent progress (0-100).
    """
    supplier = Chem.SDMolSupplier(path, removeHs=True)
    total = len(supplier)

    rows = []
    for i, mol in enumerate(supplier):
        if mol is None:
            continue
        props = mol.GetPropsAsDict()
        row = {"SMILES": Chem.MolToSmiles(mol), "_MolBlock": Chem.MolToMolBlock(mol)}
        row.update(props)
        rows.append(row)

        if progress_callback and total > 0 and (i + 1) % 100 == 0:
            progress_callback(int((i + 1) / total * 100))

    if progress_callback:
        progress_callback(100)

    df = pd.DataFrame(rows)
    if df.empty:
        return df, None

    schemas = {
        "SMILES": ColumnSchema("SMILES", ColumnType.SMILES),
        "_MolBlock": ColumnSchema("_MolBlock", ColumnType.MOL_BLOCK),
    }
    return df, schemas


def save_sdf(path: str, df: pd.DataFrame, smiles_col: str = "SMILES"):
    """Write DataFrame back to SDF. Uses _MolBlock if available, else generates from SMILES."""
    writer = Chem.SDWriter(path)
    skip_cols = {smiles_col, "_MolBlock"}

    for _, row in df.iterrows():
        mol = None
        if "_MolBlock" in df.columns and pd.notna(row.get("_MolBlock")):
            mol = Chem.MolFromMolBlock(row["_MolBlock"])
        if mol is None and smiles_col in df.columns and pd.notna(row.get(smiles_col)):
            mol = Chem.MolFromSmiles(row[smiles_col])
            if mol is not None:
                AllChem.Compute2DCoords(mol)
        if mol is None:
            continue

        for col in df.columns:
            if col in skip_cols:
                continue
            val = row[col]
            if pd.notna(val):
                mol.SetProp(col, str(val))

        writer.write(mol)
    writer.close()
