#!/bin/bash

################################################################################
# HPC Environment Setup Script for StructBioReasoner
#
# This script automates the setup of StructBioReasoner with MDAgent on HPC
#
# Usage:
#   bash scripts/hpc/setup_hpc_environment.sh
#
# What it does:
#   1. Creates conda environment
#   2. Installs dependencies
#   3. Clones and sets up MDAgent
#   4. Creates necessary directories
#   5. Configures environment variables
################################################################################

set -e  # Exit on error

echo "========================================="
echo "StructBioReasoner HPC Setup"
echo "========================================="
echo "This script will set up StructBioReasoner with MDAgent on HPC"
echo ""

# Configuration
CONDA_ENV_NAME="structbio_env"
PYTHON_VERSION="3.9"
STRUCTBIO_HOME="$HOME/StructBioReasoner"
MDAGENT_HOME="$HOME/MDAgent"

# Check if we're on an HPC system
if ! command -v module &> /dev/null; then
    echo "WARNING: 'module' command not found. Are you on an HPC system?"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Load modules
echo ""
echo "Step 1: Loading required modules..."
if command -v module &> /dev/null; then
    module purge
    module load python/${PYTHON_VERSION} 2>/dev/null || echo "  Note: python module may need manual loading"
    module load cuda/11.8 2>/dev/null || echo "  Note: cuda module may need manual loading"
    module load gcc/11.2.0 2>/dev/null || echo "  Note: gcc module may need manual loading"
    echo "  Loaded modules:"
    module list 2>&1 | grep -v "^$"
else
    echo "  Skipping module loading (not available)"
fi

# Step 2: Create conda environment
echo ""
echo "Step 2: Creating conda environment..."
if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    echo "  Environment '${CONDA_ENV_NAME}' already exists"
    read -p "  Recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda env remove -n ${CONDA_ENV_NAME} -y
        conda create -n ${CONDA_ENV_NAME} python=${PYTHON_VERSION} -y
    fi
else
    conda create -n ${CONDA_ENV_NAME} python=${PYTHON_VERSION} -y
fi

# Activate environment
source $(conda info --base)/etc/profile.d/conda.sh
conda activate ${CONDA_ENV_NAME}

echo "  Activated environment: ${CONDA_ENV_NAME}"
echo "  Python: $(which python)"

# Step 3: Install StructBioReasoner dependencies
echo ""
echo "Step 3: Installing StructBioReasoner dependencies..."
cd ${STRUCTBIO_HOME}

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "  Installed from requirements.txt"
else
    echo "  WARNING: requirements.txt not found"
    echo "  Installing basic dependencies..."
    pip install numpy scipy matplotlib pandas biopython
fi

# Step 4: Install OpenMM with GPU support
echo ""
echo "Step 4: Installing OpenMM with GPU support..."
conda install -c conda-forge openmm -y

# Try to install CUDA toolkit
if conda install -c conda-forge cudatoolkit=11.8 -y 2>/dev/null; then
    echo "  Installed CUDA toolkit via conda"
else
    echo "  Note: CUDA toolkit installation skipped (may already be available via modules)"
fi

# Step 5: Install trajectory analysis tools
echo ""
echo "Step 5: Installing trajectory analysis tools..."
pip install mdtraj numpy scipy matplotlib

# Step 6: Clone and setup MDAgent
echo ""
echo "Step 6: Setting up MDAgent..."
cd $HOME

if [ -d "$MDAGENT_HOME" ]; then
    echo "  MDAgent directory already exists: $MDAGENT_HOME"
    read -p "  Re-clone it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf $MDAGENT_HOME
        git clone https://github.com/msinclair-py/MDAgent.git
    fi
else
    git clone https://github.com/msinclair-py/MDAgent.git
fi

# Install MDAgent dependencies
echo "  Installing MDAgent dependencies..."
# Note: Adjust these based on actual MDAgent requirements
pip install academy-py 2>/dev/null || echo "  Note: academy-py may need manual installation"

# Step 7: Create necessary directories
echo ""
echo "Step 7: Creating directories..."
mkdir -p $HOME/StructBioReasoner/logs
mkdir -p /scratch/$USER/structbio_temp 2>/dev/null || echo "  Note: /scratch may not be available"
mkdir -p /scratch/$USER/structbio_output 2>/dev/null || true
mkdir -p /scratch/$USER/structbio_logs 2>/dev/null || true

if [ -d "/projects/$USER" ]; then
    mkdir -p /projects/$USER/structbio_results
    echo "  Created project directories"
fi

# Step 8: Configure environment variables
echo ""
echo "Step 8: Configuring environment variables..."

# Check if already configured
if grep -q "STRUCTBIO_HOME" ~/.bashrc; then
    echo "  Environment variables already configured in ~/.bashrc"
else
    cat >> ~/.bashrc <<'EOF'

# StructBioReasoner Environment
export STRUCTBIO_HOME=$HOME/StructBioReasoner
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"

# Convenience aliases
alias structbio='cd $STRUCTBIO_HOME && conda activate structbio_env'
alias structbio-gpu='bash $STRUCTBIO_HOME/scripts/hpc/interactive_gpu.sh'
EOF
    echo "  Added environment variables to ~/.bashrc"
fi

# Step 9: Create HPC-specific config
echo ""
echo "Step 9: Creating HPC configuration..."
cd ${STRUCTBIO_HOME}

if [ ! -f "config/protein_config_hpc.yaml" ]; then
    if [ -f "config/protein_config.yaml" ]; then
        cp config/protein_config.yaml config/protein_config_hpc.yaml
        echo "  Created config/protein_config_hpc.yaml"
        echo "  Please edit this file to customize for your HPC system"
    else
        echo "  WARNING: config/protein_config.yaml not found"
    fi
fi

# Step 10: Test installation
echo ""
echo "Step 10: Testing installation..."
cd ${STRUCTBIO_HOME}

echo "  Testing Python imports..."
python -c "import numpy; print('  ✓ NumPy')" || echo "  ✗ NumPy failed"
python -c "import openmm; print('  ✓ OpenMM')" || echo "  ✗ OpenMM failed"
python -c "import mdtraj; print('  ✓ MDTraj')" || echo "  ✗ MDTraj failed"

echo ""
echo "  Testing MDAgent import..."
python -c "from agents import Builder, MDSimulator, MDCoordinator; print('  ✓ MDAgent')" || echo "  ✗ MDAgent failed (may need manual setup)"

# Summary
echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Environment: ${CONDA_ENV_NAME}"
echo "StructBioReasoner: ${STRUCTBIO_HOME}"
echo "MDAgent: ${MDAGENT_HOME}"
echo ""
echo "Next steps:"
echo "  1. Reload your shell: source ~/.bashrc"
echo "  2. Activate environment: conda activate ${CONDA_ENV_NAME}"
echo "  3. Edit HPC config: config/protein_config_hpc.yaml"
echo "  4. Test with: python scripts/test_mdagent_installation.py"
echo "  5. Submit test job: sbatch scripts/hpc/run_md_simulation.slurm"
echo ""
echo "Useful commands:"
echo "  structbio          - Go to StructBioReasoner and activate env"
echo "  structbio-gpu      - Start interactive GPU session"
echo ""
echo "========================================="

