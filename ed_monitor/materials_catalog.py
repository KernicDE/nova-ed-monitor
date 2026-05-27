"""Complete Elite Dangerous material catalogue for the material tracker."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialInfo:
    name: str
    grade: int
    cap: int


# Caps per grade (from Elite Dangerous wiki)
# G1=300, G2=250, G3=200, G4=150, G5=100
# Raw materials only go up to G4.
_RAW_CAP = {1: 300, 2: 250, 3: 200, 4: 150}
_MFG_ENC_CAP = {1: 300, 2: 250, 3: 200, 4: 150, 5: 100}

RAW_CATEGORIES: list[tuple[str, list[MaterialInfo]]] = [
    ("Raw 1", [
        MaterialInfo("Carbon", 1, _RAW_CAP[1]),
        MaterialInfo("Vanadium", 2, _RAW_CAP[2]),
        MaterialInfo("Niobium", 3, _RAW_CAP[3]),
        MaterialInfo("Yttrium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 2", [
        MaterialInfo("Phosphorus", 1, _RAW_CAP[1]),
        MaterialInfo("Chromium", 2, _RAW_CAP[2]),
        MaterialInfo("Molybdenum", 3, _RAW_CAP[3]),
        MaterialInfo("Technetium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 3", [
        MaterialInfo("Sulphur", 1, _RAW_CAP[1]),
        MaterialInfo("Manganese", 2, _RAW_CAP[2]),
        MaterialInfo("Cadmium", 3, _RAW_CAP[3]),
        MaterialInfo("Ruthenium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 4", [
        MaterialInfo("Iron", 1, _RAW_CAP[1]),
        MaterialInfo("Zinc", 2, _RAW_CAP[2]),
        MaterialInfo("Tin", 3, _RAW_CAP[3]),
        MaterialInfo("Selenium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 5", [
        MaterialInfo("Nickel", 1, _RAW_CAP[1]),
        MaterialInfo("Germanium", 2, _RAW_CAP[2]),
        MaterialInfo("Tungsten", 3, _RAW_CAP[3]),
        MaterialInfo("Tellurium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 6", [
        MaterialInfo("Rhenium", 1, _RAW_CAP[1]),
        MaterialInfo("Arsenic", 2, _RAW_CAP[2]),
        MaterialInfo("Mercury", 3, _RAW_CAP[3]),
        MaterialInfo("Polonium", 4, _RAW_CAP[4]),
    ]),
    ("Raw 7", [
        MaterialInfo("Lead", 1, _RAW_CAP[1]),
        MaterialInfo("Zirconium", 2, _RAW_CAP[2]),
        MaterialInfo("Boron", 3, _RAW_CAP[3]),
        MaterialInfo("Antimony", 4, _RAW_CAP[4]),
    ]),
]

MANUFACTURED_CATEGORIES: list[tuple[str, list[MaterialInfo]]] = [
    ("Chemical", [
        MaterialInfo("Chemical Storage Units", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Chemical Processors", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Chemical Distillery", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Chemical Manipulators", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Pharmaceutical Isolators", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Thermic", [
        MaterialInfo("Tempered Alloys", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Heat Resistant Ceramics", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Precipitated Alloys", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Thermic Alloys", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Military Grade Alloys", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Heat", [
        MaterialInfo("Heat Conduction Wiring", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Heat Dispersion Plate", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Heat Exchangers", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Heat Vanes", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Proto Heat Radiators", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Conductive", [
        MaterialInfo("Basic Conductors", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Conductive Components", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Conductive Ceramics", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Conductive Polymers", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Biotech Conductors", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Mechanical", [
        MaterialInfo("Mechanical Scrap", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Mechanical Equipment", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Mechanical Components", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Configurable Components", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Improvised Components", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Capacitors", [
        MaterialInfo("Grid Resistors", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Hybrid Capacitors", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Electrochemical Arrays", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Polymer Capacitors", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Military Supercapacitors", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Shielding", [
        MaterialInfo("Worn Shield Emitters", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Shield Emitters", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Shielding Sensors", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Compound Shielding", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Imperial Shielding", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Composite", [
        MaterialInfo("Compact Composites", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Filament Composites", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("High Density Composites", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Proprietary Composites", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Core Dynamics Composites", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Crystals", [
        MaterialInfo("Crystal Shards", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Flawed Focus Crystals", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Focus Crystals", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Refined Focus Crystals", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Exquisite Focus Crystals", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Alloys", [
        MaterialInfo("Salvaged Alloys", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Galvanising Alloys", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Phase Alloys", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Proto Light Alloys", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Proto Radiolic Alloys", 5, _MFG_ENC_CAP[5]),
    ]),
]

ENCODED_CATEGORIES: list[tuple[str, list[MaterialInfo]]] = [
    ("Emission Data", [
        MaterialInfo("Exceptional Scrambled Emission Data", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Irregular Emission Data", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Unexpected Emission Data", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Decoded Emission Data", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Abnormal Compact Emissions Data", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Wake Scans", [
        MaterialInfo("Atypical Disrupted Wake Echoes", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Anomalous FSD Telemetry", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Strange Wake Solutions", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Eccentric Hyperspace Trajectories", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Datamined Wake Exceptions", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Shield Data", [
        MaterialInfo("Distorted Shield Cycle Recordings", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Inconsistent Shield Soak Analysis", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Untypical Shield Scans", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Aberrant Shield Pattern Analysis", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Peculiar Shield Frequency Data", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Encryption", [
        MaterialInfo("Unusual Encrypted Files", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Tagged Encryption Codes", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Open Symmetric Keys", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Atypical Encryption Archives", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Adaptive Encryptors Capture", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Data Archives", [
        MaterialInfo("Anomalous Bulk Scan Data", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Unidentified Scan Archives", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Classified Scan Databanks", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Divergent Scan Data", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Classified Scan Fragment", 5, _MFG_ENC_CAP[5]),
    ]),
    ("Firmware", [
        MaterialInfo("Specialised Legacy Firmware", 1, _MFG_ENC_CAP[1]),
        MaterialInfo("Modified Consumer Firmware", 2, _MFG_ENC_CAP[2]),
        MaterialInfo("Cracked Industrial Firmware", 3, _MFG_ENC_CAP[3]),
        MaterialInfo("Security Firmware Patch", 4, _MFG_ENC_CAP[4]),
        MaterialInfo("Modified Embedded Firmware", 5, _MFG_ENC_CAP[5]),
    ]),
]

ALL_CATEGORIES = [
    ("RAW", RAW_CATEGORIES),
    ("MANUFACTURED", MANUFACTURED_CATEGORIES),
    ("ENCODED", ENCODED_CATEGORIES),
]

# Flat lists for backward compatibility (e.g. status.py zero-fill)
RAW_MATERIALS: list[MaterialInfo] = []
MANUFACTURED_MATERIALS: list[MaterialInfo] = []
ENCODED_MATERIALS: list[MaterialInfo] = []
for _cat_name, _mats in RAW_CATEGORIES:
    RAW_MATERIALS.extend(_mats)
for _cat_name, _mats in MANUFACTURED_CATEGORIES:
    MANUFACTURED_MATERIALS.extend(_mats)
for _cat_name, _mats in ENCODED_CATEGORIES:
    ENCODED_MATERIALS.extend(_mats)

# Flat lookup by normalized name
_ALL_MATERIALS: list[MaterialInfo] = []
_ALL_MATERIALS.extend(RAW_MATERIALS)
_ALL_MATERIALS.extend(MANUFACTURED_MATERIALS)
_ALL_MATERIALS.extend(ENCODED_MATERIALS)

_MATERIAL_BY_NAME: dict[str, MaterialInfo] = {
    m.name.lower(): m for m in _ALL_MATERIALS
}

# Compact lookup: catalogue names with all spaces/underscores removed
# (e.g. "chemicalstorageunits" → "Chemical Storage Units")
_MATERIAL_BY_COMPACT_NAME: dict[str, MaterialInfo] = {
    m.name.lower().replace(" ", "").replace("_", ""): m for m in _ALL_MATERIALS
}


def lookup(name: str) -> MaterialInfo | None:
    """Return MaterialInfo for a given material name, or None if unknown."""
    return _MATERIAL_BY_NAME.get(name.lower())


# Elite's internal material names are CamelCase (e.g. ChemicalStorageUnits)
# or wrapped in $..._name; (e.g. $chemicalstorageunits_name;).
# The catalogue stores Title Case with spaces ("Chemical Storage Units").
_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _normalize_material_name(name: str) -> str:
    """Convert internal Elite symbolic names to catalogue-style Title Case."""
    if not name:
        return name
    # Strip $..._name; wrapper
    if name.startswith("$") and "_name;" in name:
        name = name[1:].replace("_name;", "")
    # CamelCase → spaces (e.g. ChemicalStorageUnits → Chemical Storage Units)
    name = _CAMEL_RE.sub(" ", name)
    return name


def lookup_fuzzy(name: str) -> MaterialInfo | None:
    """Lookup with normalization for internal Elite symbolic names.

    Tries, in order:
    1. Exact match (case-insensitive)
    2. After stripping $..._name; and expanding CamelCase
    3. Title-cased variant of the normalized name
    4. Compact name (all spaces/underscores removed)
    """
    if not name:
        return None
    # 1. Exact / direct lookup
    info = lookup(name)
    if info:
        return info
    # 2. Normalized (strip wrapper + CamelCase → spaces)
    normalized = _normalize_material_name(name)
    info = lookup(normalized)
    if info:
        return info
    # 3. Title-cased normalized (e.g. "chemical storage units" → "Chemical Storage Units")
    info = lookup(normalized.title())
    if info:
        return info
    # 4. Compact match (e.g. "chemicalstorageunits" or "$chemicalstorageunits_name;")
    compact = _normalize_material_name(name).lower().replace(" ", "").replace("_", "")
    info = _MATERIAL_BY_COMPACT_NAME.get(compact)
    if info:
        return info
    return None


def cap_for(name: str) -> int:
    """Return storage cap for a material name. Defaults to 100 if unknown."""
    info = lookup(name)
    return info.cap if info else 100


def grade_for(name: str) -> int:
    """Return grade for a material name. Defaults to 1 if unknown."""
    info = lookup(name)
    return info.grade if info else 1
