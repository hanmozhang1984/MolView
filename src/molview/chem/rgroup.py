"""R-group decomposition using RDKit's RGroupDecompose."""
from __future__ import annotations

import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition


def _parse_core(core_smiles: str):
    """Parse a core SMILES/SMARTS for R-group decomposition.

    If the input contains R-group dummy atoms ([*:n]) from Ketcher, they are
    preserved as-is for RGroupDecompose (which uses them as attachment points).
    If parsing as SMILES fails, falls back to SMARTS.
    Also returns a plain scaffold (dummies removed) for substructure pre-filtering.
    """
    # Try SMILES first, then SMARTS
    core = Chem.MolFromSmiles(core_smiles)
    if core is None:
        core = Chem.MolFromSmarts(core_smiles)
    if core is None:
        return None, None

    has_dummies = any(a.GetAtomicNum() == 0 for a in core.GetAtoms())

    if has_dummies:
        # Build a plain scaffold for substructure filtering:
        # remove dummy atoms and sanitize
        rw = Chem.RWMol(core)
        for a in rw.GetAtoms():
            if a.GetAtomicNum() == 0:
                a.SetAtomicNum(1)
        try:
            Chem.SanitizeMol(rw)
            plain = Chem.RemoveHs(rw)
        except Exception:
            plain = core
        return core, plain
    else:
        return core, core


def rgroup_decompose(
    smiles_series: pd.Series,
    core_smiles: str,
    progress_callback=None,
) -> pd.DataFrame | None:
    """Decompose molecules into core + R-groups.

    Args:
        smiles_series: Series of SMILES strings.
        core_smiles: SMILES or SMARTS of the core/scaffold.
            May include [*:n] R-group labels from Ketcher.
            May also be a plain scaffold SMILES without labels.
        progress_callback: Optional callable(int) for percent progress.

    Returns:
        DataFrame with columns Core, R1, R2, ... containing SMILES of fragments,
        or None if the core is invalid or no molecules match.
    """
    core_with_dummies, plain_core = _parse_core(core_smiles)
    if core_with_dummies is None:
        return None

    # Build mol list — no substructure pre-filter when core has dummies
    # (the dummy-labeled core won't match as a substructure).
    # Instead, let RGroupDecompose handle the matching and use 'unmatched' to filter.
    mols = []
    valid_indices = []
    total = len(smiles_series)

    for i, smiles in enumerate(smiles_series):
        if pd.notna(smiles) and str(smiles).strip():
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is not None:
                # Pre-filter with plain core if available and different from dummy core
                if plain_core is not core_with_dummies:
                    if not mol.HasSubstructMatch(plain_core):
                        continue
                mols.append(mol)
                valid_indices.append(i)

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(int((i + 1) / total * 50))

    if not mols:
        return None

    if progress_callback:
        progress_callback(60)

    # Run decomposition
    rgroup_results, unmatched = rdRGroupDecomposition.RGroupDecompose(
        [core_with_dummies], mols, asSmiles=True
    )

    if progress_callback:
        progress_callback(80)

    if not rgroup_results:
        return None

    # Filter out unmatched molecules
    matched_results = []
    matched_indices = []
    unmatched_set = set(unmatched)
    for j, entry in enumerate(rgroup_results):
        if j not in unmatched_set:
            matched_results.append(entry)
            matched_indices.append(valid_indices[j])

    if not matched_results:
        return None

    # Collect all R-group column names
    all_keys = set()
    for entry in matched_results:
        all_keys.update(entry.keys())

    # Build result DataFrame aligned with original index
    result = pd.DataFrame(index=range(total))
    for key in sorted(all_keys):
        result[key] = pd.Series(dtype=str)

    for j, entry in enumerate(matched_results):
        orig_idx = matched_indices[j]
        for key, val in entry.items():
            result.at[orig_idx, key] = val

    if progress_callback:
        progress_callback(100)

    return result
