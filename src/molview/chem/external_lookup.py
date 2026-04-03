"""PubChem compound lookup via PUG REST API."""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from typing import Optional


_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Properties to retrieve
_DEFAULT_PROPERTIES = [
    "MolecularFormula", "MolecularWeight", "XLogP", "TPSA",
    "HBondDonorCount", "HBondAcceptorCount", "RotatableBondCount",
    "IUPACName", "CanonicalSMILES", "CID",
]


def lookup_by_smiles(smiles: str, properties: list[str] | None = None) -> Optional[dict]:
    """Look up a compound on PubChem by SMILES. Returns a dict of properties or None."""
    if properties is None:
        properties = _DEFAULT_PROPERTIES
    prop_str = ",".join(properties)
    encoded = urllib.parse.quote(smiles, safe="")
    url = f"{_PUBCHEM_BASE}/compound/smiles/{encoded}/property/{prop_str}/JSON"
    return _fetch(url)


def lookup_by_name(name: str, properties: list[str] | None = None) -> Optional[dict]:
    """Look up a compound on PubChem by name. Returns a dict of properties or None."""
    if properties is None:
        properties = _DEFAULT_PROPERTIES
    prop_str = ",".join(properties)
    encoded = urllib.parse.quote(name, safe="")
    url = f"{_PUBCHEM_BASE}/compound/name/{encoded}/property/{prop_str}/JSON"
    return _fetch(url)


def lookup_by_cid(cid: int, properties: list[str] | None = None) -> Optional[dict]:
    """Look up a compound on PubChem by CID. Returns a dict of properties or None."""
    if properties is None:
        properties = _DEFAULT_PROPERTIES
    prop_str = ",".join(properties)
    url = f"{_PUBCHEM_BASE}/compound/cid/{cid}/property/{prop_str}/JSON"
    return _fetch(url)


def batch_lookup_by_smiles(
    smiles_list: list[str],
    properties: list[str] | None = None,
    progress_callback=None,
) -> list[Optional[dict]]:
    """Look up multiple compounds by SMILES. Returns list of dicts (None for failures)."""
    results = []
    total = len(smiles_list)
    for i, smiles in enumerate(smiles_list):
        if smiles and str(smiles).strip():
            try:
                results.append(lookup_by_smiles(str(smiles), properties))
            except Exception:
                results.append(None)
        else:
            results.append(None)

        if progress_callback and (i + 1) % 5 == 0:
            progress_callback(int((i + 1) / total * 100))

    if progress_callback:
        progress_callback(100)
    return results


def _fetch(url: str) -> Optional[dict]:
    """Fetch JSON from PubChem API. Returns the first property table entry or None."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        table = data.get("PropertyTable", {}).get("Properties", [])
        if table:
            return table[0]
    except Exception:
        pass
    return None
