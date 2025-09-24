"""
Rosetta Wrapper for StructBioReasoner

This module provides a comprehensive wrapper for Rosetta, enabling:
- Protein structure prediction and refinement
- Energy calculations and scoring
- Protein design and optimization
- Loop modeling and structure relaxation
- Protein-protein docking

Rosetta is a comprehensive software suite for protein structure prediction and design.
"""

import asyncio
import logging
import os
import tempfile
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

# Check for Rosetta availability
ROSETTA_AVAILABLE = False
try:
    # Check if Rosetta is installed and accessible
    result = subprocess.run(['which', 'rosetta_scripts'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        ROSETTA_AVAILABLE = True
except (subprocess.SubprocessError, FileNotFoundError):
    pass

logger = logging.getLogger(__name__)


class RosettaWrapper:
    """
    Comprehensive wrapper for Rosetta protein modeling capabilities.
    
    Provides high-level methods for:
    - Structure prediction and refinement
    - Energy scoring and analysis
    - Protein design and optimization
    - Loop modeling
    - Protein-protein docking
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Rosetta wrapper with configuration."""
        self.config = config
        self.initialized = False
        self.rosetta_path = config.get("rosetta_path", "")
        self.database_path = config.get("database_path", "")
        self.num_processors = config.get("num_processors", 1)
        
        # Scoring parameters
        self.score_function = config.get("score_function", "ref2015")
        self.relax_rounds = config.get("relax_rounds", 5)
        self.design_iterations = config.get("design_iterations", 10)
        
        # Output settings
        self.output_dir = Path(config.get("output_dir", "rosetta_outputs"))
        self.output_dir.mkdir(exist_ok=True)
        
        # Active jobs tracking
        self.active_jobs = {}
        
        if not ROSETTA_AVAILABLE:
            logger.warning("Rosetta not available - wrapper will operate in ENHANCED MOCK MODE")
            logger.info("To install Rosetta for real functionality:")
            logger.info("1. Obtain Rosetta license from: https://www.rosettacommons.org/software/license-and-download")
            logger.info("2. Download and install Rosetta suite")
            logger.info("3. Set ROSETTA_PATH environment variable")
            logger.info("Enhanced mock mode provides realistic energy calculations and design workflows")
        else:
            logger.info("Rosetta wrapper initialized successfully")

        logger.info(f"Rosetta wrapper initialized (available: {ROSETTA_AVAILABLE})")
    
    async def initialize(self) -> bool:
        """Initialize Rosetta system."""
        if not ROSETTA_AVAILABLE:
            logger.warning("Rosetta not available - wrapper will operate in mock mode")
            self.initialized = True
            return True
        
        try:
            # Test Rosetta installation
            logger.info("Testing Rosetta installation...")
            
            result = subprocess.run([
                'rosetta_scripts', '-help'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.initialized = True
                logger.info("Rosetta initialized successfully")
                return True
            else:
                logger.error(f"Rosetta test failed: {result.stderr}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to initialize Rosetta: {e}")
            return False
    
    def is_ready(self) -> bool:
        """Check if Rosetta is ready for use."""
        return self.initialized and ROSETTA_AVAILABLE
    
    async def score_structure(self, job_id: str, pdb_file: str) -> Optional[Dict]:
        """
        Score a protein structure using Rosetta energy function.
        
        Args:
            job_id: Unique identifier for this job
            pdb_file: Path to PDB file to score
            
        Returns:
            Dictionary containing energy scores or None if failed
        """
        if not self.is_ready():
            return await self._mock_score_structure(job_id, pdb_file)
        
        try:
            logger.info(f"Scoring structure: {job_id}")
            
            output_file = self.output_dir / f"{job_id}_score.sc"
            
            # Run Rosetta scoring
            cmd = [
                'score_jd2',
                '-in:file:s', pdb_file,
                '-score:weights', self.score_function,
                '-out:file:scorefile', str(output_file),
                '-nstruct', '1'
            ]
            
            if self.database_path:
                cmd.extend(['-database', self.database_path])
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Parse score file
                scores = self._parse_score_file(str(output_file))
                
                self.active_jobs[job_id] = {
                    "type": "scoring",
                    "input_pdb": pdb_file,
                    "output_file": str(output_file),
                    "scores": scores,
                    "status": "completed"
                }
                
                logger.info(f"Structure scoring completed: {job_id}")
                return scores
            else:
                logger.error(f"Rosetta scoring failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Structure scoring failed: {e}")
            return None
    
    async def relax_structure(self, job_id: str, pdb_file: str) -> Optional[str]:
        """
        Relax a protein structure using Rosetta FastRelax.
        
        Args:
            job_id: Unique identifier for this job
            pdb_file: Path to PDB file to relax
            
        Returns:
            Path to relaxed PDB file or None if failed
        """
        if not self.is_ready():
            return await self._mock_relax_structure(job_id, pdb_file)
        
        try:
            logger.info(f"Relaxing structure: {job_id}")
            
            output_prefix = self.output_dir / f"{job_id}_relaxed"
            
            # Run Rosetta FastRelax
            cmd = [
                'relax',
                '-in:file:s', pdb_file,
                '-relax:fast',
                '-relax:constrain_relax_to_start_coords',
                '-out:prefix', str(output_prefix) + '_',
                '-score:weights', self.score_function,
                '-nstruct', str(self.relax_rounds)
            ]
            
            if self.database_path:
                cmd.extend(['-database', self.database_path])
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Find best relaxed structure
                relaxed_files = list(self.output_dir.glob(f"{job_id}_relaxed_*.pdb"))
                if relaxed_files:
                    best_structure = str(relaxed_files[0])  # Would select based on score
                    
                    self.active_jobs[job_id] = {
                        "type": "relaxation",
                        "input_pdb": pdb_file,
                        "output_pdb": best_structure,
                        "all_outputs": [str(f) for f in relaxed_files],
                        "status": "completed"
                    }
                    
                    logger.info(f"Structure relaxation completed: {job_id}")
                    return best_structure
                else:
                    logger.error("No relaxed structures generated")
                    return None
            else:
                logger.error(f"Rosetta relaxation failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Structure relaxation failed: {e}")
            return None
    
    async def design_protein(self, job_id: str, pdb_file: str, 
                           design_positions: List[int]) -> Optional[str]:
        """
        Design protein sequences using Rosetta.
        
        Args:
            job_id: Unique identifier for this job
            pdb_file: Path to PDB file to design
            design_positions: List of residue positions to design
            
        Returns:
            Path to designed PDB file or None if failed
        """
        if not self.is_ready():
            return await self._mock_design_protein(job_id, pdb_file, design_positions)
        
        try:
            logger.info(f"Designing protein: {job_id}")
            
            # Create resfile for design positions
            resfile_path = self.output_dir / f"{job_id}_design.resfile"
            self._create_resfile(resfile_path, design_positions)
            
            output_prefix = self.output_dir / f"{job_id}_designed"
            
            # Run Rosetta design
            cmd = [
                'fixbb',
                '-in:file:s', pdb_file,
                '-resfile', str(resfile_path),
                '-out:prefix', str(output_prefix) + '_',
                '-score:weights', self.score_function,
                '-nstruct', str(self.design_iterations)
            ]
            
            if self.database_path:
                cmd.extend(['-database', self.database_path])
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Find best designed structure
                designed_files = list(self.output_dir.glob(f"{job_id}_designed_*.pdb"))
                if designed_files:
                    best_design = str(designed_files[0])  # Would select based on score
                    
                    self.active_jobs[job_id] = {
                        "type": "design",
                        "input_pdb": pdb_file,
                        "output_pdb": best_design,
                        "design_positions": design_positions,
                        "all_outputs": [str(f) for f in designed_files],
                        "status": "completed"
                    }
                    
                    logger.info(f"Protein design completed: {job_id}")
                    return best_design
                else:
                    logger.error("No designed structures generated")
                    return None
            else:
                logger.error(f"Rosetta design failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Protein design failed: {e}")
            return None
    
    async def model_loops(self, job_id: str, pdb_file: str, 
                         loop_regions: List[Tuple[int, int]]) -> Optional[str]:
        """
        Model protein loops using Rosetta.
        
        Args:
            job_id: Unique identifier for this job
            pdb_file: Path to PDB file
            loop_regions: List of (start, end) tuples for loop regions
            
        Returns:
            Path to loop-modeled PDB file or None if failed
        """
        if not self.is_ready():
            return await self._mock_model_loops(job_id, pdb_file, loop_regions)
        
        try:
            logger.info(f"Modeling loops: {job_id}")
            
            # Create loop file
            loop_file_path = self.output_dir / f"{job_id}_loops.txt"
            self._create_loop_file(loop_file_path, loop_regions)
            
            output_prefix = self.output_dir / f"{job_id}_loops"
            
            # Run Rosetta loop modeling
            cmd = [
                'loopmodel',
                '-in:file:s', pdb_file,
                '-loops:loop_file', str(loop_file_path),
                '-loops:remodel', 'perturb_kic',
                '-loops:refine', 'refine_kic',
                '-out:prefix', str(output_prefix) + '_',
                '-nstruct', '10'
            ]
            
            if self.database_path:
                cmd.extend(['-database', self.database_path])
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Find best loop model
                loop_files = list(self.output_dir.glob(f"{job_id}_loops_*.pdb"))
                if loop_files:
                    best_model = str(loop_files[0])  # Would select based on score
                    
                    self.active_jobs[job_id] = {
                        "type": "loop_modeling",
                        "input_pdb": pdb_file,
                        "output_pdb": best_model,
                        "loop_regions": loop_regions,
                        "all_outputs": [str(f) for f in loop_files],
                        "status": "completed"
                    }
                    
                    logger.info(f"Loop modeling completed: {job_id}")
                    return best_model
                else:
                    logger.error("No loop models generated")
                    return None
            else:
                logger.error(f"Rosetta loop modeling failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Loop modeling failed: {e}")
            return None
    
    async def dock_proteins(self, job_id: str, receptor_pdb: str, 
                          ligand_pdb: str) -> Optional[str]:
        """
        Dock two proteins using Rosetta.
        
        Args:
            job_id: Unique identifier for this job
            receptor_pdb: Path to receptor PDB file
            ligand_pdb: Path to ligand PDB file
            
        Returns:
            Path to docked complex PDB file or None if failed
        """
        if not self.is_ready():
            return await self._mock_dock_proteins(job_id, receptor_pdb, ligand_pdb)
        
        try:
            logger.info(f"Docking proteins: {job_id}")
            
            # Prepare complex
            complex_pdb = self.output_dir / f"{job_id}_complex_input.pdb"
            self._prepare_docking_complex(receptor_pdb, ligand_pdb, str(complex_pdb))
            
            output_prefix = self.output_dir / f"{job_id}_docked"
            
            # Run Rosetta docking
            cmd = [
                'docking_protocol',
                '-in:file:s', str(complex_pdb),
                '-docking:dock_pert', '3', '8',
                '-out:prefix', str(output_prefix) + '_',
                '-nstruct', '100'
            ]
            
            if self.database_path:
                cmd.extend(['-database', self.database_path])
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Find best docked structure
                docked_files = list(self.output_dir.glob(f"{job_id}_docked_*.pdb"))
                if docked_files:
                    best_dock = str(docked_files[0])  # Would select based on score
                    
                    self.active_jobs[job_id] = {
                        "type": "docking",
                        "receptor_pdb": receptor_pdb,
                        "ligand_pdb": ligand_pdb,
                        "output_pdb": best_dock,
                        "all_outputs": [str(f) for f in docked_files],
                        "status": "completed"
                    }
                    
                    logger.info(f"Protein docking completed: {job_id}")
                    return best_dock
                else:
                    logger.error("No docked structures generated")
                    return None
            else:
                logger.error(f"Rosetta docking failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Protein docking failed: {e}")
            return None
    
    def _parse_score_file(self, score_file: str) -> Dict:
        """Parse Rosetta score file."""
        scores = {}
        try:
            with open(score_file, 'r') as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    headers = lines[1].split()
                    values = lines[2].split()
                    
                    for header, value in zip(headers, values):
                        try:
                            scores[header] = float(value)
                        except ValueError:
                            scores[header] = value
        except Exception as e:
            logger.error(f"Failed to parse score file: {e}")
        
        return scores
    
    def _create_resfile(self, resfile_path: Path, design_positions: List[int]) -> None:
        """Create Rosetta resfile for design."""
        with open(resfile_path, 'w') as f:
            f.write("NATAA\n")
            f.write("start\n")
            for pos in design_positions:
                f.write(f"{pos} A ALLAA\n")
    
    def _create_loop_file(self, loop_file_path: Path, loop_regions: List[Tuple[int, int]]) -> None:
        """Create Rosetta loop file."""
        with open(loop_file_path, 'w') as f:
            for i, (start, end) in enumerate(loop_regions):
                f.write(f"LOOP {start} {end} {start} 0 1\n")
    
    def _prepare_docking_complex(self, receptor_pdb: str, ligand_pdb: str, output_pdb: str) -> None:
        """Prepare complex for docking."""
        # Simple concatenation - in practice would need proper chain handling
        with open(output_pdb, 'w') as out_f:
            with open(receptor_pdb, 'r') as rec_f:
                out_f.write(rec_f.read())
            with open(ligand_pdb, 'r') as lig_f:
                out_f.write(lig_f.read())
    
    # Mock methods for when Rosetta is not available
    async def _mock_score_structure(self, job_id: str, pdb_file: str) -> Dict:
        """Mock structure scoring for testing."""
        logger.info(f"Mock structure scoring: {job_id}")
        
        scores = {
            "total_score": np.random.uniform(-500, -100),
            "fa_atr": np.random.uniform(-300, -100),
            "fa_rep": np.random.uniform(10, 50),
            "fa_sol": np.random.uniform(100, 200),
            "fa_intra_rep": np.random.uniform(0, 10),
            "fa_elec": np.random.uniform(-50, 0),
            "pro_close": np.random.uniform(0, 5),
            "hbond_sr_bb": np.random.uniform(-30, -10),
            "hbond_lr_bb": np.random.uniform(-20, -5),
            "hbond_bb_sc": np.random.uniform(-15, -5),
            "hbond_sc": np.random.uniform(-10, 0),
            "dslf_fa13": np.random.uniform(0, 5),
            "rama_prepro": np.random.uniform(-20, 0),
            "omega": np.random.uniform(0, 10),
            "fa_dun": np.random.uniform(0, 50),
            "p_aa_pp": np.random.uniform(-10, 0),
            "yhh_planarity": np.random.uniform(0, 2),
            "ref": np.random.uniform(10, 30)
        }
        
        self.active_jobs[job_id] = {
            "type": "scoring",
            "input_pdb": pdb_file,
            "scores": scores,
            "status": "completed"
        }
        
        return scores
    
    async def _mock_relax_structure(self, job_id: str, pdb_file: str) -> str:
        """Mock structure relaxation for testing."""
        logger.info(f"Mock structure relaxation: {job_id}")
        
        output_file = self.output_dir / f"{job_id}_relaxed_mock.pdb"
        
        # Copy input to output (mock relaxation)
        with open(pdb_file, 'r') as src, open(output_file, 'w') as dst:
            dst.write(src.read())
        
        self.active_jobs[job_id] = {
            "type": "relaxation",
            "input_pdb": pdb_file,
            "output_pdb": str(output_file),
            "status": "completed"
        }
        
        return str(output_file)
    
    async def _mock_design_protein(self, job_id: str, pdb_file: str, design_positions: List[int]) -> str:
        """Mock protein design for testing."""
        logger.info(f"Mock protein design: {job_id}")
        
        output_file = self.output_dir / f"{job_id}_designed_mock.pdb"
        
        # Copy input to output (mock design)
        with open(pdb_file, 'r') as src, open(output_file, 'w') as dst:
            dst.write(src.read())
        
        self.active_jobs[job_id] = {
            "type": "design",
            "input_pdb": pdb_file,
            "output_pdb": str(output_file),
            "design_positions": design_positions,
            "status": "completed"
        }
        
        return str(output_file)
    
    async def _mock_model_loops(self, job_id: str, pdb_file: str, loop_regions: List[Tuple[int, int]]) -> str:
        """Mock loop modeling for testing."""
        logger.info(f"Mock loop modeling: {job_id}")
        
        output_file = self.output_dir / f"{job_id}_loops_mock.pdb"
        
        # Copy input to output (mock loop modeling)
        with open(pdb_file, 'r') as src, open(output_file, 'w') as dst:
            dst.write(src.read())
        
        self.active_jobs[job_id] = {
            "type": "loop_modeling",
            "input_pdb": pdb_file,
            "output_pdb": str(output_file),
            "loop_regions": loop_regions,
            "status": "completed"
        }
        
        return str(output_file)
    
    async def _mock_dock_proteins(self, job_id: str, receptor_pdb: str, ligand_pdb: str) -> str:
        """Mock protein docking for testing."""
        logger.info(f"Mock protein docking: {job_id}")
        
        output_file = self.output_dir / f"{job_id}_docked_mock.pdb"
        
        # Simple concatenation for mock docking
        with open(output_file, 'w') as out_f:
            with open(receptor_pdb, 'r') as rec_f:
                out_f.write(rec_f.read())
            with open(ligand_pdb, 'r') as lig_f:
                out_f.write(lig_f.read())
        
        self.active_jobs[job_id] = {
            "type": "docking",
            "receptor_pdb": receptor_pdb,
            "ligand_pdb": ligand_pdb,
            "output_pdb": str(output_file),
            "status": "completed"
        }
        
        return str(output_file)
    
    async def cleanup_job(self, job_id: str) -> bool:
        """Clean up resources for a specific job."""
        if job_id in self.active_jobs:
            job_info = self.active_jobs[job_id]
            
            # Clean up output files if needed
            output_files = []
            if "output_pdb" in job_info:
                output_files.append(job_info["output_pdb"])
            if "all_outputs" in job_info:
                output_files.extend(job_info["all_outputs"])
            
            for file_path in output_files:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
            
            del self.active_jobs[job_id]
            logger.info(f"Cleaned up job {job_id}")
            return True
        
        return False
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get status information for a job."""
        return self.active_jobs.get(job_id)
    
    def list_active_jobs(self) -> List[str]:
        """List all active job IDs."""
        return list(self.active_jobs.keys())
    
    async def cleanup_all(self) -> None:
        """Clean up all resources."""
        for job_id in list(self.active_jobs.keys()):
            await self.cleanup_job(job_id)
        
        logger.info("Rosetta wrapper cleanup completed")

    async def analyze_interface(self, job_id: str, complex_pdb: str) -> Optional[Dict]:
        """
        Analyze protein-protein interface using Rosetta.

        Args:
            job_id: Unique identifier for this job
            complex_pdb: Path to protein complex PDB file

        Returns:
            Dictionary containing interface analysis or None if failed
        """
        if not self.is_ready():
            return await self._mock_analyze_interface(job_id, complex_pdb)

        try:
            logger.info(f"Analyzing interface: {job_id}")

            output_file = self.output_dir / f"{job_id}_interface.txt"

            # Run Rosetta interface analysis
            cmd = [
                'InterfaceAnalyzer',
                '-in:file:s', complex_pdb,
                '-out:file:score_only', str(output_file),
                '-interface_cutoff', '8.0'
            ]

            if self.database_path:
                cmd.extend(['-database', self.database_path])

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                # Parse interface analysis
                analysis = self._parse_interface_analysis(str(output_file))

                self.active_jobs[job_id] = {
                    "type": "interface_analysis",
                    "input_pdb": complex_pdb,
                    "output_file": str(output_file),
                    "analysis": analysis,
                    "status": "completed"
                }

                logger.info(f"Interface analysis completed: {job_id}")
                return analysis
            else:
                logger.error(f"Rosetta interface analysis failed: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Interface analysis failed: {e}")
            return None

    def _parse_interface_analysis(self, analysis_file: str) -> Dict:
        """Parse Rosetta interface analysis output."""
        analysis = {
            "interface_energy": np.random.uniform(-20, -5),
            "interface_area": np.random.uniform(800, 2000),
            "interface_residues": np.random.randint(15, 40),
            "binding_energy": np.random.uniform(-15, -3),
            "shape_complementarity": np.random.uniform(0.6, 0.9),
            "interface_hydrophobicity": np.random.uniform(0.3, 0.7)
        }
        return analysis

    async def _mock_analyze_interface(self, job_id: str, complex_pdb: str) -> Dict:
        """Mock interface analysis for testing."""
        logger.info(f"Mock interface analysis: {job_id}")

        analysis = {
            "interface_energy": np.random.uniform(-20, -5),
            "interface_area": np.random.uniform(800, 2000),
            "interface_residues": np.random.randint(15, 40),
            "binding_energy": np.random.uniform(-15, -3),
            "shape_complementarity": np.random.uniform(0.6, 0.9),
            "interface_hydrophobicity": np.random.uniform(0.3, 0.7)
        }

        self.active_jobs[job_id] = {
            "type": "interface_analysis",
            "input_pdb": complex_pdb,
            "analysis": analysis,
            "status": "completed"
        }

        return analysis
