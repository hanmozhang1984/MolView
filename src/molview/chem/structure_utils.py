from __future__ import annotations

import pandas as pd
from rdkit import Chem, rdBase


def detect_smiles_columns(df: pd.DataFrame, sample_size: int = 20) -> list[str]:
    """Detect columns that likely contain SMILES strings.

    Suppresses RDKit parse warnings during detection since we're intentionally
    testing non-SMILES strings.
    """
    # Suppress all RDKit logging during detection
    rdBase.DisableLog("rdApp.*")

    smiles_cols = []
    try:
        for col in df.columns:
            if df[col].dtype != object:
                continue
            sample = df[col].dropna().head(sample_size)
            if len(sample) == 0:
                continue
            valid = 0
            for val in sample:
                s = str(val).strip()
                if len(s) < 2:
                    continue
                mol = Chem.MolFromSmiles(s, sanitize=True)
                if mol is not None:
                    valid += 1
            if valid >= len(sample) * 0.6:
                smiles_cols.append(col)
    finally:
        rdBase.EnableLog("rdApp.*")

    return smiles_cols
