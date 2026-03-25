#!/usr/bin/env python3
"""
glycam_mapping.py  (CLI wrapper)

Thin command-line interface around
``struct_bio_reasoner.agents.molecular_dynamics.glycam_mapper.GlycanConverter``.

Converts Chai-predicted glycoprotein PDB files to GLYCAM/AMBER convention:
  1. Detects glycosidic bonds from atomic distances.
  2. Determines anomeric configuration from glycan-tree topology.
  3. Assigns GLYCAM 3-letter residue codes (linkage + sugar letter + anomer).
  4. Renames atoms for N-acetyl sugars (C7→C2N, C8→CME, O7→O2N).
  5. Renames protein ASN residues linked to glycans → NLN.
  6. Outputs a renamed PDB and a tleap input script.

Usage:
    python scripts/glycam_mapping.py input.pdb [--output renamed.pdb] \\
        [--leapscript leap.in] [--ff ff14SB] [--glycam GLYCAM_06j-1] [--quiet]
"""

import argparse
import logging
import sys
from pathlib import Path

# Import core logic from the library module.
# If running the script standalone without the package installed, add the repo
# root to sys.path first:
#   PYTHONPATH=/path/to/StructBioReasoner python scripts/glycam_mapping.py …
try:
    from struct_bio_reasoner.agents.molecular_dynamics.glycam_mapper import (
        GlycanConverter,
        BOND_CUTOFF,
        PROTEIN_SUGAR_CUTOFF,
    )
except ImportError as _err:
    print(
        f"ERROR: cannot import glycam_mapper — is the package installed?\n  {_err}",
        file=sys.stderr,
    )
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Chai glycoprotein PDB to GLYCAM/AMBER convention."
    )
    parser.add_argument("input_pdb", help="Input PDB file from Chai")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output renamed PDB path (default: <stem>_glycam.pdb next to input)",
    )
    parser.add_argument(
        "--leapscript", "-l", default=None,
        help="Output tleap script path (default: <stem>_leap.in next to input)",
    )
    parser.add_argument("--ff", default="ff14SB",
                        help="Protein force field for tleap (default: ff14SB)")
    parser.add_argument("--glycam", default="GLYCAM_06j-1",
                        help="GLYCAM force field version (default: GLYCAM_06j-1)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress INFO logging")
    parser.add_argument(
        "--bond-cutoff", type=float, default=BOND_CUTOFF,
        help=f"Glycosidic bond distance cutoff in Å (default: {BOND_CUTOFF})",
    )
    parser.add_argument(
        "--protein-bond-cutoff", type=float, default=PROTEIN_SUGAR_CUTOFF,
        help=f"Protein-sugar bond cutoff in Å (default: {PROTEIN_SUGAR_CUTOFF})",
    )
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    input_pdb = Path(args.input_pdb)
    output_dir = input_pdb.parent

    converter = GlycanConverter(
        ff=args.ff,
        glycam_ff=args.glycam,
        bond_cutoff=args.bond_cutoff,
        protein_sugar_cutoff=args.protein_bond_cutoff,
    )

    result = converter.convert_pdb(
        input_pdb=input_pdb,
        output_dir=output_dir,
        output_pdb=args.output,
        leap_script=args.leapscript,
    )

    print(f"\nDone!")
    print(f"  Renamed PDB  : {result['glycam_pdb']}")
    print(f"  tleap script : {result['leap_script']}")
    print(f"  Sugar residues: {result['n_sugars']}")
    print(f"  Bonds detected: {len(result['bonds'])}")
    print(f"\nNext steps:")
    print(f"  1. Review {result['glycam_pdb']} in PyMOL/VMD")
    print(f"  2. Run: tleap -f {result['leap_script']}")
    print(f"  3. Check for missing-parameter warnings")


if __name__ == "__main__":
    main()

