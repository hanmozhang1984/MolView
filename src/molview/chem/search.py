from __future__ import annotations

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem, rdFingerprintGenerator


def exact_match_search(smiles_series: pd.Series, query_smiles: str,
                       progress_callback=None) -> list[bool]:
    """Return a boolean mask: True for rows whose canonical SMILES matches the query exactly."""
    query_mol = Chem.MolFromSmiles(query_smiles)
    if query_mol is None:
        return [False] * len(smiles_series)
    canonical_query = Chem.MolToSmiles(query_mol)

    results = []
    total = len(smiles_series)
    for i, smiles in enumerate(smiles_series):
        if pd.notna(smiles) and str(smiles).strip():
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is not None:
                results.append(Chem.MolToSmiles(mol) == canonical_query)
            else:
                results.append(False)
        else:
            results.append(False)

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(int((i + 1) / total * 100))

    return results


def substructure_search(smiles_series: pd.Series, query_smarts: str,
                        progress_callback=None) -> list[bool]:
    """Return a boolean mask: True for rows whose molecule contains the query substructure.

    Accepts SMILES or SMARTS as query. SMILES input (e.g. from Ketcher) is
    converted to a proper substructure query that handles aromaticity correctly.
    """
    # Try parsing as SMILES first (handles Ketcher output like C1=CC=CC=C1),
    # then fall back to SMARTS for explicit query patterns
    query = Chem.MolFromSmiles(query_smarts)
    if query is None:
        query = Chem.MolFromSmarts(query_smarts)
    if query is None:
        return [False] * len(smiles_series)

    results = []
    total = len(smiles_series)
    for i, smiles in enumerate(smiles_series):
        if pd.notna(smiles) and str(smiles).strip():
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is not None:
                results.append(mol.HasSubstructMatch(query))
            else:
                results.append(False)
        else:
            results.append(False)

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(int((i + 1) / total * 100))

    return results


def similarity_search(smiles_series: pd.Series, query_smiles: str,
                      threshold: float = 0.7,
                      progress_callback=None) -> list[float]:
    """Return Tanimoto similarity scores for each row vs the query molecule.

    Scores below threshold are set to 0.0.
    """
    query_mol = Chem.MolFromSmiles(query_smiles)
    if query_mol is None:
        return [0.0] * len(smiles_series)

    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    query_fp = fpgen.GetFingerprint(query_mol)

    results = []
    total = len(smiles_series)
    for i, smiles in enumerate(smiles_series):
        score = 0.0
        if pd.notna(smiles) and str(smiles).strip():
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is not None:
                fp = fpgen.GetFingerprint(mol)
                score = DataStructs.TanimotoSimilarity(query_fp, fp)
                if score < threshold:
                    score = 0.0
        results.append(round(score, 4))

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(int((i + 1) / total * 100))

    return results
