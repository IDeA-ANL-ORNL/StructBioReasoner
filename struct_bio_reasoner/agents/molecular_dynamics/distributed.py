from parsl import python_app, Config
from pathlib import Path
from typing import Any

# Parsl apps that directly execute the simulation tasks
# These run in separate processes/threads and don't use the Agent framework
@python_app
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

@python_app
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

@python_app
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
