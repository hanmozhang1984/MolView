from __future__ import annotations

import pandas as pd
from typing import Optional
from rdkit import Chem

from molview.models.column_schema import ColumnSchema, ColumnType


def load_mol(path: str) -> tuple[pd.DataFrame, Optional[dict[str, ColumnSchema]]]:
    """Load a single MOL file into a one-row DataFrame."""
    mol = Chem.MolFromMolFile(path, removeHs=True)
    if mol is None:
        return pd.DataFrame(), None

    smiles = Chem.MolToSmiles(mol)
    mol_block = Chem.MolToMolBlock(mol)
    row = {"SMILES": smiles, "_MolBlock": mol_block}
    for prop_name, prop_val in mol.GetPropsAsDict().items():
        row[prop_name] = prop_val

    df = pd.DataFrame([row])
    schemas = {
        "SMILES": ColumnSchema("SMILES", ColumnType.SMILES),
        "_MolBlock": ColumnSchema("_MolBlock", ColumnType.MOL_BLOCK),
    }
    return df, schemas


def save_mol(path: str, mol_block: str):
    """Write a single MOL block to a file."""
    with open(path, "w") as f:
        f.write(mol_block)
