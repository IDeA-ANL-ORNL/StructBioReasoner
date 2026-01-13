# MDAgent Setup Guide

## Quick Setup

This guide will help you install and configure MDAgent for use with StructBioReasoner.

## Prerequisites

- Python 3.8 or higher
- StructBioReasoner installed
- Git

## Installation Steps

### Step 1: Clone MDAgent Repository

```bash
# Navigate to a directory where you want to install MDAgent
cd ~/Desktop/Code  # or your preferred location

# Clone the MDAgent repository
git clone https://github.com/msinclair-py/MDAgent.git
cd MDAgent
```

### Step 2: Install MDAgent Dependencies

MDAgent requires the following packages:
- `academy` - Agent framework
- `molecular_simulations` - MD simulation library

```bash
# Install Academy framework
pip install academy-py  # or the correct package name

# Install molecular_simulations
# This may need to be installed from source or a specific repository
# Check MDAgent's requirements.txt or documentation
```

### Step 3: Add MDAgent to Python Path

You have two options:

#### Option A: Install as Editable Package (Recommended)

If MDAgent has a `setup.py` or `pyproject.toml`:

```bash
cd MDAgent
pip install -e .
```

#### Option B: Add to PYTHONPATH

If MDAgent doesn't have a setup file, add it to your Python path:

**For bash/zsh (add to ~/.bashrc or ~/.zshrc):**
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/MDAgent"
```

**For current session only:**
```bash
export PYTHONPATH="${PYTHONPATH}:$HOME/Desktop/Code/MDAgent"
```

**For Python script:**
```python
import sys
sys.path.insert(0, '/path/to/MDAgent')
```

### Step 4: Verify Installation

Test that MDAgent can be imported:

```bash
python -c "from agents import Builder, MDSimulator, MDCoordinator; print('MDAgent imported successfully!')"
```

If successful, you should see:
```
MDAgent imported successfully!
```

### Step 5: Install Optional Dependencies

For trajectory analysis:

```bash
pip install mdtraj numpy
```

## Configuration for StructBioReasoner

### Update Configuration File

Edit `config/protein_config.yaml`:

```yaml
agents:
  molecular_dynamics:
    enabled: true
    md_backend: "mdagent"  # Switch to MDAgent backend
    
    mdagent:
      solvent_model: "explicit"  # or "implicit"
      force_field: "amber14"
      water_model: "tip3p"
      equil_steps: 10_000
      prod_steps: 1_000_000
      protein: true
      output_file: "system.pdb"
```

### Test Integration

Run the example script:

```bash
cd /path/to/StructBioReasoner
python examples/mdagent_integration_example.py --backend mdagent --example 1
```

## Troubleshooting

### Error: "No module named 'agents'"

**Problem**: Python cannot find the MDAgent agents module.

**Solutions**:

1. **Check PYTHONPATH**:
   ```bash
   echo $PYTHONPATH
   ```
   Make sure it includes the MDAgent directory.

2. **Add to PYTHONPATH temporarily**:
   ```bash
   export PYTHONPATH="${PYTHONPATH}:/path/to/MDAgent"
   ```

3. **Add to Python script**:
   ```python
   import sys
   sys.path.insert(0, '/path/to/MDAgent')
   ```

4. **Install as package** (if setup.py exists):
   ```bash
   cd /path/to/MDAgent
   pip install -e .
   ```

### Error: "No module named 'academy'"

**Problem**: Academy framework not installed.

**Solution**:
```bash
pip install academy-py
# or check MDAgent documentation for correct package name
```

### Error: "No module named 'molecular_simulations'"

**Problem**: Molecular simulations library not installed.

**Solution**:
Check MDAgent's documentation or requirements.txt for installation instructions.

### Error: "MDAgent not available - falling back to OpenMM"

**Problem**: MDAgent initialization failed, but system continues with OpenMM.

**This is expected behavior** if:
- MDAgent is not installed
- MDAgent dependencies are missing
- There's a configuration issue

**To fix**:
1. Check that MDAgent is properly installed
2. Verify all dependencies are installed
3. Check the logs for specific error messages

## Permanent Setup

### For Development

Add to your shell configuration file (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# MDAgent Setup
export PYTHONPATH="${PYTHONPATH}:$HOME/Desktop/Code/MDAgent"
```

Then reload your shell:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### For Production

Create a proper Python package installation:

1. **Create setup.py in MDAgent directory** (if it doesn't exist):

```python
from setuptools import setup, find_packages

setup(
    name="mdagent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "academy-py",
        "molecular_simulations",
        # Add other dependencies
    ],
)
```

2. **Install the package**:
```bash
cd /path/to/MDAgent
pip install -e .
```

## Verification Checklist

- [ ] MDAgent repository cloned
- [ ] Academy framework installed
- [ ] molecular_simulations library installed
- [ ] MDAgent added to PYTHONPATH or installed as package
- [ ] Can import: `from agents import Builder, MDSimulator, MDCoordinator`
- [ ] StructBioReasoner config updated to use MDAgent backend
- [ ] Example script runs successfully

## Quick Test Script

Save this as `test_mdagent.py`:

```python
#!/usr/bin/env python
"""Quick test script for MDAgent installation."""

import sys

def test_mdagent_import():
    """Test if MDAgent can be imported."""
    try:
        from agents import Builder, MDSimulator, MDCoordinator
        print("✅ MDAgent agents imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import MDAgent: {e}")
        return False

def test_academy_import():
    """Test if Academy framework can be imported."""
    try:
        from academy.exchange import LocalExchangeFactory
        from academy.manager import Manager
        print("✅ Academy framework imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import Academy: {e}")
        return False

def test_molecular_simulations():
    """Test if molecular_simulations can be imported."""
    try:
        from molecular_simulations.build import ImplicitSolvent, ExplicitSolvent
        from molecular_simulations.simulate import ImplicitSimulator, Simulator
        print("✅ molecular_simulations imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import molecular_simulations: {e}")
        return False

def main():
    print("Testing MDAgent Installation\n" + "="*50)
    
    results = []
    results.append(test_academy_import())
    results.append(test_molecular_simulations())
    results.append(test_mdagent_import())
    
    print("\n" + "="*50)
    if all(results):
        print("✅ All tests passed! MDAgent is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

Run it:
```bash
python test_mdagent.py
```

## Next Steps

Once MDAgent is installed and verified:

1. **Read the Integration Guide**: `docs/MDAGENT_INTEGRATION_GUIDE.md`
2. **Run Examples**: `examples/mdagent_integration_example.py`
3. **Configure Your Workflows**: Update your protein engineering workflows to use MDAgent

## Support

If you encounter issues:

1. Check MDAgent repository: https://github.com/msinclair-py/MDAgent
2. Review StructBioReasoner logs for detailed error messages
3. Verify all dependencies are installed
4. Check that PYTHONPATH is set correctly

## Alternative: Use OpenMM Backend

If you don't need MDAgent's specific features, you can continue using the OpenMM backend:

```yaml
agents:
  molecular_dynamics:
    md_backend: "openmm"  # Use OpenMM instead
```

The OpenMM backend is:
- Lighter weight
- Easier to install
- Fully functional for most use cases
- The default backend

