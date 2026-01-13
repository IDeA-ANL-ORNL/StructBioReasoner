# HPC Quick Start Guide

## TL;DR - Get Running in 5 Minutes

```bash
# 1. Transfer code to HPC
scp -r StructBioReasoner username@hpc.institution.edu:~/

# 2. SSH to HPC
ssh username@hpc.institution.edu

# 3. Run automated setup
cd ~/StructBioReasoner
bash scripts/hpc/setup_hpc_environment.sh

# 4. Edit job script with your account
nano scripts/hpc/run_md_simulation.slurm
# Change: REPLACE_WITH_YOUR_ACCOUNT

# 5. Submit job
sbatch scripts/hpc/run_md_simulation.slurm

# 6. Monitor
squeue -u $USER
```

## File Transfer

### Option 1: SCP (Small projects)
```bash
# From local machine
cd ~/Desktop/Code
scp -r StructBioReasoner username@hpc:~/
```

### Option 2: rsync (Recommended for updates)
```bash
# From local machine
rsync -avz --exclude='*.pyc' --exclude='__pycache__' \
    StructBioReasoner/ username@hpc:~/StructBioReasoner/
```

### Option 3: Git (Best for version control)
```bash
# On HPC
cd ~
git clone https://github.com/IDeA-ANL-ORNL/StructBioReasoner.git
cd StructBioReasoner
git checkout your-branch
```

## Quick Setup Commands

### Automated Setup
```bash
cd ~/StructBioReasoner
bash scripts/hpc/setup_hpc_environment.sh
```

### Manual Setup (if automated fails)
```bash
# Load modules
module load python/3.9 cuda/11.8

# Create environment
conda create -n structbio_env python=3.9 -y
conda activate structbio_env

# Install dependencies
cd ~/StructBioReasoner
pip install -r requirements.txt
conda install -c conda-forge openmm cudatoolkit=11.8 -y
pip install mdtraj numpy

# Setup MDAgent
cd ~
git clone https://github.com/msinclair-py/MDAgent.git
echo 'export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"' >> ~/.bashrc
source ~/.bashrc
```

## Job Submission Cheat Sheet

### Single Job
```bash
# Edit account name first!
nano scripts/hpc/run_md_simulation.slurm

# Submit
sbatch scripts/hpc/run_md_simulation.slurm

# Check status
squeue -u $USER

# View output
tail -f logs/structbio_JOBID.out
```

### Array Job (Multiple Proteins)
```bash
# Create protein list
cat > data/protein_list.txt <<EOF
1ubq
2lyz
3hfm
EOF

# Submit array job
sbatch scripts/hpc/run_md_array.slurm

# Monitor all tasks
squeue -u $USER
```

### Interactive Session
```bash
# Start interactive GPU session
bash scripts/hpc/interactive_gpu.sh

# Once in session, test:
python examples/mdagent_integration_example.py --backend mdagent
```

## Common SLURM Commands

```bash
# Submit job
sbatch script.slurm

# Check queue
squeue -u $USER

# Cancel job
scancel JOBID

# Cancel all your jobs
scancel -u $USER

# Job details
scontrol show job JOBID

# Job history
sacct -j JOBID --format=JobID,JobName,State,ExitCode,Elapsed

# Check account balance
sshare -U
```

## Monitoring Jobs

### Real-time Log Viewing
```bash
# Follow output
tail -f logs/structbio_JOBID.out

# Check for errors
grep -i error logs/structbio_*.err

# Watch GPU usage (in interactive session)
watch -n 1 nvidia-smi
```

### Job Status
```bash
# All your jobs
squeue -u $USER

# Specific job
squeue -j JOBID

# Detailed info
scontrol show job JOBID
```

## Directory Structure

```
$HOME/
├── StructBioReasoner/
│   ├── config/
│   │   └── protein_config_hpc.yaml  # Edit this!
│   ├── scripts/hpc/
│   │   ├── run_md_simulation.slurm  # Edit account!
│   │   └── run_md_array.slurm
│   └── logs/                        # Job outputs
└── MDAgent/                         # Auto-installed

/scratch/$USER/
├── structbio_temp/                  # Temporary files
└── structbio_output/                # Job outputs

/projects/$USER/
└── structbio_results/               # Permanent results
```

## Configuration

### Minimal HPC Config

Edit `config/protein_config_hpc.yaml`:

```yaml
agents:
  molecular_dynamics:
    enabled: true
    md_backend: "mdagent"
    
    mdagent:
      solvent_model: "explicit"
      force_field: "amber14"
      water_model: "tip3p"
      equil_steps: 50_000
      prod_steps: 10_000_000  # 20 ns
    
    platform: "CUDA"
    
    output_dir: "/scratch/$USER/structbio_output"
```

### Job Script Customization

Edit `scripts/hpc/run_md_simulation.slurm`:

```bash
#SBATCH --account=YOUR_ACCOUNT_HERE    # REQUIRED!
#SBATCH --partition=gpu                # Your GPU partition
#SBATCH --time=24:00:00                # Adjust as needed
#SBATCH --mem=32G                      # Adjust as needed
```

## Troubleshooting

### Job Fails Immediately
```bash
# Check error log
cat logs/structbio_JOBID.err

# Common issues:
# - Wrong account name
# - Wrong partition name
# - Module not found
```

### Out of Memory
```bash
# Increase memory in job script
#SBATCH --mem=64G  # or higher
```

### GPU Not Found
```bash
# Check GPU partition name
sinfo -o "%20P %5a %10l %6D %6t %N"

# Verify GPU request
#SBATCH --gres=gpu:1
```

### Import Errors
```bash
# Check PYTHONPATH
echo $PYTHONPATH

# Should include MDAgent
export PYTHONPATH="${PYTHONPATH}:$HOME/MDAgent"
```

### Module Not Found
```bash
# List available modules
module avail

# Load correct versions
module load python/3.9  # or whatever is available
module load cuda/11.8   # or whatever is available
```

## Performance Tips

### GPU Optimization
```yaml
# In config/protein_config_hpc.yaml
agents:
  molecular_dynamics:
    platform: "CUDA"
    precision: "mixed"  # Faster
    
    mdagent:
      prod_steps: 50_000_000  # 100 ns on GPU
```

### Resource Requests
```bash
# Don't over-request!
# For single protein MD:
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1

# For large systems:
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
```

### Parallel Jobs
```bash
# Submit multiple independent jobs
for protein in 1ubq 2lyz 3hfm; do
    sbatch --export=PROTEIN=$protein scripts/hpc/run_md_simulation.slurm
done
```

## Data Management

### Copy Results Back
```bash
# From HPC to local
scp -r username@hpc:/projects/$USER/structbio_results/ ./results/

# Or use rsync
rsync -avz username@hpc:/projects/$USER/structbio_results/ ./results/
```

### Cleanup Scratch
```bash
# Remove old files (>7 days)
find /scratch/$USER/structbio_* -mtime +7 -delete
```

## Getting Help

### Check System Documentation
```bash
# Most HPC systems have local docs
man sbatch
man squeue

# Or online documentation
# Check your institution's HPC user guide
```

### Test Installation
```bash
cd ~/StructBioReasoner
python scripts/test_mdagent_installation.py
```

### Verify GPU Access
```bash
# In interactive session
srun --partition=gpu --gres=gpu:1 --pty bash
nvidia-smi
```

## Example Workflow

```bash
# 1. Transfer code
rsync -avz StructBioReasoner/ username@hpc:~/StructBioReasoner/

# 2. SSH to HPC
ssh username@hpc

# 3. Setup (first time only)
cd ~/StructBioReasoner
bash scripts/hpc/setup_hpc_environment.sh

# 4. Edit configuration
nano config/protein_config_hpc.yaml

# 5. Edit job script
nano scripts/hpc/run_md_simulation.slurm
# Change: REPLACE_WITH_YOUR_ACCOUNT

# 6. Test in interactive session
bash scripts/hpc/interactive_gpu.sh
# Once in session:
python struct_bio_reasoner.py --mode batch --goal "Test" --count 1
exit

# 7. Submit production job
sbatch scripts/hpc/run_md_simulation.slurm

# 8. Monitor
squeue -u $USER
tail -f logs/structbio_*.out

# 9. Copy results back
scp -r username@hpc:/projects/$USER/structbio_results/ ./
```

## Next Steps

- Read full guide: `docs/HPC_DEPLOYMENT.md`
- Customize configs: `config/protein_config_hpc.yaml`
- Review examples: `examples/mdagent_integration_example.py`
- Check integration guide: `docs/MDAGENT_INTEGRATION_GUIDE.md`

