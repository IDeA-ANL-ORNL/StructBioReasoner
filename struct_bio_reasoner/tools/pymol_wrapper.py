"""
PyMOL wrapper for protein visualization and analysis.

This module provides a wrapper around PyMOL for structural analysis
and visualization tasks in protein engineering.
"""

import asyncio
import logging
import tempfile
import os
import subprocess
import shutil
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

# Check for PyMOL availability
PYMOL_COMMAND_AVAILABLE = bool(shutil.which("pymol"))
PYMOL_PYTHON_AVAILABLE = False

# Check for Homebrew PyMOL with its own Python environment
HOMEBREW_PYMOL_PATH = "/opt/homebrew/Cellar/pymol/3.0.0/libexec/bin/python"
HOMEBREW_PYMOL_AVAILABLE = os.path.exists(HOMEBREW_PYMOL_PATH)

try:
    import pymol
    from pymol import cmd
    PYMOL_PYTHON_AVAILABLE = True
except ImportError:
    pymol = None
    cmd = None

# Determine which PyMOL interface to use
PYMOL_AVAILABLE = PYMOL_PYTHON_AVAILABLE or PYMOL_COMMAND_AVAILABLE or HOMEBREW_PYMOL_AVAILABLE


class PyMOLWrapper:
    """
    Wrapper class for PyMOL operations.

    Provides high-level methods for protein structure analysis,
    visualization, and mutation modeling.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PyMOL wrapper.

        Args:
            config: PyMOL configuration parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Configuration parameters
        self.headless_mode = config.get("headless_mode", True)
        self.ray_trace_quality = config.get("ray_trace_quality", 2)
        self.image_format = config.get("image_format", "png")
        self.image_resolution = config.get("image_resolution", [1024, 768])

        # State
        self.initialized = False
        self.current_structures = {}

        # Determine which PyMOL interface to use
        if PYMOL_PYTHON_AVAILABLE:
            self.use_command_line = False
            self.use_homebrew = False
            self.logger.info("Using Python PyMOL interface")
        elif HOMEBREW_PYMOL_AVAILABLE:
            self.use_command_line = False
            self.use_homebrew = True
            self.logger.info("Using Homebrew PyMOL interface")
        elif PYMOL_COMMAND_AVAILABLE:
            self.use_command_line = True
            self.use_homebrew = False
            self.logger.info("Using command-line PyMOL interface")
        else:
            self.use_command_line = False
            self.use_homebrew = False
            self.logger.warning("PyMOL not available - wrapper will operate in mock mode")
    
    async def initialize(self):
        """Initialize PyMOL session."""
        if not PYMOL_AVAILABLE:
            self.logger.warning("PyMOL not available - initialization skipped")
            self.initialized = False
            return

        try:
            if self.use_homebrew:
                # Test Homebrew PyMOL
                result = await self._run_homebrew_pymol_command('print("PyMOL Homebrew ready")')
                if result and result.returncode == 0:
                    self.initialized = True
                    self.logger.info("Homebrew PyMOL initialized successfully")
                else:
                    self.logger.error(f"Failed to initialize Homebrew PyMOL: {result.stderr if result else 'Unknown error'}")
                    self.initialized = False
            elif self.use_command_line:
                # Test command-line PyMOL
                result = await self._run_pymol_command('print "PyMOL command line ready"\nquit')
                if result and result.returncode == 0:
                    self.initialized = True
                    self.logger.info("Command-line PyMOL initialized successfully")
                else:
                    self.logger.error(f"Failed to initialize command-line PyMOL: {result.stderr if result else 'Unknown error'}")
                    self.initialized = False
            else:
                # Initialize Python PyMOL
                if self.headless_mode:
                    pymol.pymol_argv = ['pymol', '-c']  # Command line mode

                pymol.finish_launching()

                # Set basic preferences
                cmd.set('ray_trace_mode', self.ray_trace_quality)
                cmd.set('antialias', 2)
                cmd.set('orthoscopic', 'on')

                self.initialized = True
                self.logger.info("Python PyMOL initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize PyMOL: {e}")
            self.initialized = False
    
    def is_ready(self) -> bool:
        """Check if PyMOL is ready for operations."""
        return PYMOL_AVAILABLE and self.initialized

    async def _run_pymol_command(self, command: str, input_files: Optional[List[str]] = None) -> Optional[subprocess.CompletedProcess]:
        """
        Run a PyMOL command using the command-line interface.

        Args:
            command: PyMOL command to execute
            input_files: Optional list of input files

        Returns:
            CompletedProcess result or None if failed
        """
        if not PYMOL_COMMAND_AVAILABLE:
            return None

        try:
            # Create temporary script file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pml', delete=False) as script_file:
                script_file.write(command)
                script_path = script_file.name

            # Build PyMOL command
            pymol_cmd = ['pymol', '-c', '-Q']  # -c for command line, -Q for quiet
            if input_files:
                pymol_cmd.extend(input_files)
            pymol_cmd.append(script_path)

            # Execute command
            result = await asyncio.create_subprocess_exec(
                *pymol_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            # Clean up script file
            os.unlink(script_path)

            # Create result object
            completed_result = subprocess.CompletedProcess(
                args=pymol_cmd,
                returncode=result.returncode,
                stdout=stdout,
                stderr=stderr
            )

            return completed_result

        except Exception as e:
            self.logger.error(f"Failed to run PyMOL command: {e}")
            return None

    async def _run_homebrew_pymol_command(self, python_code: str) -> Optional[subprocess.CompletedProcess]:
        """
        Run a PyMOL command using the Homebrew PyMOL Python environment.

        Args:
            python_code: Python code to execute with PyMOL

        Returns:
            CompletedProcess result or None if failed
        """
        if not HOMEBREW_PYMOL_AVAILABLE:
            return None

        try:
            # Execute Python code with Homebrew PyMOL
            result = await asyncio.create_subprocess_exec(
                HOMEBREW_PYMOL_PATH,
                '-c',
                python_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            # Create result object
            completed_result = subprocess.CompletedProcess(
                args=[HOMEBREW_PYMOL_PATH, '-c', python_code],
                returncode=result.returncode,
                stdout=stdout,
                stderr=stderr
            )

            return completed_result

        except Exception as e:
            self.logger.error(f"Failed to run Homebrew PyMOL command: {e}")
            return None
    
    async def load_structure(self, structure_data: Dict[str, Any], name: str = "protein") -> bool:
        """
        Load a protein structure into PyMOL.

        Args:
            structure_data: Structure data (file path or PDB content)
            name: Name for the structure in PyMOL

        Returns:
            True if successful, False otherwise
        """
        if not self.is_ready():
            return False

        try:
            if self.use_command_line or self.use_homebrew:
                # For command-line/homebrew interface, we'll handle loading in individual methods
                self.current_structures[name] = structure_data
                self.logger.info(f"Structure '{name}' registered for {'Homebrew' if self.use_homebrew else 'command-line'} use")
                return True
            else:
                # Handle different input types for Python interface
                if "file_path" in structure_data:
                    file_path = structure_data["file_path"]
                    cmd.load(file_path, name)
                elif "pdb_content" in structure_data:
                    # Save content to temporary file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp_file:
                        tmp_file.write(structure_data["pdb_content"])
                        tmp_file_path = tmp_file.name

                    cmd.load(tmp_file_path, name)
                    os.unlink(tmp_file_path)  # Clean up
                else:
                    self.logger.error("Invalid structure data format")
                    return False

                self.current_structures[name] = structure_data
                self.logger.info(f"Structure '{name}' loaded successfully")
                return True

        except Exception as e:
            self.logger.error(f"Failed to load structure: {e}")
            return False
    
    async def identify_binding_sites(self, structure_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Identify potential binding sites in the protein structure.
        
        Args:
            structure_data: Protein structure data
            
        Returns:
            List of binding site information
        """
        if not self.is_ready():
            return []
        
        binding_sites = []
        
        try:
            # Load structure
            structure_name = "temp_structure"
            if not await self.load_structure(structure_data, structure_name):
                return []
            
            # Find cavities using PyMOL's cavity detection
            cmd.create("cavities", f"{structure_name}")
            cmd.show_as("surface", "cavities")
            
            # Get cavity information (simplified approach)
            # In a real implementation, you would use more sophisticated cavity detection
            cavity_info = self._detect_cavities_simple(structure_name)
            
            for i, cavity in enumerate(cavity_info):
                binding_sites.append({
                    "site_id": f"site_{i+1}",
                    "type": "cavity",
                    "residues": cavity.get("residues", []),
                    "volume": cavity.get("volume", 0.0),
                    "center": cavity.get("center", [0, 0, 0])
                })
            
            # Clean up
            cmd.delete(structure_name)
            cmd.delete("cavities")
            
        except Exception as e:
            self.logger.error(f"Binding site identification failed: {e}")
        
        return binding_sites
    
    async def calculate_cavity_volumes(self, structure_data: Dict[str, Any]) -> List[float]:
        """
        Calculate volumes of protein cavities.
        
        Args:
            structure_data: Protein structure data
            
        Returns:
            List of cavity volumes
        """
        if not self.is_ready():
            return []
        
        volumes = []
        
        try:
            # Load structure
            structure_name = "temp_structure"
            if not await self.load_structure(structure_data, structure_name):
                return []
            
            # Calculate cavity volumes (simplified)
            cavity_info = self._detect_cavities_simple(structure_name)
            volumes = [cavity.get("volume", 0.0) for cavity in cavity_info]
            
            # Clean up
            cmd.delete(structure_name)
            
        except Exception as e:
            self.logger.error(f"Cavity volume calculation failed: {e}")
        
        return volumes
    
    async def visualize_mutations(self,
                                structure_data: Dict[str, Any],
                                mutations: List[Dict[str, Any]],
                                output_path: Optional[str] = None) -> Optional[str]:
        """
        Create visualization of protein mutations.

        Args:
            structure_data: Protein structure data
            mutations: List of mutations to visualize
            output_path: Path to save visualization image

        Returns:
            Path to generated image or None if failed
        """
        if not self.is_ready():
            return None

        try:
            # Generate image path
            if output_path:
                image_path = output_path
            else:
                image_path = tempfile.mktemp(suffix=f'.{self.image_format}')

            if self.use_homebrew:
                return await self._visualize_mutations_homebrew(structure_data, mutations, image_path)
            elif self.use_command_line:
                return await self._visualize_mutations_cmdline(structure_data, mutations, image_path)
            else:
                return await self._visualize_mutations_python(structure_data, mutations, image_path)

        except Exception as e:
            self.logger.error(f"Mutation visualization failed: {e}")
            return None

    async def _visualize_mutations_python(self, structure_data: Dict[str, Any],
                                        mutations: List[Dict[str, Any]],
                                        image_path: str) -> Optional[str]:
        """Visualize mutations using Python PyMOL interface."""
        # Load structure
        structure_name = "protein"
        if not await self.load_structure(structure_data, structure_name):
            return None

        # Set up visualization
        cmd.hide("everything", structure_name)
        cmd.show("cartoon", structure_name)
        cmd.color("gray80", structure_name)

        # Highlight mutation sites
        for i, mutation in enumerate(mutations):
            position = mutation.get("position", 0)
            if position > 0:
                selection_name = f"mutation_{i+1}"
                cmd.select(selection_name, f"{structure_name} and resi {position}")
                cmd.show("spheres", selection_name)
                cmd.color("red", selection_name)

        # Set view and render
        cmd.orient()
        cmd.zoom()
        cmd.png(image_path, width=self.image_resolution[0], height=self.image_resolution[1])

        # Clean up
        cmd.delete("all")

        self.logger.info(f"Mutation visualization saved to {image_path}")
        return image_path

    async def _visualize_mutations_homebrew(self, structure_data: Dict[str, Any],
                                          mutations: List[Dict[str, Any]],
                                          image_path: str) -> Optional[str]:
        """Visualize mutations using Homebrew PyMOL interface."""
        # Create temporary PDB file if needed
        pdb_file = None
        if "pdb_content" in structure_data:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp_file:
                tmp_file.write(structure_data["pdb_content"])
                pdb_file = tmp_file.name
        elif "file_path" in structure_data:
            pdb_file = structure_data["file_path"]
        else:
            self.logger.error("No valid structure data provided")
            return None

        # Create Python script for PyMOL
        python_script = f'''
import pymol
from pymol import cmd

# Initialize PyMOL
pymol.pymol_argv = ['pymol', '-c']
pymol.finish_launching()

try:
    # Load structure
    cmd.load("{pdb_file}", "protein")

    # Set up visualization
    cmd.hide("everything", "protein")
    cmd.show("cartoon", "protein")
    cmd.color("gray80", "protein")

    # Highlight mutation sites
'''

        for i, mutation in enumerate(mutations):
            position = mutation.get("position", 0)
            if position > 0:
                selection_name = f"mutation_{i+1}"
                python_script += f'''
    cmd.select("{selection_name}", "protein and resi {position}")
    cmd.show("spheres", "{selection_name}")
    cmd.color("red", "{selection_name}")
'''

        python_script += f'''
    # Set view and render
    cmd.orient()
    cmd.zoom()
    cmd.png("{image_path}", width={self.image_resolution[0]}, height={self.image_resolution[1]})

    print("Visualization completed successfully")

except Exception as e:
    print(f"Error: {{e}}")

finally:
    cmd.quit()
'''

        # Execute Python script with Homebrew PyMOL
        result = await self._run_homebrew_pymol_command(python_script)

        # Clean up temporary PDB file
        if "pdb_content" in structure_data and pdb_file:
            os.unlink(pdb_file)

        if result and result.returncode == 0 and os.path.exists(image_path):
            self.logger.info(f"Mutation visualization saved to {image_path}")
            return image_path
        else:
            self.logger.error(f"Homebrew PyMOL visualization failed: {result.stderr if result else 'Unknown error'}")
            return None

    async def _visualize_mutations_cmdline(self, structure_data: Dict[str, Any],
                                         mutations: List[Dict[str, Any]],
                                         image_path: str) -> Optional[str]:
        """Visualize mutations using command-line PyMOL interface."""
        # Create temporary PDB file if needed
        pdb_file = None
        if "pdb_content" in structure_data:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp_file:
                tmp_file.write(structure_data["pdb_content"])
                pdb_file = tmp_file.name
        elif "file_path" in structure_data:
            pdb_file = structure_data["file_path"]
        else:
            self.logger.error("No valid structure data provided")
            return None

        # Create PyMOL script
        script_lines = [
            f"load {pdb_file}, protein",
            "hide everything, protein",
            "show cartoon, protein",
            "color gray80, protein"
        ]

        # Add mutation highlighting
        for i, mutation in enumerate(mutations):
            position = mutation.get("position", 0)
            if position > 0:
                selection_name = f"mutation_{i+1}"
                script_lines.extend([
                    f"select {selection_name}, protein and resi {position}",
                    f"show spheres, {selection_name}",
                    f"color red, {selection_name}"
                ])

        # Add rendering commands
        script_lines.extend([
            "orient",
            "zoom",
            f"png {image_path}, width={self.image_resolution[0]}, height={self.image_resolution[1]}",
            "quit"
        ])

        script_content = "\n".join(script_lines)

        # Execute PyMOL script
        result = await self._run_pymol_command(script_content, [pdb_file] if pdb_file else None)

        # Clean up temporary PDB file
        if "pdb_content" in structure_data and pdb_file:
            os.unlink(pdb_file)

        if result and result.returncode == 0 and os.path.exists(image_path):
            self.logger.info(f"Mutation visualization saved to {image_path}")
            return image_path
        else:
            self.logger.error(f"PyMOL visualization failed: {result.stderr if result else 'Unknown error'}")
            return None

    async def create_structure_visualization(self,
                                           structure_data: Dict[str, Any],
                                           output_path: Optional[str] = None,
                                           style: str = "cartoon") -> Optional[str]:
        """
        Create a basic visualization of a protein structure.

        Args:
            structure_data: Protein structure data
            output_path: Path to save visualization image
            style: Visualization style ('cartoon', 'surface', 'sticks', etc.)

        Returns:
            Path to generated image or None if failed
        """
        if not self.is_ready():
            return None

        try:
            # Generate image path
            if output_path:
                image_path = output_path
            else:
                image_path = tempfile.mktemp(suffix=f'.{self.image_format}')

            if self.use_homebrew:
                return await self._create_structure_visualization_homebrew(structure_data, image_path, style)
            elif self.use_command_line:
                return await self._create_structure_visualization_cmdline(structure_data, image_path, style)
            else:
                return await self._create_structure_visualization_python(structure_data, image_path, style)

        except Exception as e:
            self.logger.error(f"Structure visualization failed: {e}")
            return None

    async def _create_structure_visualization_python(self, structure_data: Dict[str, Any],
                                                   image_path: str, style: str) -> Optional[str]:
        """Create structure visualization using Python PyMOL interface."""
        # Load structure
        structure_name = "protein"
        if not await self.load_structure(structure_data, structure_name):
            return None

        # Set up visualization
        cmd.hide("everything", structure_name)
        cmd.show(style, structure_name)
        cmd.util.cbc(structure_name)

        # Set view and render
        cmd.orient()
        cmd.zoom()
        cmd.png(image_path, width=self.image_resolution[0], height=self.image_resolution[1])

        # Clean up
        cmd.delete("all")

        self.logger.info(f"Structure visualization saved to {image_path}")
        return image_path

    async def _create_structure_visualization_cmdline(self, structure_data: Dict[str, Any],
                                                    image_path: str, style: str) -> Optional[str]:
        """Create structure visualization using command-line PyMOL interface."""
        # Create temporary PDB file if needed
        pdb_file = None
        if "pdb_content" in structure_data:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp_file:
                tmp_file.write(structure_data["pdb_content"])
                pdb_file = tmp_file.name
        elif "file_path" in structure_data:
            pdb_file = structure_data["file_path"]
        else:
            self.logger.error("No valid structure data provided")
            return None

        # Create PyMOL script
        script_lines = [
            f"load {pdb_file}, protein",
            "hide everything, protein",
            f"show {style}, protein",
            "util.cbc protein",
            "orient",
            "zoom",
            f"png {image_path}, width={self.image_resolution[0]}, height={self.image_resolution[1]}",
            "quit"
        ]

        script_content = "\n".join(script_lines)

        # Execute PyMOL script
        result = await self._run_pymol_command(script_content, [pdb_file] if pdb_file else None)

        # Clean up temporary PDB file
        if "pdb_content" in structure_data and pdb_file:
            os.unlink(pdb_file)

        if result and result.returncode == 0 and os.path.exists(image_path):
            self.logger.info(f"Structure visualization saved to {image_path}")
            return image_path
        else:
            self.logger.error(f"PyMOL visualization failed: {result.stderr if result else 'Unknown error'}")
            return None

    async def _create_structure_visualization_homebrew(self, structure_data: Dict[str, Any],
                                                     image_path: str, style: str) -> Optional[str]:
        """Create structure visualization using Homebrew PyMOL interface."""
        # Create temporary PDB file if needed
        pdb_file = None
        if "pdb_content" in structure_data:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False) as tmp_file:
                tmp_file.write(structure_data["pdb_content"])
                pdb_file = tmp_file.name
        elif "file_path" in structure_data:
            pdb_file = structure_data["file_path"]
        else:
            self.logger.error("No valid structure data provided")
            return None

        # Create Python script for PyMOL
        python_script = f'''
import pymol
from pymol import cmd

# Initialize PyMOL
pymol.pymol_argv = ['pymol', '-c']
pymol.finish_launching()

try:
    # Load structure
    cmd.load("{pdb_file}", "protein")

    # Set up visualization
    cmd.hide("everything", "protein")
    cmd.show("{style}", "protein")
    cmd.util.cbc("protein")

    # Set view and render
    cmd.orient()
    cmd.zoom()
    cmd.png("{image_path}", width={self.image_resolution[0]}, height={self.image_resolution[1]})

    print("Structure visualization completed successfully")

except Exception as e:
    print(f"Error: {{e}}")

finally:
    cmd.quit()
'''

        # Execute Python script with Homebrew PyMOL
        result = await self._run_homebrew_pymol_command(python_script)

        # Clean up temporary PDB file
        if "pdb_content" in structure_data and pdb_file:
            os.unlink(pdb_file)

        if result and result.returncode == 0 and os.path.exists(image_path):
            self.logger.info(f"Structure visualization saved to {image_path}")
            return image_path
        else:
            self.logger.error(f"Homebrew PyMOL visualization failed: {result.stderr if result else 'Unknown error'}")
            return None
    
    async def calculate_surface_area(self, structure_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate protein surface areas.
        
        Args:
            structure_data: Protein structure data
            
        Returns:
            Dictionary with surface area measurements
        """
        if not self.is_ready():
            return {}
        
        surface_areas = {}
        
        try:
            # Load structure
            structure_name = "protein"
            if not await self.load_structure(structure_data, structure_name):
                return {}
            
            # Calculate surface areas
            cmd.set('dot_solvent', 1)
            cmd.set('dot_density', 3)
            
            # Total surface area
            total_area = cmd.get_area(structure_name)
            surface_areas["total"] = total_area
            
            # Solvent accessible surface area
            cmd.create("surface", structure_name)
            cmd.show("surface", "surface")
            sasa = cmd.get_area("surface")
            surface_areas["solvent_accessible"] = sasa
            
            # Clean up
            cmd.delete("all")
            
        except Exception as e:
            self.logger.error(f"Surface area calculation failed: {e}")
        
        return surface_areas
    
    def _detect_cavities_simple(self, structure_name: str) -> List[Dict[str, Any]]:
        """
        Simple cavity detection using PyMOL.
        
        This is a simplified implementation. In practice, you would use
        more sophisticated cavity detection algorithms.
        """
        cavities = []
        
        try:
            # Get all atoms
            atoms = cmd.get_model(structure_name).atom
            
            # Simple cavity detection based on atom density
            # This is a placeholder - real cavity detection is much more complex
            if len(atoms) > 100:  # Arbitrary threshold
                cavities.append({
                    "residues": ["1", "2", "3"],  # Placeholder
                    "volume": 100.0,  # Placeholder
                    "center": [0, 0, 0]  # Placeholder
                })
            
        except Exception as e:
            self.logger.debug(f"Simple cavity detection failed: {e}")
        
        return cavities
    
    async def cleanup(self):
        """Clean up PyMOL session."""
        if self.is_ready():
            try:
                cmd.delete("all")
                cmd.reinitialize()
            except Exception as e:
                self.logger.warning(f"PyMOL cleanup failed: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        if hasattr(self, 'initialized') and self.initialized:
            try:
                asyncio.create_task(self.cleanup())
            except Exception:
                pass  # Ignore cleanup errors during destruction
