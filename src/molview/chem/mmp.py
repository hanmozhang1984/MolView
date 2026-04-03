"""Matched Molecular Pair (MMP) analysis using RDKit's MMPA fragmentation."""
from __future__ import annotations

import pandas as pd
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMMPA
from collections import defaultdict


def find_matched_pairs(
    smiles_series: pd.Series,
    property_col: pd.Series | None = None,
    data_cols: dict[str, pd.Series] | None = None,
    max_cuts: int = 1,
    min_context_atoms: int = 6,
    max_rgroup_atoms: int = 13,
    progress_callback=None,
) -> pd.DataFrame:
    """Find matched molecular pairs by fragmentation.

    For 1-cut: each molecule is fragmented into (context, R-group) pairs.
    Molecules sharing the same context are matched molecular pairs.

    Args:
        smiles_series: Series of SMILES strings.
        property_col: Optional numeric property Series for computing deltas.
        max_cuts: Number of cuts for fragmentation (1 or 2).
        progress_callback: Optional callable(int) for percent progress.

    Returns:
        DataFrame with columns: Mol_A_idx, Mol_B_idx, Mol_A, Mol_B,
        Context, R_A, R_B, and optionally Property_A, Property_B, Delta.
    """
    # Step 1: Fragment all molecules and index by context (large fragment)
    context_index = defaultdict(list)  # canonical_context -> [(mol_idx, r_group, smiles)]
    total = len(smiles_series)

    for i, smiles in enumerate(smiles_series):
        if pd.isna(smiles) or not str(smiles).strip():
            continue
        mol = Chem.MolFromSmiles(str(smiles))
        if mol is None:
            continue

        try:
            frags = rdMMPA.FragmentMol(mol, maxCuts=max_cuts, resultsAsMols=False)
        except Exception:
            continue

        for core_smi, chains in frags:
            if max_cuts == 1:
                # For 1-cut: core is empty, chains = "context.rgroup"
                parts = chains.split(".")
                if len(parts) != 2:
                    continue
                context, rgroup = parts
            else:
                # For 2-cut: core is the context, chains = "rgroup1.rgroup2"
                if not core_smi:
                    # Sometimes 2-cut also has empty core with 3-part chains
                    parts = chains.split(".")
                    if len(parts) == 2:
                        context, rgroup = parts
                    else:
                        continue
                else:
                    context = core_smi
                    rgroup = chains

            # Canonicalize the context and filter by size
            ctx_mol = Chem.MolFromSmiles(context)
            if ctx_mol is None:
                continue
            # Skip contexts that are too small (e.g. just "Cl" or "C")
            ctx_heavy = ctx_mol.GetNumHeavyAtoms()
            if ctx_heavy < min_context_atoms:
                continue
            # Skip R-groups that are too large (the "variable" part should be small)
            rg_mol = Chem.MolFromSmiles(rgroup)
            if rg_mol is not None and rg_mol.GetNumHeavyAtoms() > max_rgroup_atoms:
                continue
            ctx_canon = Chem.MolToSmiles(ctx_mol)
            context_index[ctx_canon].append((i, rgroup, str(smiles)))

        if progress_callback and (i + 1) % 50 == 0:
            progress_callback(int((i + 1) / total * 60))

    if progress_callback:
        progress_callback(60)

    # Step 2: Build pairs from molecules sharing the same context
    pairs = []
    for context, members in context_index.items():
        if len(members) < 2:
            continue

        # Deduplicate by mol_idx (same molecule can appear multiple times
        # if it has the same context from different fragmentations)
        seen = {}
        for mol_idx, rgroup, smi in members:
            if mol_idx not in seen:
                seen[mol_idx] = (rgroup, smi)

        unique_members = list(seen.items())
        if len(unique_members) < 2:
            continue

        # Limit pairwise to avoid combinatorial explosion
        member_list = unique_members[:50]
        for a_idx in range(len(member_list)):
            for b_idx in range(a_idx + 1, len(member_list)):
                mol_a_idx, (r_a, smi_a) = member_list[a_idx]
                mol_b_idx, (r_b, smi_b) = member_list[b_idx]

                if r_a == r_b:
                    continue

                row = {
                    'Mol_A_idx': mol_a_idx,
                    'Mol_B_idx': mol_b_idx,
                    'Mol_A': smi_a,
                    'Mol_B': smi_b,
                    'Context': context,
                    'R_A': r_a,
                    'R_B': r_b,
                }

                if property_col is not None:
                    prop_a = property_col.iloc[mol_a_idx]
                    prop_b = property_col.iloc[mol_b_idx]
                    row['Property_A'] = prop_a
                    row['Property_B'] = prop_b
                    if pd.notna(prop_a) and pd.notna(prop_b):
                        row['Delta'] = round(float(prop_b) - float(prop_a), 4)
                    else:
                        row['Delta'] = np.nan

                # Extra data columns
                if data_cols:
                    for col_name, series in data_cols.items():
                        row[f'{col_name}_A'] = series.iloc[mol_a_idx]
                        row[f'{col_name}_B'] = series.iloc[mol_b_idx]

                pairs.append(row)

    if progress_callback:
        progress_callback(100)

    if not pairs:
        return pd.DataFrame()

    return pd.DataFrame(pairs)
