#!/usr/bin/env python3
"""Molecular dynamics simulation launcher using OpenMM.

Wraps the MDAgent/OpenMM pipeline: system building (implicit/explicit solvent),
energy minimization, equilibration, and production MD.  Results are recorded
as artifacts in the Artifact DAG for provenance tracking.

Usage:
    python run_md.py --input-pdb structure.pdb --output-dir results/
    python run_md.py --help
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Artifact DAG integration (Layer 3)
# ---------------------------------------------------------------------------
# Resolve the skills/_shared package regardless of how this script is invoked.
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from _shared.artifact import (
    ArtifactMetadata,
    ArtifactType,
    create_artifact,
)
from _shared.artifact_store import ArtifactStore
from _shared.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SKILL_NAME = "molecular-dynamics"
SKILL_VERSION = "0.1.0"

DEFAULT_FORCEFIELD = "amber14-all"
DEFAULT_WATER_MODEL = "tip3p"
DEFAULT_TEMPERATURE_K = 300.0
DEFAULT_PRESSURE_ATM = 1.0
DEFAULT_EQUIL_STEPS = 10_000
DEFAULT_PROD_STEPS = 500_000
DEFAULT_TIMESTEP_FS = 2.0
DEFAULT_SOLVENT = "explicit"
DEFAULT_PLATFORM = "CUDA"


# ---------------------------------------------------------------------------
# OpenMM simulation helpers
# ---------------------------------------------------------------------------

def _build_system(
    pdb_path: Path,
    output_dir: Path,
    forcefield: str,
    water_model: str,
    solvent: str,
    temperature_k: float,
) -> Dict[str, Any]:
    """Build an OpenMM system from a PDB file.

    Returns a dict with keys used by downstream steps (topology path,
    system XML, etc.).  When OpenMM is not installed the function returns
    a placeholder so that ``--help`` and dry-run validation still work.
    """
    try:
        import openmm.app as app
        import openmm.unit as unit
    except ImportError:
        logger.warning("OpenMM not installed — returning placeholder build result")
        return {
            "status": "placeholder",
            "pdb_path": str(pdb_path),
            "output_dir": str(output_dir),
        }

    output_dir.mkdir(parents=True, exist_ok=True)

    pdb = app.PDBFile(str(pdb_path))

    # Select force-field files
    ff_files = [f"{forcefield}.xml"]
    if solvent == "explicit":
        ff_files.append(f"{water_model}.xml")
    elif solvent == "implicit":
        ff_files.append("implicit/gbn2.xml")

    forcefield_obj = app.ForceField(*ff_files)

    # Solvation
    if solvent == "explicit":
        modeller = app.Modeller(pdb.topology, pdb.positions)
        modeller.addSolvent(
            forcefield_obj,
            model=water_model,
            padding=1.0 * unit.nanometers,
            ionicStrength=0.15 * unit.molar,
        )
        topology = modeller.topology
        positions = modeller.positions
    else:
        topology = pdb.topology
        positions = pdb.positions

    system = forcefield_obj.createSystem(
        topology,
        nonbondedMethod=app.PME if solvent == "explicit" else app.NoCutoff,
        nonbondedCutoff=1.0 * unit.nanometers if solvent == "explicit" else None,
        constraints=app.HBonds,
    )

    # Save solvated PDB
    solvated_pdb = output_dir / "solvated.pdb"
    with open(solvated_pdb, "w") as f:
        app.PDBFile.writeFile(topology, positions, f)

    return {
        "status": "success",
        "topology": topology,
        "positions": positions,
        "system": system,
        "solvated_pdb": str(solvated_pdb),
    }


def _run_simulation(
    build_result: Dict[str, Any],
    output_dir: Path,
    temperature_k: float,
    pressure_atm: float,
    equil_steps: int,
    prod_steps: int,
    timestep_fs: float,
    solvent: str,
    platform_name: str,
) -> Dict[str, Any]:
    """Run equilibration + production MD.

    Returns a results dict with trajectory paths and basic statistics.
    """
    if build_result.get("status") == "placeholder":
        logger.warning("Build was placeholder — skipping simulation")
        return {"status": "placeholder", "output_dir": str(output_dir)}

    try:
        import openmm as mm
        import openmm.app as app
        import openmm.unit as unit
    except ImportError:
        logger.warning("OpenMM not installed — returning placeholder simulation result")
        return {"status": "placeholder", "output_dir": str(output_dir)}

    output_dir.mkdir(parents=True, exist_ok=True)

    topology = build_result["topology"]
    positions = build_result["positions"]
    system = build_result["system"]

    # Add barostat for NPT (explicit solvent only)
    if solvent == "explicit":
        system.addForce(
            mm.MonteCarloBarostat(
                pressure_atm * unit.atmospheres,
                temperature_k * unit.kelvin,
                25,
            )
        )

    integrator = mm.LangevinMiddleIntegrator(
        temperature_k * unit.kelvin,
        1.0 / unit.picoseconds,
        timestep_fs * unit.femtoseconds,
    )

    # Platform selection
    try:
        platform = mm.Platform.getPlatformByName(platform_name)
    except Exception:
        logger.warning("Platform %s not available, falling back to CPU", platform_name)
        platform = mm.Platform.getPlatformByName("CPU")

    simulation = app.Simulation(topology, system, integrator, platform)
    simulation.context.setPositions(positions)

    # Energy minimization
    logger.info("Running energy minimization...")
    simulation.minimizeEnergy()

    minimized_pdb = output_dir / "minimized.pdb"
    state = simulation.context.getState(getPositions=True)
    with open(minimized_pdb, "w") as f:
        app.PDBFile.writeFile(topology, state.getPositions(), f)

    # Equilibration
    logger.info("Running equilibration for %d steps...", equil_steps)
    simulation.context.setVelocitiesToTemperature(temperature_k * unit.kelvin)
    simulation.step(equil_steps)

    # Production MD with reporters
    traj_file = output_dir / "prod.dcd"
    log_file = output_dir / "prod.log"

    report_interval = max(prod_steps // 1000, 100)
    simulation.reporters.append(
        app.DCDReporter(str(traj_file), report_interval)
    )
    simulation.reporters.append(
        app.StateDataReporter(
            str(log_file),
            report_interval,
            step=True,
            potentialEnergy=True,
            temperature=True,
            volume=True,
            speed=True,
        )
    )

    logger.info("Running production MD for %d steps...", prod_steps)
    simulation.step(prod_steps)

    # Save final state
    final_state = simulation.context.getState(
        getPositions=True, getVelocities=True, getEnergy=True
    )
    final_pdb = output_dir / "final.pdb"
    with open(final_pdb, "w") as f:
        app.PDBFile.writeFile(topology, final_state.getPositions(), f)

    pe = final_state.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)
    temp_actual = (
        2
        * final_state.getKineticEnergy().value_in_unit(unit.kilojoules_per_mole)
        / (3 * system.getNumParticles() * 0.00831446)
    )

    return {
        "status": "success",
        "output_dir": str(output_dir),
        "trajectory": str(traj_file),
        "log_file": str(log_file),
        "final_pdb": str(final_pdb),
        "minimized_pdb": str(minimized_pdb),
        "solvated_pdb": build_result.get("solvated_pdb"),
        "potential_energy_kj": pe,
        "final_temperature_k": temp_actual,
        "equil_steps": equil_steps,
        "prod_steps": prod_steps,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_md_simulation(
    input_pdb: str | Path,
    output_dir: str | Path,
    forcefield: str = DEFAULT_FORCEFIELD,
    water_model: str = DEFAULT_WATER_MODEL,
    temperature_k: float = DEFAULT_TEMPERATURE_K,
    pressure_atm: float = DEFAULT_PRESSURE_ATM,
    equil_steps: int = DEFAULT_EQUIL_STEPS,
    prod_steps: int = DEFAULT_PROD_STEPS,
    timestep_fs: float = DEFAULT_TIMESTEP_FS,
    solvent: str = DEFAULT_SOLVENT,
    platform: str = DEFAULT_PLATFORM,
    artifact_store_root: Optional[str | Path] = None,
    parent_artifact_ids: tuple[str, ...] = (),
) -> Dict[str, Any]:
    """Run an MD simulation and optionally record provenance.

    Parameters mirror the CLI flags.  When *artifact_store_root* is given the
    function writes artifacts and provenance records; otherwise it just runs
    the simulation.
    """
    input_pdb = Path(input_pdb)
    output_dir = Path(output_dir)

    # Optional provenance tracking
    store: Optional[ArtifactStore] = None
    tracker: Optional[ProvenanceTracker] = None
    run_record = None

    if artifact_store_root is not None:
        store = ArtifactStore(artifact_store_root)
        tracker = ProvenanceTracker(artifact_store_root)
        run_record = tracker.start_run(
            skill_name=SKILL_NAME,
            skill_version=SKILL_VERSION,
            input_artifact_ids=list(parent_artifact_ids),
            parameters={
                "input_pdb": str(input_pdb),
                "forcefield": forcefield,
                "water_model": water_model,
                "temperature_k": temperature_k,
                "pressure_atm": pressure_atm,
                "equil_steps": equil_steps,
                "prod_steps": prod_steps,
                "timestep_fs": timestep_fs,
                "solvent": solvent,
                "platform": platform,
            },
        )

    try:
        # Build
        build_result = _build_system(
            pdb_path=input_pdb,
            output_dir=output_dir,
            forcefield=forcefield,
            water_model=water_model,
            solvent=solvent,
            temperature_k=temperature_k,
        )

        # Simulate
        sim_result = _run_simulation(
            build_result=build_result,
            output_dir=output_dir,
            temperature_k=temperature_k,
            pressure_atm=pressure_atm,
            equil_steps=equil_steps,
            prod_steps=prod_steps,
            timestep_fs=timestep_fs,
            solvent=solvent,
            platform_name=platform,
        )

        # Record artifacts
        output_artifact_ids: list[str] = []
        if store is not None:
            # Trajectory artifact
            traj_artifact = create_artifact(
                parent_ids=parent_artifact_ids,
                metadata=ArtifactMetadata(
                    artifact_type=ArtifactType.TRAJECTORY,
                    skill_name=SKILL_NAME,
                    skill_version=SKILL_VERSION,
                    tags=frozenset({"md", solvent, forcefield}),
                ),
                data={
                    "trajectory_path": sim_result.get("trajectory"),
                    "topology_path": sim_result.get("solvated_pdb"),
                    "output_dir": str(output_dir),
                    "equil_steps": equil_steps,
                    "prod_steps": prod_steps,
                    "temperature_k": temperature_k,
                    "pressure_atm": pressure_atm,
                },
                run_id=run_record.run_id if run_record else None,
            )
            store.put(traj_artifact)
            output_artifact_ids.append(traj_artifact.artifact_id)

            # Simulation summary artifact
            sim_artifact = create_artifact(
                parent_ids=(traj_artifact.artifact_id,),
                metadata=ArtifactMetadata(
                    artifact_type=ArtifactType.SIMULATION,
                    skill_name=SKILL_NAME,
                    skill_version=SKILL_VERSION,
                    tags=frozenset({"md", "summary"}),
                ),
                data=sim_result,
                run_id=run_record.run_id if run_record else None,
            )
            store.put(sim_artifact)
            output_artifact_ids.append(sim_artifact.artifact_id)

        if tracker is not None and run_record is not None:
            tracker.finish_run(
                run_id=run_record.run_id,
                output_artifact_ids=output_artifact_ids,
                status="success",
            )

        sim_result["artifact_ids"] = output_artifact_ids
        return sim_result

    except Exception as exc:
        if tracker is not None and run_record is not None:
            tracker.finish_run(
                run_id=run_record.run_id,
                output_artifact_ids=[],
                status="failed",
                error=str(exc),
            )
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_md",
        description="Run molecular dynamics simulations using OpenMM.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-pdb",
        type=str,
        required=True,
        help="Path to the input PDB structure file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory for simulation output files.",
    )
    parser.add_argument(
        "--forcefield",
        type=str,
        default=DEFAULT_FORCEFIELD,
        help="Force field to use.",
    )
    parser.add_argument(
        "--water-model",
        type=str,
        default=DEFAULT_WATER_MODEL,
        choices=["tip3p", "tip4pew", "tip5p", "spce"],
        help="Water model for explicit solvent.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE_K,
        help="Simulation temperature in Kelvin.",
    )
    parser.add_argument(
        "--pressure",
        type=float,
        default=DEFAULT_PRESSURE_ATM,
        help="Pressure in atmospheres (NPT ensemble, explicit solvent only).",
    )
    parser.add_argument(
        "--equil-steps",
        type=int,
        default=DEFAULT_EQUIL_STEPS,
        help="Number of equilibration steps.",
    )
    parser.add_argument(
        "--prod-steps",
        type=int,
        default=DEFAULT_PROD_STEPS,
        help="Number of production MD steps.",
    )
    parser.add_argument(
        "--timestep",
        type=float,
        default=DEFAULT_TIMESTEP_FS,
        help="Integration timestep in femtoseconds.",
    )
    parser.add_argument(
        "--solvent",
        type=str,
        default=DEFAULT_SOLVENT,
        choices=["explicit", "implicit"],
        help="Solvent model type.",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=DEFAULT_PLATFORM,
        choices=["CUDA", "OpenCL", "CPU"],
        help="OpenMM compute platform.",
    )
    parser.add_argument(
        "--artifact-store",
        type=str,
        default=None,
        help="Root directory for the artifact store (enables provenance tracking).",
    )
    parser.add_argument(
        "--parent-artifacts",
        type=str,
        nargs="*",
        default=[],
        help="Parent artifact IDs for DAG lineage.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = run_md_simulation(
        input_pdb=args.input_pdb,
        output_dir=args.output_dir,
        forcefield=args.forcefield,
        water_model=args.water_model,
        temperature_k=args.temperature,
        pressure_atm=args.pressure,
        equil_steps=args.equil_steps,
        prod_steps=args.prod_steps,
        timestep_fs=args.timestep,
        solvent=args.solvent,
        platform=args.platform,
        artifact_store_root=args.artifact_store,
        parent_artifact_ids=tuple(args.parent_artifacts),
    )

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
