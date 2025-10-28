#!/usr/bin/env python
"""
Quick test script for MDAgent installation.

This script verifies that MDAgent and its dependencies are properly installed
and can be imported by StructBioReasoner.

Usage:
    python scripts/test_mdagent_installation.py
"""

import sys
from pathlib import Path

def test_mdagent_import():
    """Test if MDAgent can be imported."""
    print("\n1. Testing MDAgent import...")
    try:
        from agents import Builder, MDSimulator, MDCoordinator
        print("   ✅ MDAgent agents imported successfully")
        print(f"      - Builder: {Builder}")
        print(f"      - MDSimulator: {MDSimulator}")
        print(f"      - MDCoordinator: {MDCoordinator}")
        return True
    except ImportError as e:
        print(f"   ❌ Failed to import MDAgent: {e}")
        print("\n   Troubleshooting:")
        print("   - Make sure MDAgent is cloned: git clone https://github.com/msinclair-py/MDAgent.git")
        print("   - Add to PYTHONPATH: export PYTHONPATH=\"${PYTHONPATH}:/path/to/MDAgent\"")
        print("   - Or install as package: cd /path/to/MDAgent && pip install -e .")
        return False

def test_academy_import():
    """Test if Academy framework can be imported."""
    print("\n2. Testing Academy framework import...")
    try:
        from academy.exchange import LocalExchangeFactory
        from academy.manager import Manager
        from academy.agent import Agent, action
        from academy.handle import Handle
        print("   ✅ Academy framework imported successfully")
        print(f"      - LocalExchangeFactory: {LocalExchangeFactory}")
        print(f"      - Manager: {Manager}")
        return True
    except ImportError as e:
        print(f"   ❌ Failed to import Academy: {e}")
        print("\n   Troubleshooting:")
        print("   - Install Academy: pip install academy-py")
        print("   - Or check MDAgent documentation for correct package name")
        return False

def test_molecular_simulations():
    """Test if molecular_simulations can be imported."""
    print("\n3. Testing molecular_simulations import...")
    try:
        from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
        from molecular_simulations.simulate import ImplicitSimulator, Simulator
        print("   ✅ molecular_simulations imported successfully")
        print(f"      - ImplicitSolvent: {ImplicitSolvent}")
        print(f"      - ExplicitSolvent: {ExplicitSolvent}")
        print(f"      - ImplicitSimulator: {ImplicitSimulator}")
        print(f"      - Simulator: {Simulator}")
        return True
    except ImportError as e:
        print(f"   ❌ Failed to import molecular_simulations: {e}")
        print("\n   Troubleshooting:")
        print("   - Check MDAgent documentation for installation instructions")
        print("   - This library may need to be installed separately")
        return False

def test_mdagent_adapter():
    """Test if MDAgent adapter can be imported."""
    print("\n4. Testing StructBioReasoner MDAgent adapter...")
    try:
        from struct_bio_reasoner.agents.molecular_dynamics.mdagent_adapter import MDAgentAdapter
        print("   ✅ MDAgentAdapter imported successfully")
        print(f"      - MDAgentAdapter: {MDAgentAdapter}")
        return True
    except ImportError as e:
        print(f"   ❌ Failed to import MDAgentAdapter: {e}")
        print("\n   This should not happen if StructBioReasoner is installed correctly.")
        return False

def test_optional_dependencies():
    """Test optional dependencies for trajectory analysis."""
    print("\n5. Testing optional dependencies...")
    
    results = []
    
    # Test MDTraj
    try:
        import mdtraj as md
        print("   ✅ MDTraj imported successfully")
        print(f"      - Version: {md.version.version}")
        results.append(True)
    except ImportError:
        print("   ⚠️  MDTraj not available (optional)")
        print("      - Install with: pip install mdtraj")
        print("      - Needed for detailed trajectory analysis")
        results.append(False)
    
    # Test NumPy
    try:
        import numpy as np
        print("   ✅ NumPy imported successfully")
        print(f"      - Version: {np.__version__}")
        results.append(True)
    except ImportError:
        print("   ⚠️  NumPy not available (optional)")
        print("      - Install with: pip install numpy")
        results.append(False)
    
    return any(results)  # At least one optional dependency

def test_pythonpath():
    """Display current PYTHONPATH."""
    print("\n6. Checking PYTHONPATH...")
    pythonpath = sys.path
    print("   Current Python search paths:")
    for i, path in enumerate(pythonpath[:10], 1):  # Show first 10
        print(f"      {i}. {path}")
    if len(pythonpath) > 10:
        print(f"      ... and {len(pythonpath) - 10} more")
    
    # Check if MDAgent might be in path
    mdagent_in_path = any('MDAgent' in p for p in pythonpath)
    if mdagent_in_path:
        print("   ✅ MDAgent directory found in Python path")
    else:
        print("   ⚠️  MDAgent directory not found in Python path")
        print("      - You may need to add it: export PYTHONPATH=\"${PYTHONPATH}:/path/to/MDAgent\"")
    
    return True

def print_summary(results):
    """Print test summary."""
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    test_names = [
        "MDAgent Import",
        "Academy Framework",
        "Molecular Simulations",
        "MDAgent Adapter",
        "Optional Dependencies",
        "PYTHONPATH Check"
    ]
    
    for name, result in zip(test_names, results):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:12} - {name}")
    
    print("="*70)
    
    # Overall status
    required_tests = results[:4]  # First 4 are required
    if all(required_tests):
        print("\n🎉 SUCCESS! MDAgent is fully installed and ready to use with StructBioReasoner!")
        print("\nNext steps:")
        print("1. Read the integration guide: docs/MDAGENT_INTEGRATION_GUIDE.md")
        print("2. Run examples: python examples/mdagent_integration_example.py --backend mdagent")
        print("3. Update your config: config/protein_config.yaml")
        return 0
    else:
        print("\n⚠️  INCOMPLETE! Some required components are missing.")
        print("\nPlease fix the failed tests above before using MDAgent backend.")
        print("\nAlternatively, you can use the OpenMM backend:")
        print("  - Set md_backend: 'openmm' in config/protein_config.yaml")
        print("  - OpenMM is lighter weight and easier to install")
        return 1

def main():
    """Main entry point."""
    print("="*70)
    print("MDAgent Installation Test")
    print("="*70)
    print("\nThis script will verify that MDAgent and its dependencies are")
    print("properly installed and can be used with StructBioReasoner.")
    
    results = []
    
    # Run tests
    results.append(test_academy_import())
    results.append(test_molecular_simulations())
    results.append(test_mdagent_import())
    results.append(test_mdagent_adapter())
    results.append(test_optional_dependencies())
    results.append(test_pythonpath())
    
    # Print summary
    return print_summary(results)

if __name__ == "__main__":
    sys.exit(main())

