from __future__ import annotations

import math
import pandas as pd
import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors


# ── LogD estimation via SMARTS-based pKa lookup + Henderson-Hasselbalch ──

# Common ionizable groups with approximate pKa values.
# (SMARTS pattern, pKa, type: "acid" loses H to become anionic, "base" gains H to become cationic)
_IONIZABLE_GROUPS = [
    # Carboxylic acids
    ("[CX3](=O)[OX2H1]", 4.0, "acid"),
    # Sulfonamides (acidic NH)
    ("[#16X4](=[OX1])(=[OX1])([#7H1])", 10.0, "acid"),
    # Phenols
    ("[OX2H1]c1ccccc1", 10.0, "acid"),
    # Tetrazoles (bioisostere of carboxylic acid)
    ("[nH]1nnnc1", 4.9, "acid"),
    # Phosphonic acid
    ("[PX4](=O)([OX2H1])", 1.5, "acid"),
    # Primary aliphatic amines
    ("[NX3H2;!$(N=*);!$(N#*);!$(Nc)]", 10.0, "base"),
    # Secondary aliphatic amines
    ("[NX3H1;!$(N=*);!$(N#*);!$(Nc)]([CX4])([CX4])", 10.5, "base"),
    # Tertiary aliphatic amines
    ("[NX3H0;!$(N=*);!$(N#*);!$(Nc)]([CX4])([CX4])([CX4])", 9.8, "base"),
    # Primary aromatic amines (anilines)
    ("[NX3H2]c", 4.6, "base"),
    # Imidazole
    ("[nH]1ccnc1", 6.8, "base"),
    # Pyridine
    ("n1ccccc1", 5.2, "base"),
    # Guanidines
    ("[NX3H2]C(=[NH])N", 12.5, "base"),
    # Amidines
    ("[NX3H2]C(=[NH])[!N]", 11.0, "base"),
]

# Pre-compile SMARTS
_IONIZABLE_PATTERNS = []
for smarts, pka, ion_type in _IONIZABLE_GROUPS:
    pat = Chem.MolFromSmarts(smarts)
    if pat is not None:
        _IONIZABLE_PATTERNS.append((pat, pka, ion_type))


def _estimate_logd(mol, ph: float = 7.4) -> float:
    """Estimate LogD at a given pH using Henderson-Hasselbalch approximation.

    For acids:  LogD = LogP - log10(1 + 10^(pH - pKa))
    For bases:  LogD = LogP - log10(1 + 10^(pKa - pH))

    When multiple ionizable groups are present, the total correction is the sum
    of individual corrections (independent ionization approximation).
    """
    logp = Descriptors.MolLogP(mol)
    correction = 0.0

    for pat, pka, ion_type in _IONIZABLE_PATTERNS:
        matches = mol.GetSubstructMatches(pat)
        n = len(matches)
        if n == 0:
            continue
        if ion_type == "acid":
            correction += n * math.log10(1 + 10 ** (ph - pka))
        else:  # base
            correction += n * math.log10(1 + 10 ** (pka - ph))

    return round(logp - correction, 3)


# Default pH for LogD calculation
_logd_ph = 7.4


def set_logd_ph(ph: float):
    """Set the pH used for LogD calculations."""
    global _logd_ph
    _logd_ph = ph


def get_logd_ph() -> float:
    return _logd_ph


# ── Property registry ──

PROPERTY_REGISTRY = {
    "MW": ("Molecular Weight", lambda mol: round(Descriptors.MolWt(mol), 2)),
    "MF": ("Molecular Formula", lambda mol: rdMolDescriptors.CalcMolFormula(mol)),
    "LogP": ("Crippen LogP", lambda mol: round(Descriptors.MolLogP(mol), 3)),
    "LogD": ("LogD (pH-dependent)", lambda mol: _estimate_logd(mol, _logd_ph)),
    "TPSA": ("Topological PSA", lambda mol: round(Descriptors.TPSA(mol), 2)),
    "RotBonds": ("Rotatable Bonds", lambda mol: Descriptors.NumRotatableBonds(mol)),
    "HBD": ("H-Bond Donors", lambda mol: Descriptors.NumHDonors(mol)),
    "HBA": ("H-Bond Acceptors", lambda mol: Descriptors.NumHAcceptors(mol)),
}


def calculate_properties(
    smiles_series: pd.Series,
    property_names: list[str],
    progress_callback=None,
) -> dict[str, list]:
    """Calculate molecular properties from a SMILES series.

    Returns a dict mapping property name to list of values (one per row).
    """
    results = {name: [] for name in property_names}
    total = len(smiles_series)

    for i, smiles in enumerate(smiles_series):
        mol = None
        if pd.notna(smiles) and str(smiles).strip():
            mol = Chem.MolFromSmiles(str(smiles))

        for name in property_names:
            if mol is not None and name in PROPERTY_REGISTRY:
                try:
                    _, func = PROPERTY_REGISTRY[name]
                    results[name].append(func(mol))
                except Exception:
                    results[name].append(np.nan)
            else:
                results[name].append(np.nan)

        if progress_callback and (i + 1) % 50 == 0:
            progress_callback(int((i + 1) / total * 100))

    if progress_callback:
        progress_callback(100)

    return results
