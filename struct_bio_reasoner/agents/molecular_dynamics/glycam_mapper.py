"""
glycam_mapper.py

Core library for converting Chai-predicted glycoprotein PDB files to
GLYCAM/AMBER convention, ready for AMBER molecular dynamics preparation.

Conversion steps
----------------
1. Parse PDB atoms and residues.
2. Detect glycosidic bonds from inter-residue atomic distances.
3. Determine anomeric configuration from glycan-tree topology.
4. Assign GLYCAM 3-letter residue codes (linkage + sugar letter + anomer).
5. Rename atoms for N-acetyl sugars (C7→C2N, C8→CME, O7→O2N).
6. Rename protein ASN residues linked to glycans → NLN.
7. Write a GLYCAM-formatted PDB and a tleap input script.

Public API
----------
    from struct_bio_reasoner.agents.molecular_dynamics.glycam_mapper import GlycanConverter

    converter = GlycanConverter()
    result = converter.convert_pdb("fold.pdb", output_dir="prep/")
    # result['glycam_pdb']   → Path to renamed PDB
    # result['leap_script']  → Path to tleap .in script
"""

import math
import sys
import logging
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PDB residue names Chai uses for sugars
SUGAR_RESNAMES = {"NAG", "FUC", "MAN", "BMA", "GAL", "SIA", "GLC", "XYS"}

# Chai residue name → (GLYCAM one-letter code, D/L config)
SUGAR_TO_GLYCAM_LETTER: Dict[str, Tuple[str, str]] = {
    "NAG": ("Y", "D"),   # GlcNAc
    "NDG": ("Y", "D"),   # GlcNAc alternate
    "FUC": ("F", "L"),   # Fucose  (L-config → lowercase 'f')
    "MAN": ("M", "D"),   # Mannose
    "BMA": ("M", "D"),   # β-Mannose (anomer determined from geometry/tree)
    "GAL": ("L", "D"),   # Galactose
    "GLC": ("G", "D"),   # Glucose
    "SIA": ("S", "D"),   # Sialic acid
    "BGC": ("G", "D"),   # β-Glucose
    "A2G": ("Y", "D"),   # GlcNAc alternate
}

# Occupied hydroxyl positions (children) → GLYCAM linkage prefix character
LINKAGE_CODE: Dict[frozenset, str] = {
    frozenset():          "0",   # terminal
    frozenset({2}):       "2",
    frozenset({3}):       "3",
    frozenset({4}):       "4",
    frozenset({6}):       "6",
    frozenset({2, 3}):    "Z",
    frozenset({2, 4}):    "D",
    frozenset({2, 6}):    "U",
    frozenset({3, 4}):    "E",
    frozenset({3, 6}):    "V",
    frozenset({4, 6}):    "U",
    frozenset({2, 3, 4}): "H",
    frozenset({2, 3, 6}): "S",
    frozenset({2, 4, 6}): "T",
    frozenset({3, 4, 6}): "Q",
    frozenset({2, 3, 4, 6}): "W",
}

# Atom name remapping for N-acetyl sugars
NACETYL_ATOM_RENAME: Dict[str, str] = {
    "C7": "C2N",
    "C8": "CME",
    "O7": "O2N",
}

# Distance thresholds (Angstroms)
BOND_CUTOFF = 1.85
PROTEIN_SUGAR_CUTOFF = 2.0
DISULFIDE_CUTOFF = 2.1   # S–S bond ~2.05 Å; allow small tolerance


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Atom:
    serial: int
    name: str
    resname: str
    chain: str
    resseq: int
    x: float
    y: float
    z: float
    occupancy: float
    bfactor: float
    element: str
    record: str   # "ATOM" or "HETATM"


@dataclass
class Residue:
    resname: str
    chain: str
    resseq: int
    atoms: dict = field(default_factory=dict)  # atom_name → Atom

    @property
    def key(self) -> tuple:
        return (self.chain, self.resseq)

    def get_coord(self, atom_name: str) -> Optional[tuple]:
        a = self.atoms.get(atom_name)
        return (a.x, a.y, a.z) if a else None

    @property
    def is_sugar(self) -> bool:
        return self.resname in SUGAR_RESNAMES or self.resname in SUGAR_TO_GLYCAM_LETTER


@dataclass
class GlycosidicBond:
    child_key: tuple          # (chain, resseq) of the sugar donating C1
    parent_key: tuple         # (chain, resseq) of the parent receiving the bond
    child_atom: str           # atom on child (always "C1")
    parent_atom: str          # atom on parent (e.g. "O4", "O6", "ND2")
    linkage_position: Optional[int]   # carbon position on parent, or None for protein link
    distance: float


@dataclass
class DisulfideBond:
    """A disulfide bond between two CYS residues (SG–SG)."""
    res1_key: tuple   # (chain, resseq) of the first cysteine
    res2_key: tuple   # (chain, resseq) of the second cysteine
    distance: float   # SG–SG distance in Å


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(a: tuple, b: tuple) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def _dihedral_angle(p1, p2, p3, p4) -> float:
    """Compute dihedral angle in degrees from four (x,y,z) tuples."""
    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    def sub(a, b):
        return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
    def dot(a, b):
        return sum(ai*bi for ai, bi in zip(a, b))
    def norm(a):
        return math.sqrt(dot(a, a))

    b1, b2, b3 = sub(p2, p1), sub(p3, p2), sub(p4, p3)
    n1, n2 = cross(b1, b2), cross(b2, b3)
    n1n, n2n = norm(n1), norm(n2)
    if n1n < 1e-10 or n2n < 1e-10:
        return 0.0
    cos_a = max(-1.0, min(1.0, dot(n1, n2) / (n1n * n2n)))
    angle = math.degrees(math.acos(cos_a))
    if dot(n1, b3) < 0:
        angle = -angle
    return angle


def _default_anomer(resname: str) -> str:
    """Biological defaults for common N-glycan sugars."""
    return {
        "NAG": "B", "NDG": "B", "A2G": "B",
        "FUC": "A",
        "MAN": "A", "BMA": "B",
        "GAL": "B",
        "GLC": "B",
        "SIA": "A",
    }.get(resname, "B")


def _determine_anomers_from_tree(
    residues: dict,
    bonds: List[GlycosidicBond],
) -> Dict[tuple, str]:
    """
    Assign anomeric configuration using glycan-tree topology.
    Much more reliable than geometry for predicted structures.
    """
    child_bond: Dict[tuple, GlycosidicBond] = {}
    for b in bonds:
        child_bond[b.child_key] = b

    anomers: Dict[tuple, str] = {}

    for key, res in residues.items():
        if not res.is_sugar:
            continue

        bond = child_bond.get(key)
        rn = res.resname

        if bond is None:
            anomers[key] = _default_anomer(rn)
            continue

        parent = residues.get(bond.parent_key)
        if parent is None:
            anomers[key] = _default_anomer(rn)
            continue

        parent_rn = parent.resname

        if rn in ("NAG", "NDG", "A2G"):
            # GlcNAc is almost always β in N-glycans
            anomers[key] = "B"
        elif rn == "FUC":
            # Fucose is always α-L in mammalian N-glycans
            anomers[key] = "A"
        elif rn in ("MAN", "BMA"):
            if parent_rn in ("NAG", "NDG", "A2G"):
                anomers[key] = "B"   # core mannose → β
            else:
                anomers[key] = "A"   # arm mannose → α
        elif rn == "GAL":
            anomers[key] = "B"
        elif rn == "SIA":
            anomers[key] = "A"
        else:
            anomers[key] = _default_anomer(rn)

    return anomers


# ---------------------------------------------------------------------------
# PDB parsing
# ---------------------------------------------------------------------------

def _parse_pdb(filepath: Path):
    """Parse PDB into (list[Atom], dict[(chain,resseq) → Residue])."""
    atoms: List[Atom] = []
    residues: Dict[tuple, Residue] = {}

    with open(filepath) as fh:
        for line in fh:
            if not (line.startswith("ATOM") or line.startswith("HETATM")):
                continue
            record  = line[0:6].strip()
            serial  = int(line[6:11])
            name    = line[12:16].strip()
            resname = line[17:20].strip()
            chain   = line[21].strip()
            resseq  = int(line[22:26])
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            try:    occ = float(line[54:60])
            except: occ = 1.0
            try:    bf = float(line[60:66])
            except: bf = 0.0
            try:    element = line[76:78].strip()
            except: element = name[0]

            atom = Atom(serial, name, resname, chain, resseq,
                        x, y, z, occ, bf, element, record)
            atoms.append(atom)
            key = (chain, resseq)
            if key not in residues:
                residues[key] = Residue(resname, chain, resseq)
            residues[key].atoms[name] = atom

    return atoms, residues


# ---------------------------------------------------------------------------
# Bond detection
# ---------------------------------------------------------------------------

def _detect_glycosidic_bonds(
    residues: Dict[tuple, Residue],
    bond_cutoff: float = BOND_CUTOFF,
    protein_sugar_cutoff: float = PROTEIN_SUGAR_CUTOFF,
) -> List[GlycosidicBond]:
    """
    Find all glycosidic bonds by distance: C1–O (sugar–sugar) and
    C1–ND2 (ASN–sugar protein links).  Returns the shortest bond per C1.
    """
    bonds: List[GlycosidicBond] = []
    sugar_residues = {k: v for k, v in residues.items() if v.is_sugar}

    for child_key, child_res in sugar_residues.items():
        c1 = child_res.get_coord("C1")
        if c1 is None:
            continue

        for parent_key, parent_res in residues.items():
            if parent_key == child_key:
                continue

            if parent_res.is_sugar:
                for aname, atom in parent_res.atoms.items():
                    if not aname.startswith("O"):
                        continue
                    if aname in ("O5", "O2N", "O7"):   # ring / N-acetyl oxygens
                        continue
                    coord = (atom.x, atom.y, atom.z)
                    d = _dist(c1, coord)
                    if d < bond_cutoff:
                        try:
                            pos = int(aname[1])
                        except (ValueError, IndexError):
                            pos = None
                        bonds.append(GlycosidicBond(
                            child_key=child_key, parent_key=parent_key,
                            child_atom="C1", parent_atom=aname,
                            linkage_position=pos, distance=d,
                        ))

            elif parent_res.resname in ("ASN", "NLN"):
                nd2 = parent_res.get_coord("ND2")
                if nd2 is not None:
                    d = _dist(c1, nd2)
                    if d < protein_sugar_cutoff:
                        bonds.append(GlycosidicBond(
                            child_key=child_key, parent_key=parent_key,
                            child_atom="C1", parent_atom="ND2",
                            linkage_position=None, distance=d,
                        ))

    # Keep only shortest bond per C1
    best: Dict[tuple, GlycosidicBond] = {}
    for b in bonds:
        if b.child_key not in best or b.distance < best[b.child_key].distance:
            best[b.child_key] = b
    return list(best.values())


def _detect_disulfide_bonds(
    residues: Dict[tuple, Residue],
    cutoff: float = DISULFIDE_CUTOFF,
) -> List[DisulfideBond]:
    """
    Detect disulfide bonds by finding CYS–CYS pairs whose SG atoms are
    within *cutoff* Å of each other.

    Parameters
    ----------
    residues :
        Residue dict as returned by ``_parse_pdb``.
    cutoff :
        SG–SG distance threshold in Å.  Defaults to ``DISULFIDE_CUTOFF``
        (2.1 Å), which is generous enough to catch all genuine disulfides
        while excluding non-bonded cysteine pairs (typically > 4 Å).

    Returns
    -------
    List of :class:`DisulfideBond` objects, one per detected pair.
    """
    cys_keys = [
        k for k, v in residues.items()
        if v.resname in ("CYS", "CYX")
    ]
    bonds: List[DisulfideBond] = []
    for i, k1 in enumerate(cys_keys):
        sg1 = residues[k1].get_coord("SG")
        if sg1 is None:
            continue
        for k2 in cys_keys[i + 1:]:
            sg2 = residues[k2].get_coord("SG")
            if sg2 is None:
                continue
            d = _dist(sg1, sg2)
            if d < cutoff:
                bonds.append(DisulfideBond(res1_key=k1, res2_key=k2, distance=d))
                logger.debug(
                    "Disulfide detected: %s%d – %s%d  (%.3f Å)",
                    k1[0], k1[1], k2[0], k2[1], d,
                )
    return bonds


# ---------------------------------------------------------------------------
# GLYCAM name assignment
# ---------------------------------------------------------------------------

def _assign_glycam_names(
    residues: Dict[tuple, Residue],
    bonds: List[GlycosidicBond],
):
    """
    Return (glycam_names, nln_residues).
      glycam_names  : dict (chain, resseq) → 3-char GLYCAM name
      nln_residues  : set of (chain, resseq) for protein ASNs → NLN
    """
    parent_substitutions: Dict[tuple, set] = defaultdict(set)
    protein_sugar_links: Dict[tuple, tuple] = {}

    for b in bonds:
        if b.linkage_position is not None:
            parent_substitutions[b.parent_key].add(b.linkage_position)
        else:
            protein_sugar_links[b.parent_key] = b.child_key

    anomers = _determine_anomers_from_tree(residues, bonds)
    glycam_names: Dict[tuple, str] = {}

    for key, res in residues.items():
        if not res.is_sugar:
            continue
        rn = res.resname
        if rn not in SUGAR_TO_GLYCAM_LETTER:
            logger.warning("Unknown sugar %s at %s — skipping", rn, key)
            continue

        letter, config = SUGAR_TO_GLYCAM_LETTER[rn]
        anomer = anomers.get(key, _default_anomer(rn))

        positions = parent_substitutions.get(key, set())
        pos_key = frozenset(positions)
        if pos_key in LINKAGE_CODE:
            link_code = LINKAGE_CODE[pos_key]
        else:
            logger.warning("Unknown linkage %s for %s at %s — using '0'", positions, rn, key)
            link_code = "0"

        sugar_char = letter.lower() if config == "L" else letter.upper()
        glycam_names[key] = f"{link_code}{sugar_char}{anomer}"

    return glycam_names, set(protein_sugar_links.keys())


# ---------------------------------------------------------------------------
# PDB rewriting
# ---------------------------------------------------------------------------

def _rewrite_pdb(
    atoms: List[Atom],
    glycam_names: Dict[tuple, str],
    nln_residues: set,
    output_path: Path,
    cyx_residues: set = frozenset(),
) -> Path:
    """Write a new PDB file with GLYCAM residue/atom names.

    Parameters
    ----------
    atoms :
        Flat list of ``Atom`` objects from ``_parse_pdb``.
    glycam_names :
        Mapping (chain, resseq) → GLYCAM 3-letter code for sugar residues.
    nln_residues :
        Set of (chain, resseq) for ASN residues renamed to NLN.
    output_path :
        Destination file path.
    cyx_residues :
        Set of (chain, resseq) for CYS residues involved in disulfide bonds;
        these are written as CYX so that AMBER knows to apply the disulfide
        cross-link parameters.
    """
    lines_out = []
    for atom in atoms:
        key = (atom.chain, atom.resseq)
        new_resname = atom.resname
        new_atom_name = atom.name

        if key in glycam_names:
            new_resname = glycam_names[key]
            if atom.resname in ("NAG", "NDG", "A2G"):
                new_atom_name = NACETYL_ATOM_RENAME.get(atom.name, atom.name)
        elif key in nln_residues:
            new_resname = "NLN"
        elif key in cyx_residues and atom.resname == "CYS":
            new_resname = "CYX"

        name_field = f" {new_atom_name:<3s}" if len(new_atom_name) < 4 else f"{new_atom_name:<4s}"
        resname_field = f"{new_resname:>3s}"

        line = (f"{atom.record:<6s}{atom.serial:5d} {name_field} {resname_field} "
                f"{atom.chain:1s}{atom.resseq:4d}    "
                f"{atom.x:8.3f}{atom.y:8.3f}{atom.z:8.3f}"
                f"{atom.occupancy:6.2f}{atom.bfactor:6.2f}          "
                f"{atom.element:>2s}")
        lines_out.append((key, line))

    # Insert TER records between chain boundaries and sugar-protein boundaries
    final_lines = []
    prev_key = None
    for key, line in lines_out:
        if prev_key is not None and key != prev_key:
            prev_chain = prev_key[0]
            cur_chain = key[0]
            if prev_chain != cur_chain:
                final_lines.append("TER")
            elif key in glycam_names or prev_key in glycam_names:
                final_lines.append("TER")
        final_lines.append(line)
        prev_key = key

    final_lines.extend(["TER", "END"])
    output_path.write_text("\n".join(final_lines) + "\n")
    return output_path


# ---------------------------------------------------------------------------
# tleap script generation
# ---------------------------------------------------------------------------

def _format_bond_commands(
    residues: Dict[tuple, Residue],
    bonds: List[GlycosidicBond],
    mol_name: str = "prot",
) -> List[str]:
    """
    Return a list of tleap ``bond`` command strings for all detected bonds.

    The molecule name (``mol_name``) must match the variable name used when
    the PDB is loaded in the tleap script — ``prot`` for
    ``ImplicitSolvent`` and ``PROT`` for ``ExplicitSolvent`` in the
    ``molecular-simulations`` library.

    Parameters
    ----------
    residues :
        Residue dict as returned by ``_parse_pdb``.
    bonds :
        Detected glycosidic bonds from ``_detect_glycosidic_bonds``.
    mol_name :
        tleap molecule variable name.  Defaults to ``"prot"``.

    Returns
    -------
    List of strings, each a complete tleap bond command, e.g.::

        ["bond prot.42.ND2 prot.43.C1",
         "bond prot.43.C1 prot.44.O4"]
    """
    seen: List[tuple] = []
    for res in sorted(residues.values(), key=lambda r: (r.chain, r.resseq)):
        if res.key not in seen:
            seen.append(res.key)
    res_index = {key: i + 1 for i, key in enumerate(seen)}

    commands: List[str] = []
    for b in bonds:
        ci = res_index.get(b.child_key)
        pi = res_index.get(b.parent_key)
        if ci is None or pi is None:
            logger.warning("Cannot find residue index for bond %s — skipping", b)
            continue
        if b.linkage_position is None:
            # protein–sugar bond  (parent atom = ND2, child atom = C1)
            commands.append(
                f"bond {mol_name}.{pi}.{b.parent_atom} {mol_name}.{ci}.{b.child_atom}"
            )
        else:
            # sugar–sugar glycosidic bond
            commands.append(
                f"bond {mol_name}.{ci}.{b.child_atom} {mol_name}.{pi}.{b.parent_atom}"
            )
    return commands


def _format_disulfide_commands(
    residues: Dict[tuple, Residue],
    disulfides: List[DisulfideBond],
    mol_name: str = "prot",
) -> List[str]:
    """
    Return a list of tleap ``bond`` command strings for all detected
    disulfide bonds (SG–SG).

    Parameters
    ----------
    residues :
        Residue dict as returned by ``_parse_pdb``.
    disulfides :
        Detected disulfide bonds from ``_detect_disulfide_bonds``.
    mol_name :
        tleap molecule variable name (``"prot"`` or ``"PROT"``).

    Returns
    -------
    List of strings such as ``["bond prot.14.SG prot.65.SG", ...]``.
    """
    seen: List[tuple] = []
    for res in sorted(residues.values(), key=lambda r: (r.chain, r.resseq)):
        if res.key not in seen:
            seen.append(res.key)
    res_index = {key: i + 1 for i, key in enumerate(seen)}

    commands: List[str] = []
    for db in disulfides:
        i1 = res_index.get(db.res1_key)
        i2 = res_index.get(db.res2_key)
        if i1 is None or i2 is None:
            logger.warning("Cannot find residue index for disulfide %s — skipping", db)
            continue
        commands.append(f"bond {mol_name}.{i1}.SG {mol_name}.{i2}.SG")
    return commands


def _generate_leap_script(
    residues: Dict[tuple, Residue],
    bonds: List[GlycosidicBond],
    glycam_names: Dict[tuple, str],
    nln_residues: set,
    output_pdb: Path,
    script_path: Path,
    ff: str = "ff14SB",
    glycam_ff: str = "GLYCAM_06j-1",
    disulfides: Optional[List[DisulfideBond]] = None,
) -> Path:
    """Write a tleap input script with force-field sources and bond commands."""
    # Sequential residue numbering (as tleap sees them)
    seen: List[tuple] = []
    for res in sorted(residues.values(), key=lambda r: (r.chain, r.resseq)):
        if res.key not in seen:
            seen.append(res.key)
    res_index = {key: i + 1 for i, key in enumerate(seen)}

    lines = [
        "# Auto-generated tleap script (via GlycanConverter)",
        f"source leaprc.{ff}",
        f"source leaprc.{glycam_ff}",
        "source leaprc.water.tip3p",
        "",
        f"mol = loadpdb {output_pdb}",
        "",
    ]

    # --- Disulfide bonds ---
    ss_lines = []
    for db in (disulfides or []):
        i1 = res_index.get(db.res1_key)
        i2 = res_index.get(db.res2_key)
        if i1 is None or i2 is None:
            logger.warning("Cannot find residue index for disulfide %s — skipping", db)
            continue
        ss_lines.append(
            f"bond mol.{i1}.SG mol.{i2}.SG"
            f"  # CYX {db.res1_key[0]}{db.res1_key[1]} – CYX {db.res2_key[0]}{db.res2_key[1]}"
            f"  ({db.distance:.3f} Å)"
        )
    if ss_lines:
        lines.append("# --- Disulfide bonds ---")
        lines.extend(ss_lines)
        lines.append("")

    protein_bonds, sugar_bonds = [], []
    for b in bonds:
        ci = res_index.get(b.child_key)
        pi = res_index.get(b.parent_key)
        if ci is None or pi is None:
            logger.warning("Cannot find residue index for bond %s", b)
            continue
        parent_res = residues[b.parent_key]
        child_res = residues[b.child_key]
        if b.linkage_position is None:
            protein_bonds.append(
                f"bond mol.{pi}.{b.parent_atom} mol.{ci}.{b.child_atom}"
                f"  # {parent_res.resname} {parent_res.chain}{parent_res.resseq}"
                f" -> {child_res.resname} {b.child_key[0]}{b.child_key[1]}"
            )
        else:
            sugar_bonds.append(
                f"bond mol.{ci}.{b.child_atom} mol.{pi}.{b.parent_atom}"
                f"  # {child_res.resname} {b.child_key[0]}{b.child_key[1]}"
                f" ->({b.linkage_position})-> "
                f"{parent_res.resname} {b.parent_key[0]}{b.parent_key[1]}"
            )

    if protein_bonds:
        lines.append("# --- Protein-glycan bonds ---")
        lines.extend(protein_bonds)
        lines.append("")
    if sugar_bonds:
        lines.append("# --- Glycosidic bonds ---")
        lines.extend(sugar_bonds)
        lines.append("")

    lines += [
        "# --- Check and save ---",
        "check mol",
        "charge mol",
        "",
        "addions mol Na+ 0",
        "addions mol Cl- 0",
        "solvatebox mol TIP3PBOX 12.0",
        "",
        "saveamberparm mol system.prmtop system.inpcrd",
        "savepdb mol system_leap.pdb",
        "quit",
    ]
    script_path.write_text("\n".join(lines) + "\n")
    return script_path


# ---------------------------------------------------------------------------
# Public GlycanConverter class
# ---------------------------------------------------------------------------

class GlycanConverter:
    """
    Convert a Chai-predicted glycoprotein PDB into GLYCAM/AMBER format.

    Parameters
    ----------
    ff : str
        Protein force field name as used in tleap (default ``ff14SB``).
    glycam_ff : str
        GLYCAM force field name as used in tleap (default ``GLYCAM_06j-1``).
    bond_cutoff : float
        Distance threshold (Å) for detecting sugar–sugar glycosidic bonds.
    protein_sugar_cutoff : float
        Distance threshold (Å) for detecting protein–sugar bonds (ASN ND2).

    Example
    -------
    ::

        converter = GlycanConverter()
        result = converter.convert_pdb("fold.pdb", output_dir="prep/")
        print(result['glycam_pdb'])   # renamed PDB
        print(result['leap_script'])  # tleap input script
    """

    def __init__(
        self,
        ff: str = "ff14SB",
        glycam_ff: str = "GLYCAM_06j-1",
        bond_cutoff: float = BOND_CUTOFF,
        protein_sugar_cutoff: float = PROTEIN_SUGAR_CUTOFF,
        disulfide_cutoff: float = DISULFIDE_CUTOFF,
    ):
        self.ff = ff
        self.glycam_ff = glycam_ff
        self.bond_cutoff = bond_cutoff
        self.protein_sugar_cutoff = protein_sugar_cutoff
        self.disulfide_cutoff = disulfide_cutoff
        self._log = logging.getLogger(__name__)

    def convert_pdb(
        self,
        input_pdb: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        output_pdb: Optional[Union[str, Path]] = None,
        leap_script: Optional[Union[str, Path]] = None,
        mol_name: str = "prot",
    ) -> Dict[str, Any]:
        """
        Convert *input_pdb* to GLYCAM/AMBER convention.

        Parameters
        ----------
        input_pdb : path-like
            Chai-1 output PDB containing protein + glycan chains.
        output_dir : path-like, optional
            Directory where output files are written.  Defaults to the same
            directory as *input_pdb*.
        output_pdb : path-like, optional
            Explicit path for the renamed PDB.  Overrides *output_dir*.
        leap_script : path-like, optional
            Explicit path for the tleap ``.in`` script.  Overrides *output_dir*.
        mol_name : str, optional
            tleap molecule variable name used when formatting ``bond_commands``.
            Should match the variable name in the tleap script that loads the
            PDB — ``"prot"`` for ``ImplicitSolvent``, ``"PROT"`` for
            ``ExplicitSolvent`` in the ``molecular-simulations`` library.
            Defaults to ``"prot"``.

        Returns
        -------
        dict with keys:
            ``glycam_pdb``      – Path to the renamed PDB file
            ``leap_script``     – Path to the tleap input script
            ``bonds``           – list of detected GlycosidicBond objects
            ``disulfide_bonds`` – list of detected DisulfideBond objects
            ``bond_commands``   – list of tleap bond command strings (glycan +
                                  disulfide) ready to inject into an external
                                  tleap script
            ``glycam_names``    – dict (chain, resseq) → GLYCAM 3-letter code
            ``nln_residues``    – set of (chain, resseq) renamed to NLN
            ``cyx_residues``    – set of (chain, resseq) renamed to CYX
            ``n_sugars``        – number of sugar residues found
        """
        input_pdb = Path(input_pdb)

        if output_dir is None:
            output_dir = input_pdb.parent
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = input_pdb.stem
        if output_pdb is None:
            output_pdb = output_dir / f"{stem}_glycam.pdb"
        if leap_script is None:
            leap_script = output_dir / f"{stem}_leap.in"

        output_pdb = Path(output_pdb)
        leap_script = Path(leap_script)

        self._log.info("GlycanConverter: reading %s", input_pdb)
        atoms, residues = _parse_pdb(input_pdb)
        n_sugars = sum(1 for r in residues.values() if r.is_sugar)
        self._log.info("  %d atoms, %d residues, %d sugars", len(atoms), len(residues), n_sugars)

        # --- Disulfide detection (always, regardless of glycan content) ---
        self._log.info("Detecting disulfide bonds (cutoff=%.2fÅ)…", self.disulfide_cutoff)
        disulfides = _detect_disulfide_bonds(residues, self.disulfide_cutoff)
        cyx_residues: set = set()
        for db in disulfides:
            cyx_residues.add(db.res1_key)
            cyx_residues.add(db.res2_key)
        self._log.info(
            "  %d disulfide bond(s) detected (%d CYX residues)", len(disulfides), len(cyx_residues)
        )

        if n_sugars == 0:
            self._log.warning("No sugar residues found in %s.", input_pdb)
            # Still need to rewrite PDB if there are disulfides (CYS→CYX rename).
            if cyx_residues:
                self._log.info("  Rewriting PDB to apply CYX renaming → %s", output_pdb)
                _rewrite_pdb(atoms, {}, set(), output_pdb, cyx_residues=cyx_residues)
            else:
                import shutil
                shutil.copy(input_pdb, output_pdb)
            ss_cmds = _format_disulfide_commands(residues, disulfides, mol_name=mol_name)
            leap_script.write_text(
                f"source leaprc.{self.ff}\nsource leaprc.{self.glycam_ff}\n"
                f"mol = loadpdb {output_pdb}\n"
                + ("\n".join(ss_cmds) + "\n" if ss_cmds else "")
                + "check mol\nquit\n"
            )
            return {
                "glycam_pdb": output_pdb,
                "leap_script": leap_script,
                "bonds": [],
                "disulfide_bonds": disulfides,
                "bond_commands": ss_cmds,
                "glycam_names": {},
                "nln_residues": set(),
                "cyx_residues": cyx_residues,
                "n_sugars": 0,
            }

        self._log.info("Detecting glycosidic bonds (cutoff=%.2fÅ)…", self.bond_cutoff)
        bonds = _detect_glycosidic_bonds(residues, self.bond_cutoff, self.protein_sugar_cutoff)
        self._log.info("  %d bond(s) detected", len(bonds))

        self._log.info("Assigning GLYCAM names…")
        glycam_names, nln_residues = _assign_glycam_names(residues, bonds)
        self._log.info(
            "  %d sugar residues named, %d ASN→NLN", len(glycam_names), len(nln_residues)
        )

        self._log.info("Writing renamed PDB → %s", output_pdb)
        _rewrite_pdb(atoms, glycam_names, nln_residues, output_pdb, cyx_residues=cyx_residues)

        self._log.info("Writing tleap script → %s", leap_script)
        _generate_leap_script(
            residues, bonds, glycam_names, nln_residues,
            output_pdb, leap_script,
            ff=self.ff, glycam_ff=self.glycam_ff,
            disulfides=disulfides,
        )

        glycan_cmds = _format_bond_commands(residues, bonds, mol_name=mol_name)
        ss_cmds = _format_disulfide_commands(residues, disulfides, mol_name=mol_name)
        bond_commands = ss_cmds + glycan_cmds   # disulfides first so tleap sees them early
        self._log.info(
            "  %d bond command(s) formatted (%d disulfide, %d glycan, mol_name=%r)",
            len(bond_commands), len(ss_cmds), len(glycan_cmds), mol_name,
        )

        return {
            "glycam_pdb": output_pdb,
            "leap_script": leap_script,
            "bonds": bonds,
            "disulfide_bonds": disulfides,
            "bond_commands": bond_commands,
            "glycam_names": glycam_names,
            "nln_residues": nln_residues,
            "cyx_residues": cyx_residues,
            "n_sugars": n_sugars,
        }


