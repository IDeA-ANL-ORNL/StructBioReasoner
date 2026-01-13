# HPC Scripts for StructBioReasoner

This directory contains scripts for running StructBioReasoner with MDAgent on High-Performance Computing (HPC) systems.

## Quick Start

1. **Setup environment** (first time only):
   ```bash
   bash setup_hpc_environment.sh
   ```

2. **Edit job scripts** with your HPC account:
   ```bash
   nano run_md_simulation.slurm
   # Change: REPLACE_WITH_YOUR_ACCOUNT
   ```

3. **Submit job**:
   ```bash
   sbatch run_md_simulation.slurm
   ```

## Available Scripts

### Setup Scripts

#### `setup_hpc_environment.sh`
Automated setup script that:
- Creates conda environment
- Installs all dependencies
- Clones and configures MDAgent
- Sets up directory structure
- Configures environment variables

**Usage:**
```bash
bash setup_hpc_environment.sh
```

### Job Submission Scripts

#### `run_md_simulation.slurm`
Single MD simulation job for SLURM systems.

**Features:**
- GPU-accelerated MD simulations
- Automatic scratch space management
- Results archiving to project space
- Comprehensive logging

**Usage:**
```bash
# Edit account name first
nano run_md_simulation.slurm

# Submit
sbatch run_md_simulation.slurm
```

**Customization:**
- `--account`: Your HPC account/allocation
- `--partition`: GPU partition name
- `--time`: Job time limit
- `--mem`: Memory request
- `--gres=gpu:1`: GPU request

#### `run_md_array.slurm`
Array job for processing multiple proteins in parallel.

**Features:**
- Process multiple proteins from a list
- Parallel execution with concurrency control
- Individual result directories per protein

**Usage:**
```bash
# Create protein list
cat > ../../data/protein_list.txt <<EOF
1ubq
2lyz
3hfm
EOF

# Submit array job
sbatch run_md_array.slurm
```

**Array Configuration:**
```bash
#SBATCH --array=1-10%5
#              ↑    ↑
#              |    └─ Max 5 jobs running simultaneously
#              └────── Process proteins 1-10 from list
```

### Interactive Scripts

#### `interactive_gpu.sh`
Request interactive GPU session for testing and development.

**Usage:**
```bash
bash interactive_gpu.sh
```

**What it does:**
- Requests GPU node
- Loads required modules
- Activates conda environment
- Sets up environment variables
- Provides interactive shell

**Use cases:**
- Testing code changes
- Debugging simulations
- Interactive analysis
- Quick prototyping

## Script Customization

### Common Modifications

#### Change Account/Allocation
```bash
#SBATCH --account=YOUR_ACCOUNT
```

#### Adjust Resources
```bash
#SBATCH --time=48:00:00      # 48 hours
#SBATCH --mem=64G            # 64 GB RAM
#SBATCH --gres=gpu:2         # 2 GPUs
#SBATCH --cpus-per-task=16   # 16 CPU cores
```

#### Change Partition
```bash
#SBATCH --partition=gpu-a100  # Specific GPU type
```

#### Email Notifications
```bash
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=your.email@institution.edu
```

### Module Loading

Adjust for your HPC system:

```bash
# Example for different systems:

# System A
module load python/3.9 cuda/11.8 gcc/11.2.0

# System B
module load anaconda3 cuda/12.0

# System C
module load python cuda openmm
```

### Directory Paths

Update paths for your HPC system:

```bash
# Scratch space
SCRATCH_DIR=/scratch/$USER/structbio_${SLURM_JOB_ID}

# Or use different scratch location:
SCRATCH_DIR=/tmp/$USER/structbio_${SLURM_JOB_ID}
SCRATCH_DIR=/local/scratch/$USER/structbio_${SLURM_JOB_ID}

# Project space
RESULTS_DIR=/projects/$USER/structbio_results

# Or:
RESULTS_DIR=/work/$USER/structbio_results
RESULTS_DIR=/home/$USER/results/structbio
```

## PBS/Torque Systems

If your HPC uses PBS instead of SLURM, convert the scripts:

### SLURM to PBS Conversion

| SLURM | PBS |
|-------|-----|
| `#SBATCH --job-name=NAME` | `#PBS -N NAME` |
| `#SBATCH --account=ACCT` | `#PBS -A ACCT` |
| `#SBATCH --partition=PART` | `#PBS -q PART` |
| `#SBATCH --nodes=1` | `#PBS -l nodes=1` |
| `#SBATCH --time=24:00:00` | `#PBS -l walltime=24:00:00` |
| `#SBATCH --mem=32G` | `#PBS -l mem=32gb` |
| `#SBATCH --gres=gpu:1` | `#PBS -l nodes=1:ppn=1:gpus=1` |
| `$SLURM_JOB_ID` | `$PBS_JOBID` |
| `$SLURM_ARRAY_TASK_ID` | `$PBS_ARRAYID` |

### Example PBS Script

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

module load python/3.9 cuda/11.8
conda activate structbio_env
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"

python struct_bio_reasoner.py --mode batch --goal "..." --count 5
```

## Monitoring Jobs

### SLURM Commands
```bash
# Check queue
squeue -u $USER

# Job details
scontrol show job JOBID

# Cancel job
scancel JOBID

# Job history
sacct -j JOBID

# Watch logs
tail -f logs/structbio_*.out
```

### PBS Commands
```bash
# Check queue
qstat -u $USER

# Job details
qstat -f JOBID

# Cancel job
qdel JOBID

# Watch logs
tail -f logs/structbio_*.out
```

## Troubleshooting

### Job Fails Immediately

**Check error log:**
```bash
cat logs/structbio_JOBID.err
```

**Common issues:**
- Wrong account name → Edit `#SBATCH --account`
- Wrong partition → Check with `sinfo`
- Module not found → Check with `module avail`

### Out of Memory

**Increase memory:**
```bash
#SBATCH --mem=64G  # or higher
```

### GPU Not Available

**Check GPU partitions:**
```bash
sinfo -o "%20P %5a %10l %6D %6t %N"
```

**Verify GPU request:**
```bash
#SBATCH --gres=gpu:1
```

### Import Errors

**Check PYTHONPATH:**
```bash
echo $PYTHONPATH
```

**Should include:**
```bash
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
```

## Best Practices

1. **Test in Interactive Session First**
   ```bash
   bash interactive_gpu.sh
   # Test your commands
   exit
   # Then submit batch job
   ```

2. **Use Scratch Space**
   - Run simulations in `/scratch`
   - Copy results to project space
   - Clean up scratch after job

3. **Request Appropriate Resources**
   - Don't over-request (wastes allocation)
   - Don't under-request (job fails)
   - Monitor first few jobs to optimize

4. **Use Array Jobs for Multiple Proteins**
   - More efficient than individual jobs
   - Better queue management
   - Easier to monitor

5. **Save Logs**
   - Keep job output logs
   - Useful for debugging
   - Track resource usage

## Examples

### Submit Single Job
```bash
sbatch run_md_simulation.slurm
```

### Submit Array Job
```bash
# Create protein list
echo -e "1ubq\n2lyz\n3hfm" > ../../data/protein_list.txt

# Submit
sbatch run_md_array.slurm
```

### Interactive Testing
```bash
bash interactive_gpu.sh
```

### Monitor Jobs
```bash
# Watch queue
watch -n 5 'squeue -u $USER'

# Follow log
tail -f logs/structbio_*.out
```

## Support

- **HPC Documentation**: See `../../docs/HPC_DEPLOYMENT.md`
- **Quick Start**: See `../../docs/HPC_QUICK_START.md`
- **Integration Guide**: See `../../docs/MDAGENT_INTEGRATION_GUIDE.md`
- **Your HPC System**: Check institution-specific documentation

