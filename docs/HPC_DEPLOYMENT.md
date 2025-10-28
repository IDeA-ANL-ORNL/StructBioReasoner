# HPC Deployment Guide for StructBioReasoner with MDAgent

## Overview

This guide covers deploying StructBioReasoner with MDAgent backend on High-Performance Computing (HPC) systems for production-scale molecular dynamics simulations.

## Prerequisites

- Access to HPC system with:
  - SLURM, PBS, or similar job scheduler
  - GPU nodes (recommended for MD simulations)
  - Module system (Environment Modules or Lmod)
- SSH access to the HPC system
- Basic familiarity with HPC job submission

## Deployment Architecture

```
Local Machine                    HPC System
├── Development                  ├── Compute Nodes
├── Code editing                 │   ├── GPU nodes (MD simulations)
├── Testing                      │   └── CPU nodes (analysis)
└── Job submission               ├── Storage
                                 │   ├── Home directory (code)
                                 │   ├── Scratch (simulations)
                                 │   └── Project space (results)
                                 └── Software
                                     ├── Modules
                                     └── Conda environments
```

## Installation on HPC

### Step 1: Transfer StructBioReasoner to HPC

```bash
# On your local machine
cd ~/Desktop/Code

# Create a tarball (excluding large files)
tar -czf structbio_reasoner.tar.gz \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='sessions' \
    --exclude='*.dcd' \
    --exclude='*.xtc' \
    StructBioReasoner/

# Transfer to HPC
scp structbio_reasoner.tar.gz username@hpc.institution.edu:~/

# SSH to HPC
ssh username@hpc.institution.edu

# Extract
cd ~
tar -xzf structbio_reasoner.tar.gz
```

### Step 2: Set Up Python Environment on HPC

```bash
# Load required modules (adjust for your HPC system)
module load python/3.9
module load cuda/11.8  # For GPU support
module load gcc/11.2.0

# Create conda environment
conda create -n structbio_env python=3.9 -y
conda activate structbio_env

# Install StructBioReasoner dependencies
cd ~/StructBioReasoner
pip install -r requirements.txt

# Install OpenMM with GPU support
conda install -c conda-forge openmm cudatoolkit=11.8 -y

# Install trajectory analysis tools
pip install mdtraj numpy scipy matplotlib
```

### Step 3: Install MDAgent on HPC

```bash
# Clone MDAgent
cd ~
git clone https://github.com/msinclair-py/MDAgent.git

# Install dependencies
cd MDAgent
pip install academy-py  # Adjust package name as needed

# Add to environment setup
echo "export PYTHONPATH=\"\${PYTHONPATH}:$HOME/MDAgent\"" >> ~/.bashrc
source ~/.bashrc

# Verify installation
python -c "from agents import Builder, MDSimulator, MDCoordinator; print('MDAgent ready!')"
```

### Step 4: Configure for HPC

Create HPC-specific configuration:

```bash
cd ~/StructBioReasoner
cp config/protein_config.yaml config/protein_config_hpc.yaml
```

Edit `config/protein_config_hpc.yaml`:

```yaml
agents:
  molecular_dynamics:
    enabled: true
    md_backend: "mdagent"
    
    # HPC-optimized settings
    mdagent:
      solvent_model: "explicit"
      force_field: "amber14"
      water_model: "tip3p"
      equil_steps: 50_000      # Longer equilibration
      prod_steps: 10_000_000   # 20 ns production
      protein: true
      output_file: "system.pdb"
    
    # GPU settings
    platform: "CUDA"
    device_index: 0
    
    # Output paths for HPC
    output_dir: "/scratch/username/structbio_output"
    temp_dir: "/scratch/username/structbio_temp"

# Logging for HPC
logging:
  level: "INFO"
  file: "/scratch/username/structbio_logs/structbio.log"
  console: true
```

## SLURM Job Scripts

### Basic MD Simulation Job

Create `scripts/hpc/run_md_simulation.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=structbio_md
#SBATCH --account=your_account
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --output=logs/structbio_%j.out
#SBATCH --error=logs/structbio_%j.err

# Load modules
module load python/3.9
module load cuda/11.8
module load gcc/11.2.0

# Activate environment
source ~/.bashrc
conda activate structbio_env

# Set up paths
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
export STRUCTBIO_HOME=$HOME/StructBioReasoner
export SCRATCH_DIR=/scratch/$USER/structbio_${SLURM_JOB_ID}

# Create scratch directory
mkdir -p $SCRATCH_DIR
cd $STRUCTBIO_HOME

# Run StructBioReasoner
python struct_bio_reasoner.py \
    --mode batch \
    --goal "Design thermostable mutations for enzyme optimization" \
    --count 5 \
    --config config/protein_config_hpc.yaml \
    --output-dir $SCRATCH_DIR

# Copy results back to project space
cp -r $SCRATCH_DIR/* /projects/$USER/structbio_results/

# Cleanup
rm -rf $SCRATCH_DIR

echo "Job completed at $(date)"
```

### Array Job for Multiple Proteins

Create `scripts/hpc/run_md_array.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=structbio_array
#SBATCH --account=your_account
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --array=1-10%5  # 10 jobs, max 5 running simultaneously
#SBATCH --output=logs/structbio_array_%A_%a.out
#SBATCH --error=logs/structbio_array_%A_%a.err

# Load modules
module load python/3.9
module load cuda/11.8

# Activate environment
conda activate structbio_env
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"

# Read protein from list
PROTEIN_LIST="data/protein_list.txt"
PROTEIN=$(sed -n "${SLURM_ARRAY_TASK_ID}p" $PROTEIN_LIST)

# Set up scratch
SCRATCH_DIR=/scratch/$USER/structbio_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}
mkdir -p $SCRATCH_DIR

# Run simulation
cd $HOME/StructBioReasoner
python struct_bio_reasoner.py \
    --mode batch \
    --goal "Analyze thermostability of ${PROTEIN}" \
    --pdb data/${PROTEIN}.pdb \
    --config config/protein_config_hpc.yaml \
    --output-dir $SCRATCH_DIR

# Save results
RESULTS_DIR=/projects/$USER/structbio_results/${PROTEIN}
mkdir -p $RESULTS_DIR
cp -r $SCRATCH_DIR/* $RESULTS_DIR/

# Cleanup
rm -rf $SCRATCH_DIR
```

### Interactive GPU Session

For testing and development:

```bash
#!/bin/bash
# scripts/hpc/interactive_gpu.sh

srun --account=your_account \
     --partition=gpu \
     --nodes=1 \
     --ntasks-per-node=1 \
     --cpus-per-task=8 \
     --gres=gpu:1 \
     --time=4:00:00 \
     --mem=32G \
     --pty bash

# Once in interactive session:
module load python/3.9 cuda/11.8
conda activate structbio_env
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
cd ~/StructBioReasoner
```

## PBS/Torque Job Scripts

For systems using PBS instead of SLURM:

```bash
#!/bin/bash
#PBS -N structbio_md
#PBS -A your_account
#PBS -q gpu
#PBS -l nodes=1:ppn=8:gpus=1
#PBS -l walltime=24:00:00
#PBS -l mem=32gb
#PBS -o logs/structbio_${PBS_JOBID}.out
#PBS -e logs/structbio_${PBS_JOBID}.err

cd $PBS_O_WORKDIR

# Load modules
module load python/3.9 cuda/11.8

# Activate environment
source ~/.bashrc
conda activate structbio_env
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"

# Run job
python struct_bio_reasoner.py \
    --mode batch \
    --goal "Design thermostable mutations" \
    --count 5 \
    --config config/protein_config_hpc.yaml
```

## Workflow Management

### Create Workflow Script

Create `scripts/hpc/submit_workflow.sh`:

```bash
#!/bin/bash
# Submit complete StructBioReasoner workflow on HPC

set -e

# Configuration
ACCOUNT="your_account"
PARTITION="gpu"
CONFIG="config/protein_config_hpc.yaml"
PROTEIN_LIST="data/proteins_to_analyze.txt"

# Create log directory
mkdir -p logs

# Submit jobs
echo "Submitting StructBioReasoner workflow..."

# Job 1: Structure prediction (CPU)
JOB1=$(sbatch --parsable \
    --account=$ACCOUNT \
    --partition=cpu \
    scripts/hpc/01_structure_prediction.slurm)
echo "Structure prediction job: $JOB1"

# Job 2: MD simulations (GPU, depends on Job 1)
JOB2=$(sbatch --parsable \
    --account=$ACCOUNT \
    --partition=$PARTITION \
    --dependency=afterok:$JOB1 \
    scripts/hpc/02_md_simulations.slurm)
echo "MD simulation job: $JOB2"

# Job 3: Analysis (CPU, depends on Job 2)
JOB3=$(sbatch --parsable \
    --account=$ACCOUNT \
    --partition=cpu \
    --dependency=afterok:$JOB2 \
    scripts/hpc/03_analysis.slurm)
echo "Analysis job: $JOB3"

echo "Workflow submitted successfully!"
echo "Monitor with: squeue -u $USER"
```

## Performance Optimization

### GPU Optimization

```yaml
# config/protein_config_hpc.yaml
agents:
  molecular_dynamics:
    # Use CUDA platform
    platform: "CUDA"
    
    # GPU-specific settings
    precision: "mixed"  # Mixed precision for speed
    
    # Optimize for GPU
    mdagent:
      prod_steps: 50_000_000  # 100 ns on GPU
      
simulation:
  # Larger timestep for speed
  timestep: 0.004  # 4 fs with hydrogen mass repartitioning
```

### Parallel Job Submission

```bash
# Submit multiple independent jobs
for protein in protein1 protein2 protein3; do
    sbatch --export=PROTEIN=$protein scripts/hpc/run_md_simulation.slurm
done
```

## Data Management

### Directory Structure on HPC

```
$HOME/
├── StructBioReasoner/          # Code
├── MDAgent/                    # MDAgent installation
└── .bashrc                     # Environment setup

/scratch/$USER/
├── structbio_temp/             # Temporary files
├── structbio_output/           # Job outputs
└── structbio_logs/             # Log files

/projects/$USER/
└── structbio_results/          # Permanent results
    ├── protein1/
    ├── protein2/
    └── analysis/
```

### Automated Cleanup Script

Create `scripts/hpc/cleanup_scratch.sh`:

```bash
#!/bin/bash
# Clean up old scratch files (run weekly)

SCRATCH_DIR=/scratch/$USER
DAYS_OLD=7

# Remove files older than 7 days
find $SCRATCH_DIR/structbio_* -type f -mtime +$DAYS_OLD -delete
find $SCRATCH_DIR/structbio_* -type d -empty -delete

echo "Cleanup completed: $(date)"
```

## Monitoring and Debugging

### Check Job Status

```bash
# SLURM
squeue -u $USER
sacct -j JOBID --format=JobID,JobName,State,ExitCode,Elapsed

# PBS
qstat -u $USER
```

### View Logs

```bash
# Real-time monitoring
tail -f logs/structbio_JOBID.out

# Check for errors
grep -i error logs/structbio_*.err
```

### GPU Utilization

```bash
# In interactive session or job
nvidia-smi

# Monitor during job
watch -n 1 nvidia-smi
```

## Best Practices

1. **Use Scratch Space**: Run simulations in `/scratch`, copy results to project space
2. **Request Appropriate Resources**: Don't over-request GPUs/memory
3. **Use Array Jobs**: For multiple similar simulations
4. **Set Time Limits**: Estimate runtime and add 20% buffer
5. **Save Checkpoints**: Enable checkpoint saving for long simulations
6. **Monitor Costs**: Track compute hours if on allocation-based system
7. **Clean Up**: Remove temporary files after jobs complete

## Troubleshooting

### Common Issues

**Issue**: Job fails with "Out of memory"
```bash
# Solution: Increase memory request
#SBATCH --mem=64G  # Instead of 32G
```

**Issue**: GPU not detected
```bash
# Solution: Check CUDA module and device
module load cuda/11.8
export CUDA_VISIBLE_DEVICES=0
```

**Issue**: Import errors
```bash
# Solution: Verify PYTHONPATH
echo $PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
```

## Example: Complete Deployment

```bash
# 1. Transfer code
scp -r StructBioReasoner username@hpc:~/

# 2. SSH to HPC
ssh username@hpc

# 3. Set up environment
module load python/3.9 cuda/11.8
conda create -n structbio_env python=3.9 -y
conda activate structbio_env
cd ~/StructBioReasoner
pip install -r requirements.txt

# 4. Install MDAgent
cd ~
git clone https://github.com/msinclair-py/MDAgent.git
echo 'export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"' >> ~/.bashrc

# 5. Test installation
python ~/StructBioReasoner/scripts/test_mdagent_installation.py

# 6. Submit test job
cd ~/StructBioReasoner
sbatch scripts/hpc/run_md_simulation.slurm
```

## Next Steps

1. Customize job scripts for your HPC system
2. Adjust resource requests based on your allocation
3. Set up automated workflows
4. Configure monitoring and notifications
5. Establish data backup procedures

## Support

- HPC System Documentation: Check your institution's HPC user guide
- StructBioReasoner: See `docs/MDAGENT_INTEGRATION_GUIDE.md`
- MDAgent: https://github.com/msinclair-py/MDAgent

