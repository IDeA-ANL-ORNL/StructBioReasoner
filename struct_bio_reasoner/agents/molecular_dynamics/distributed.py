from parsl import python_app, Config
from pathlib import Path
from typing import Any

# Parsl apps that directly execute the simulation tasks
# These run in separate processes/threads and don't use the Agent framework
@python_app(executors=['cpu', 'htex'])
def parsl_build(path: Path, pdb: Path, build_kwargs: dict[str, Any]) -> Path:
    """Execute build task directly in Parsl worker."""
    from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
    
    solvent = build_kwargs.get('solvent', 'implicit')
    
    if solvent == 'implicit':
        builder = ImplicitSolvent(path=path, pdb=pdb, 
                                  **build_kwargs)
    else:  # explicit
        builder = ExplicitSolvent(path=path, pdb=pdb,
                                  **build_kwargs)
    
    try:
        builder.build()
        return builder.out.parent
    except Exception as e:
        return ''

@python_app(executors=['gpu', 'htex'])
def parsl_simulate(path: Path, sim_kwargs: dict[str, Any]) -> Path:
    """Execute simulation task directly in Parsl worker."""
    from molecular_simulations.simulate import ImplicitSimulator, Simulator
    
    solvent = sim_kwargs.get('solvent', 'implicit')
    del sim_kwargs['solvent'] # not actually a kwarg of simulator
    
    if solvent == 'implicit':
        simulator = ImplicitSimulator(path, 
                                      **sim_kwargs)
    else:  # explicit
        simulator = Simulator(path,
                              **sim_kwargs)
    
    try:
        simulator.run()
        return simulator.path
    except Exception as e:
        return ''

@python_app(executors=['cpu', 'htex'])
def parsl_mmpbsa(fe_kwargs: dict[str, Any]) -> float:
    """Execute MMPBSA calculation directly in Parsl worker."""
    from molecular_simulations.simulate.mmpbsa import MMPBSA
    
    path = fe_kwargs['dcd'].parent

    try:
        mmpbsa = MMPBSA(**fe_kwargs)
        mmpbsa.run()
        fe = mmpbsa.free_energy
    except Exception as e:
        import traceback
        logger.warn(traceback.format_exc())
        logger.warn(f'MMPBSA for {path} failed: {e}')
        fe = None
    
    return {'path': path, 'success': fe is not None, 'fe': fe}

@python_app(executors=['cpu', 'htex'])
def prepare_mmpbsa(path: Path) -> dict[str, Any]:
    from rust_simulation_tools import read_prmtop

    top = path / 'system.prmtop'
    dcd = path / 'prod.dcd'
    
    topology = read_prmtop(str(top))
    protein = topology.select('protein')
    oxts = topology.select('protein and name OXT')

    last_protein_resid = oxts.unique_residue_indices[0]
    sel1 = [resid for resid in protein.unique_residue_indices if resid <= last_protein_resid]
    sel2 = resid for resid in protein.unique_residue_indices if resid not in sel1]

    def format_for_cpptraj(resids: list[int]) -> str:
        string = ':'
        cur = resids[0] - 1
        start = resids[0]
        end = None

        for resid in resids:
            if resid - cur > 1:
                end = cur
                string += f'{start}-{end},'
                start = resid

            cur = resid

        end = resids[-1]
        string += f'{start}-{end}'

        return string

    sel1 = format_for_cpptraj(sel1)
    sel2 = format_for_cpptraj(sel2)

    return {'top': top, 'dcd': dcd, 'selections': [sel1, sel2], 'out' path}
