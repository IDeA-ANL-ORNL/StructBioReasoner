# 🚀 StructBioReasoner Installation Guide

## Complete Setup for Jnana, Protognosis, and Paper2Agent Systems

This guide provides comprehensive installation instructions for the complete StructBioReasoner framework, including all dependencies for Jnana integration, Protognosis-style multi-community systems, and the revolutionary Paper2Agent framework.

---

## 📋 **System Requirements**

### **Minimum Requirements**
- **Python**: 3.8+ (3.9+ recommended)
- **RAM**: 8GB minimum (16GB+ recommended)
- **Storage**: 10GB free space
- **OS**: macOS, Linux, or Windows

### **Recommended Requirements**
- **Python**: 3.10+
- **RAM**: 32GB for large-scale simulations
- **GPU**: CUDA-compatible GPU for deep learning models
- **Storage**: 50GB+ for databases and model caches

---

## 🔧 **Installation Steps**

### **Step 1: Clone the Repository**

```bash
# Clone StructBioReasoner
git clone https://github.com/IDeA-ANL-ORNL/StructBioReasoner.git
cd StructBioReasoner

# Clone Jnana (required dependency)
cd ..
git clone https://github.com/IDeA-ANL-ORNL/Jnana.git
cd StructBioReasoner
```

### **Step 2: Set Up Python Environment**

#### **Option A: Using Conda (Recommended)**
```bash
# Create conda environment
conda create -n structbio python=3.10
conda activate structbio

# Install scientific computing packages via conda
conda install -c conda-forge numpy scipy pandas matplotlib seaborn
conda install -c conda-forge networkx scikit-learn
conda install -c conda-forge openmm mdtraj pdbfixer  # Molecular dynamics
```

#### **Option B: Using venv**
```bash
# Create virtual environment
python -m venv structbio_env
source structbio_env/bin/activate  # On Windows: structbio_env\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### **Step 3: Install Core Dependencies**

```bash
# Install core requirements
pip install -r requirements.txt

# Install PyTorch with CUDA support (if you have a GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install PyTorch CPU-only (if no GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### **Step 4: Install Specialized Tools**

#### **PyMOL (Molecular Visualization)**
```bash
# macOS (recommended)
brew install pymol

# Alternative: pip installation
pip install pymol-open-source

# Linux
sudo apt-get install pymol  # Ubuntu/Debian
```

#### **OpenMM (Molecular Dynamics)**
```bash
# Via conda (recommended)
conda install -c conda-forge openmm mdtraj pdbfixer

# Verify OpenMM installation
python -c "import openmm; print(openmm.version.version)"
```

#### **ESM Protein Language Models**
```bash
# Install ESM
pip install fair-esm

# Download ESM models (optional - will download on first use)
python -c "import esm; esm.pretrained.esm2_t33_650M_UR50D()"
```

### **Step 5: Set Up Jnana Integration**

```bash
# Install Jnana dependencies
cd ../Jnana
pip install -r requirements.txt

# Install Jnana in development mode
pip install -e .

# Return to StructBioReasoner
cd ../StructBioReasoner

# Verify Jnana integration
python -c "from jnana.core.jnana_system import JnanaSystem; print('Jnana integration successful')"
```

### **Step 6: Configure Environment**

```bash
# Copy configuration template
cp config/protein_config.example.yaml config/protein_config.yaml

# Create .env file for API keys
cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
# Add other API keys as needed
EOF

# Create necessary directories
mkdir -p data/pdb_cache data/alphafold_cache data/literature
mkdir -p logs sessions output
```

### **Step 7: Install Optional Advanced Tools**

#### **Neo4j (Knowledge Graphs)**
```bash
# Install Neo4j driver
pip install neo4j

# Install Neo4j server (optional - for local development)
# Follow instructions at: https://neo4j.com/download/
```

#### **RFDiffusion (Protein Design)**
```bash
# Clone RFDiffusion (optional)
git clone https://github.com/RosettaCommons/RFdiffusion.git
cd RFdiffusion
pip install -e .
cd ../StructBioReasoner
```

#### **AlphaFold (Structure Prediction)**
```bash
# Install AlphaFold dependencies (optional)
pip install tensorflow dm-haiku dm-tree immutabledict ml-collections chex

# Note: Full AlphaFold requires large database downloads (>2TB)
```

---

## 🧪 **Verification and Testing**

### **Step 1: Basic Installation Test**
```bash
# Run basic verification
python scripts/verify_setup.py

# Test core imports
python -c "
from struct_bio_reasoner.core.protein_system import ProteinEngineeringSystem
from struct_bio_reasoner.paper2agent.paper2agent_orchestrator import Paper2AgentOrchestrator
print('✅ Core systems imported successfully')
"
```

### **Step 2: Run Example Demonstrations**
```bash
# Test basic functionality
python examples/ubiquitin_thermostability_design.py

# Test Paper2Agent system
python examples/phase3_paper2agent_demo.py

# Test multi-community system
python examples/multi_community_thermostability_optimization.py

# Test Ubiquitin Paper2Agent demonstration
python examples/ubiquitin_paper2agent_thermostability_demo.py
```

### **Step 3: Comprehensive Integration Test**
```bash
# Run comprehensive test suite
python test_comprehensive_integration.py

# Run specific component tests
pytest tests/ -v  # If test directory exists
```

---

## 🔧 **Platform-Specific Instructions**

### **macOS**
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install system dependencies
brew install python@3.10 git cmake
brew install pymol  # Recommended for PyMOL

# Install conda
brew install miniconda
```

### **Linux (Ubuntu/Debian)**
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install python3.10 python3.10-venv python3-pip git cmake
sudo apt install build-essential libssl-dev libffi-dev python3-dev

# Install PyMOL
sudo apt install pymol

# Install conda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```

### **Windows**
```bash
# Install Python from python.org or Microsoft Store
# Install Git from git-scm.com
# Install Visual Studio Build Tools for C++ compilation

# Use conda for scientific packages (highly recommended)
# Download Miniconda from: https://docs.conda.io/en/latest/miniconda.html

# Install in conda environment
conda create -n structbio python=3.10
conda activate structbio
conda install -c conda-forge numpy scipy pandas matplotlib seaborn
```

---

## 🚀 **Advanced Configuration**

### **GPU Support Setup**
```bash
# Check CUDA availability
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Install CUDA-enabled packages
conda install -c conda-forge cudatoolkit=11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Verify GPU support
python -c "
import torch
import openmm
print(f'PyTorch CUDA: {torch.cuda.is_available()}')
print(f'OpenMM Platforms: {[openmm.Platform.getPlatform(i).getName() for i in range(openmm.Platform.getNumPlatforms())]}')
"
```

### **Large-Scale Configuration**
```bash
# Configure for large protein systems
export OMP_NUM_THREADS=8  # Adjust based on CPU cores
export CUDA_VISIBLE_DEVICES=0  # Use specific GPU

# Increase memory limits
ulimit -m unlimited  # Remove memory limits (Linux/macOS)

# Configure cache directories
mkdir -p ~/.cache/structbio/{pdb,alphafold,esm}
```

### **Development Setup**
```bash
# Install development dependencies
pip install pytest pytest-asyncio pytest-cov
pip install black isort flake8 mypy
pip install jupyter notebook ipykernel

# Set up pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

---

## 🔍 **Troubleshooting**

### **Common Issues**

#### **Import Errors**
```bash
# If Jnana imports fail
export PYTHONPATH="${PYTHONPATH}:../Jnana"

# If StructBioReasoner imports fail
export PYTHONPATH="${PYTHONPATH}:."
```

#### **OpenMM Issues**
```bash
# Test OpenMM platforms
python -c "
import openmm
for i in range(openmm.Platform.getNumPlatforms()):
    platform = openmm.Platform.getPlatform(i)
    print(f'{platform.getName()}: {platform.getSpeed()}')
"

# If CUDA issues, install via conda
conda install -c conda-forge openmm
```

#### **PyMOL Issues**
```bash
# Test PyMOL installation
python -c "import pymol; pymol.cmd.reinitialize(); print('PyMOL working')"

# If issues, try alternative installation
pip uninstall pymol-open-source
brew install pymol  # macOS
```

#### **Memory Issues**
```bash
# Monitor memory usage
python -c "
import psutil
print(f'Available RAM: {psutil.virtual_memory().available / (1024**3):.1f} GB')
print(f'Total RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB')
"

# Reduce batch sizes in configuration files
# Edit config/protein_config.yaml and reduce batch_size parameters
```

---

## 📚 **Next Steps**

After successful installation:

1. **📖 Read Documentation**: Check `docs/` directory for detailed guides
2. **🧪 Run Examples**: Start with `examples/ubiquitin_thermostability_design.py`
3. **🔬 Try Paper2Agent**: Run `examples/phase3_paper2agent_demo.py`
4. **🤖 Multi-Community**: Test `examples/multi_community_thermostability_optimization.py`
5. **🧬 Ubiquitin Demo**: Execute `examples/ubiquitin_paper2agent_thermostability_demo.py`

### **Configuration Files**
- `config/protein_config.yaml`: Main configuration
- `.env`: API keys and environment variables
- `requirements.txt`: All Python dependencies

### **Key Directories**
- `struct_bio_reasoner/`: Core framework code
- `examples/`: Demonstration scripts
- `docs/`: Comprehensive documentation
- `data/`: Cached data and databases

---

**🎉 You're now ready to use the world's most advanced literature-validated protein engineering framework! Start with the examples and explore the revolutionary Paper2Agent system for unprecedented protein optimization results!** 🧬⚡🎯
