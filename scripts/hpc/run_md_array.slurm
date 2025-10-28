#!/bin/bash
#SBATCH --job-name=structbio_array
#SBATCH --account=REPLACE_WITH_YOUR_ACCOUNT
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --array=1-10%5
#SBATCH --output=logs/structbio_array_%A_%a.out
#SBATCH --error=logs/structbio_array_%A_%a.err

################################################################################
# StructBioReasoner Array Job for Multiple Proteins
#
# This script runs StructBioReasoner on multiple proteins in parallel
#
# Usage:
#   1. Create protein_list.txt with one protein name per line
#   2. sbatch scripts/hpc/run_md_array.slurm
#
# Array job settings:
#   --array=1-10%5  means:
#     - Process proteins 1-10 from the list
#     - Run maximum 5 jobs simultaneously
#
# Customize:
#   - Adjust array range to match number of proteins
#   - Modify %5 to control concurrent jobs
################################################################################

echo "========================================="
echo "StructBioReasoner Array Job"
echo "========================================="
echo "Array Job ID: $SLURM_ARRAY_JOB_ID"
echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
echo "Node: $SLURM_NODELIST"
echo "Start time: $(date)"
echo "========================================="

# Load modules
module purge
module load python/3.9
module load cuda/11.8
module load gcc/11.2.0

# Activate environment
source ~/.bashrc
conda activate structbio_env
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"

# Read protein from list
PROTEIN_LIST="data/protein_list.txt"

if [ ! -f "$PROTEIN_LIST" ]; then
    echo "ERROR: Protein list not found: $PROTEIN_LIST"
    echo "Create this file with one protein name per line"
    exit 1
fi

PROTEIN=$(sed -n "${SLURM_ARRAY_TASK_ID}p" $PROTEIN_LIST)

if [ -z "$PROTEIN" ]; then
    echo "ERROR: No protein found for task ID $SLURM_ARRAY_TASK_ID"
    exit 1
fi

echo "Processing protein: $PROTEIN"

# Set up directories
SCRATCH_DIR=/scratch/$USER/structbio_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}
RESULTS_DIR=/projects/$USER/structbio_results/${PROTEIN}

mkdir -p $SCRATCH_DIR
mkdir -p $RESULTS_DIR
mkdir -p logs

# Check if PDB file exists
PDB_FILE="data/${PROTEIN}.pdb"
if [ ! -f "$PDB_FILE" ]; then
    echo "WARNING: PDB file not found: $PDB_FILE"
    echo "Will attempt to fetch from PDB database"
fi

# GPU info
echo "========================================="
echo "GPU Information:"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
echo "========================================="

# Run simulation
cd $HOME/StructBioReasoner

echo "Starting StructBioReasoner for $PROTEIN..."
python struct_bio_reasoner.py \
    --mode batch \
    --goal "Analyze thermostability and design mutations for ${PROTEIN}" \
    --pdb $PDB_FILE \
    --config config/protein_config_hpc.yaml \
    --output-dir $SCRATCH_DIR \
    2>&1 | tee $SCRATCH_DIR/structbio_${PROTEIN}.log

EXIT_CODE=$?

# Save results
echo "Copying results to $RESULTS_DIR..."
cp -r $SCRATCH_DIR/* $RESULTS_DIR/

# Create summary
cat > $RESULTS_DIR/job_summary.txt <<EOF
=========================================
Job Summary for $PROTEIN
=========================================
Array Job ID: $SLURM_ARRAY_JOB_ID
Array Task ID: $SLURM_ARRAY_TASK_ID
Node: $SLURM_NODELIST
Start time: $(date)
Exit code: $EXIT_CODE
Results location: $RESULTS_DIR
=========================================
EOF

# Cleanup
# rm -rf $SCRATCH_DIR

echo "========================================="
echo "Task $SLURM_ARRAY_TASK_ID completed for $PROTEIN"
echo "Exit code: $EXIT_CODE"
echo "Results: $RESULTS_DIR"
echo "========================================="

exit $EXIT_CODE

