#!/bin/bash

################################################################################
# Interactive GPU Session for StructBioReasoner Development/Testing
#
# This script requests an interactive GPU session on the HPC system
# for testing and debugging StructBioReasoner with MDAgent
#
# Usage:
#   bash scripts/hpc/interactive_gpu.sh
#
# Customize:
#   - Replace YOUR_ACCOUNT with your HPC account
#   - Adjust time limit (default: 4 hours)
#   - Modify resource requests as needed
################################################################################

echo "Requesting interactive GPU session..."
echo "This may take a few minutes depending on queue..."

srun --account=YOUR_ACCOUNT \
     --partition=gpu \
     --nodes=1 \
     --ntasks-per-node=1 \
     --cpus-per-task=8 \
     --gres=gpu:1 \
     --time=4:00:00 \
     --mem=32G \
     --pty bash -c '
     
# Load modules
module purge
module load python/3.9
module load cuda/11.8
module load gcc/11.2.0

# Activate environment
source ~/.bashrc
conda activate structbio_env

# Set up paths
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
cd ~/StructBioReasoner

# Display environment info
echo "========================================="
echo "Interactive GPU Session Ready"
echo "========================================="
echo "Node: $(hostname)"
echo "GPU Info:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo "========================================="
echo "Environment:"
echo "  Python: $(which python)"
echo "  Conda env: $CONDA_DEFAULT_ENV"
echo "  Working dir: $(pwd)"
echo "========================================="
echo ""
echo "You can now run StructBioReasoner commands:"
echo "  python struct_bio_reasoner.py --mode batch --goal \"...\" --count 3"
echo ""
echo "Or test MDAgent integration:"
echo "  python examples/mdagent_integration_example.py --backend mdagent"
echo ""
echo "Session will end in 4 hours or when you type \"exit\""
echo "========================================="

# Start interactive bash
exec bash
'

