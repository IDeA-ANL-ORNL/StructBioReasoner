#!/bin/bash
#SBATCH --job-name=structbio_md
#SBATCH --account=REPLACE_WITH_YOUR_ACCOUNT
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --output=logs/structbio_%j.out
#SBATCH --error=logs/structbio_%j.err

################################################################################
# StructBioReasoner MD Simulation Job
# 
# This script runs StructBioReasoner with MDAgent backend on HPC GPU nodes
#
# Usage:
#   sbatch scripts/hpc/run_md_simulation.slurm
#
# Customize:
#   - Replace REPLACE_WITH_YOUR_ACCOUNT with your HPC account
#   - Adjust partition name for your system
#   - Modify resource requests as needed
################################################################################

echo "========================================="
echo "StructBioReasoner MD Simulation Job"
echo "========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "Start time: $(date)"
echo "========================================="

# Load required modules (adjust for your HPC system)
module purge
module load python/3.9
module load cuda/11.8
module load gcc/11.2.0

echo "Loaded modules:"
module list

# Activate conda environment
source ~/.bashrc
conda activate structbio_env

# Set up paths
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
export STRUCTBIO_HOME=$HOME/StructBioReasoner
export SCRATCH_DIR=/scratch/$USER/structbio_${SLURM_JOB_ID}
export RESULTS_DIR=/projects/$USER/structbio_results/job_${SLURM_JOB_ID}

echo "Environment:"
echo "  PYTHONPATH: $PYTHONPATH"
echo "  STRUCTBIO_HOME: $STRUCTBIO_HOME"
echo "  SCRATCH_DIR: $SCRATCH_DIR"
echo "  RESULTS_DIR: $RESULTS_DIR"

# Create directories
mkdir -p $SCRATCH_DIR
mkdir -p $RESULTS_DIR
mkdir -p logs

# Change to work directory
cd $STRUCTBIO_HOME

# Check GPU availability
echo "========================================="
echo "GPU Information:"
nvidia-smi
echo "========================================="

# Run StructBioReasoner
echo "Starting StructBioReasoner..."
python struct_bio_reasoner.py \
    --mode batch \
    --goal "Design thermostable mutations for enzyme optimization" \
    --count 5 \
    --config config/protein_config_hpc.yaml \
    --output-dir $SCRATCH_DIR \
    2>&1 | tee $SCRATCH_DIR/structbio_run.log

# Check exit status
EXIT_CODE=$?
echo "StructBioReasoner exit code: $EXIT_CODE"

# Copy results to permanent storage
echo "Copying results to $RESULTS_DIR..."
cp -r $SCRATCH_DIR/* $RESULTS_DIR/

# Create summary
echo "=========================================" > $RESULTS_DIR/job_summary.txt
echo "Job Summary" >> $RESULTS_DIR/job_summary.txt
echo "=========================================" >> $RESULTS_DIR/job_summary.txt
echo "Job ID: $SLURM_JOB_ID" >> $RESULTS_DIR/job_summary.txt
echo "Node: $SLURM_NODELIST" >> $RESULTS_DIR/job_summary.txt
echo "Start time: $(date)" >> $RESULTS_DIR/job_summary.txt
echo "Exit code: $EXIT_CODE" >> $RESULTS_DIR/job_summary.txt
echo "Results location: $RESULTS_DIR" >> $RESULTS_DIR/job_summary.txt
echo "=========================================" >> $RESULTS_DIR/job_summary.txt

# Cleanup scratch (optional - comment out if you want to keep)
# echo "Cleaning up scratch directory..."
# rm -rf $SCRATCH_DIR

echo "========================================="
echo "Job completed at $(date)"
echo "Results saved to: $RESULTS_DIR"
echo "========================================="

exit $EXIT_CODE

