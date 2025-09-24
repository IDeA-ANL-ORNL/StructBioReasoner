#!/usr/bin/env python3
"""
Example: Using PyMOL with StructBioReasoner for Protein Visualization

This example demonstrates how to:
1. Generate protein engineering hypotheses
2. Visualize protein structures with PyMOL
3. Create mutation visualizations
4. Export publication-quality images
"""

import asyncio
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from struct_bio_reasoner.core.protein_system import ProteinEngineeringSystem
from struct_bio_reasoner.tools.pymol_wrapper import PyMOLWrapper

# Sample PDB content for demonstration (small protein fragment)
SAMPLE_PDB = """HEADER    EXAMPLE PROTEIN                         01-JAN-25   DEMO            
ATOM      1  N   MET A   1      20.154  16.967  14.365  1.00 20.00           N  
ATOM      2  CA  MET A   1      19.030  16.101  14.618  1.00 20.00           C  
ATOM      3  C   MET A   1      17.693  16.849  14.897  1.00 20.00           C  
ATOM      4  O   MET A   1      17.534  17.975  14.425  1.00 20.00           O  
ATOM      5  CB  MET A   1      18.756  15.188  13.425  1.00 20.00           C  
ATOM      6  CG  MET A   1      19.876  14.234  13.025  1.00 20.00           C  
ATOM      7  SD  MET A   1      19.345  12.987  11.876  1.00 20.00           S  
ATOM      8  CE  MET A   1      20.876  12.234  11.425  1.00 20.00           C  
ATOM      9  N   ALA A   2      16.770  16.301  15.698  1.00 20.00           N  
ATOM     10  CA  ALA A   2      15.456  16.885  16.027  1.00 20.00           C  
ATOM     11  C   ALA A   2      14.235  15.993  15.897  1.00 20.00           C  
ATOM     12  O   ALA A   2      14.321  14.773  15.726  1.00 20.00           O  
ATOM     13  CB  ALA A   2      15.234  18.123  15.187  1.00 20.00           C  
ATOM     14  N   VAL A   3      13.063  16.587  15.969  1.00 20.00           N  
ATOM     15  CA  VAL A   3      11.789  15.889  15.857  1.00 20.00           C  
ATOM     16  C   VAL A   3      10.567  16.799  15.897  1.00 20.00           C  
ATOM     17  O   VAL A   3      10.653  18.025  15.969  1.00 20.00           O  
ATOM     18  CB  VAL A   3      11.689  14.889  16.997  1.00 20.00           C  
ATOM     19  CG1 VAL A   3      10.456  14.025  16.897  1.00 20.00           C  
ATOM     20  CG2 VAL A   3      12.967  14.089  17.097  1.00 20.00           C  
ATOM     21  N   LYS A   4      9.456   16.234  15.789  1.00 20.00           N  
ATOM     22  CA  LYS A   4      8.234   16.987  15.654  1.00 20.00           C  
ATOM     23  C   LYS A   4      7.123   16.234  14.987  1.00 20.00           C  
ATOM     24  O   LYS A   4      7.234   15.123  14.456  1.00 20.00           O  
ATOM     25  CB  LYS A   4      7.789   17.456  17.034  1.00 20.00           C  
ATOM     26  CG  LYS A   4      8.876   18.234  17.756  1.00 20.00           C  
ATOM     27  CD  LYS A   4      8.345   18.987  18.967  1.00 20.00           C  
ATOM     28  CE  LYS A   4      9.456   19.756  19.687  1.00 20.00           C  
ATOM     29  NZ  LYS A   4      8.987   20.456  20.897  1.00 20.00           N  
END
"""

async def demonstrate_pymol_integration():
    """Demonstrate PyMOL integration with StructBioReasoner."""
    print("🧬 PyMOL Integration with StructBioReasoner")
    print("=" * 60)
    
    # 1. Initialize PyMOL wrapper
    print("1. Initializing PyMOL...")
    pymol_config = {
        "headless_mode": True,
        "ray_trace_quality": 2,
        "image_format": "png",
        "image_resolution": [1200, 900]
    }
    
    pymol_wrapper = PyMOLWrapper(pymol_config)
    await pymol_wrapper.initialize()
    
    if not pymol_wrapper.is_ready():
        print("   ❌ PyMOL not available - skipping visualization examples")
        return
    
    print(f"   ✅ PyMOL initialized successfully!")
    print(f"   📍 Using {'Homebrew' if pymol_wrapper.use_homebrew else 'Python'} interface")
    
    # 2. Create basic protein structure visualization
    print("\n2. Creating basic protein structure visualization...")
    structure_data = {"pdb_content": SAMPLE_PDB}
    
    basic_image = await pymol_wrapper.create_structure_visualization(
        structure_data,
        output_path="protein_structure_basic.png",
        style="cartoon"
    )
    
    if basic_image:
        print(f"   ✅ Basic structure visualization: {basic_image}")
        print(f"   📏 File size: {os.path.getsize(basic_image)} bytes")
    
    # 3. Create different visualization styles
    print("\n3. Creating different visualization styles...")
    styles = ["cartoon", "surface", "sticks", "spheres"]
    
    for style in styles:
        image_path = f"protein_{style}.png"
        result = await pymol_wrapper.create_structure_visualization(
            structure_data,
            output_path=image_path,
            style=style
        )
        
        if result:
            print(f"   ✅ {style.capitalize()} style: {os.path.getsize(result)} bytes")
        else:
            print(f"   ❌ {style.capitalize()} style failed")
    
    # 4. Create mutation visualization
    print("\n4. Creating mutation visualization...")
    
    # Define some example mutations
    mutations = [
        {
            "position": 1,
            "wild_type": "M",
            "mutant": "L",
            "rationale": "Improve hydrophobic packing"
        },
        {
            "position": 3,
            "wild_type": "V",
            "mutant": "I",
            "rationale": "Increase side chain volume"
        },
        {
            "position": 4,
            "wild_type": "K",
            "mutant": "R",
            "rationale": "Maintain positive charge with different geometry"
        }
    ]
    
    mutation_image = await pymol_wrapper.visualize_mutations(
        structure_data,
        mutations,
        output_path="protein_mutations.png"
    )
    
    if mutation_image:
        print(f"   ✅ Mutation visualization: {mutation_image}")
        print(f"   📏 File size: {os.path.getsize(mutation_image)} bytes")
        print(f"   🎯 Highlighted {len(mutations)} mutation sites")
        
        # Print mutation details
        for i, mut in enumerate(mutations, 1):
            print(f"      Mutation {i}: {mut['wild_type']}{mut['position']}{mut['mutant']} - {mut['rationale']}")
    
    # 5. Demonstrate with real PDB structure
    print("\n5. Working with real PDB structure...")
    
    try:
        import urllib.request
        
        # Download a small protein structure (1UBQ - ubiquitin)
        print("   Downloading ubiquitin structure (1UBQ)...")
        pdb_url = "https://files.rcsb.org/download/1UBQ.pdb"
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.pdb', delete=False) as pdb_file:
            with urllib.request.urlopen(pdb_url) as response:
                pdb_content = response.read().decode('utf-8')
                pdb_file.write(pdb_content)
                pdb_file_path = pdb_file.name
        
        print(f"   ✅ Downloaded: {pdb_file_path}")
        
        # Create visualization of real structure
        real_structure_data = {"file_path": pdb_file_path}
        
        real_image = await pymol_wrapper.create_structure_visualization(
            real_structure_data,
            output_path="ubiquitin_real.png",
            style="cartoon"
        )
        
        if real_image:
            print(f"   ✅ Real protein visualization: {real_image}")
            print(f"   📏 File size: {os.path.getsize(real_image)} bytes")
        
        # Create mutation visualization on real structure
        real_mutations = [
            {"position": 8, "wild_type": "K", "mutant": "R", "rationale": "Conservative substitution"},
            {"position": 48, "wild_type": "Q", "mutant": "E", "rationale": "Change charge distribution"},
            {"position": 63, "wild_type": "M", "mutant": "L", "rationale": "Reduce oxidation susceptibility"}
        ]
        
        real_mutation_image = await pymol_wrapper.visualize_mutations(
            real_structure_data,
            real_mutations,
            output_path="ubiquitin_mutations.png"
        )
        
        if real_mutation_image:
            print(f"   ✅ Real protein mutations: {real_mutation_image}")
            print(f"   📏 File size: {os.path.getsize(real_mutation_image)} bytes")
        
        # Clean up
        os.unlink(pdb_file_path)
        
    except Exception as e:
        print(f"   ⚠️  Real PDB example failed: {e}")
    
    # 6. Integration with StructBioReasoner
    print("\n6. Integration with StructBioReasoner system...")
    
    try:
        # Initialize StructBioReasoner
        system = ProteinEngineeringSystem(
            config_path="config/protein_config.yaml",
            enable_tools=["pymol", "biopython"],
            enable_agents=["structural", "mutation_design"]
        )
        
        await system.start()
        
        # Check if PyMOL is available in the system
        status = system.get_protein_system_status()
        pymol_status = status["protein_engineering"]["tool_status"].get("pymol", False)
        
        print(f"   ✅ StructBioReasoner initialized")
        print(f"   🔧 PyMOL tool status: {'Available' if pymol_status else 'Not available'}")
        
        # Generate a hypothesis and visualize it
        session_id = await system.set_research_goal("Improve protein thermostability through strategic mutations")
        
        print(f"   📝 Research session: {session_id}")
        print("   🧠 System ready for hypothesis generation with PyMOL visualization")
        
        await system.stop()
        
    except Exception as e:
        print(f"   ⚠️  StructBioReasoner integration example failed: {e}")
    
    # 7. Summary
    print("\n7. Summary of generated files:")
    generated_files = [
        "protein_structure_basic.png",
        "protein_cartoon.png",
        "protein_surface.png", 
        "protein_sticks.png",
        "protein_spheres.png",
        "protein_mutations.png",
        "ubiquitin_real.png",
        "ubiquitin_mutations.png"
    ]
    
    total_size = 0
    for filename in generated_files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            total_size += size
            print(f"   📁 {filename}: {size:,} bytes")
    
    print(f"\n   📊 Total generated: {len([f for f in generated_files if os.path.exists(f)])} files ({total_size:,} bytes)")
    
    # Cleanup
    await pymol_wrapper.cleanup()
    
    print("\n🎉 PyMOL integration demonstration completed!")
    print("\nNext steps:")
    print("- Use PyMOL visualizations in your protein engineering workflow")
    print("- Integrate with StructBioReasoner hypothesis generation")
    print("- Create publication-quality protein structure figures")

if __name__ == "__main__":
    asyncio.run(demonstrate_pymol_integration())
