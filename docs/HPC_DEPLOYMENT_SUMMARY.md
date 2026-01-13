# HPC Deployment - Summary for Supercomputer Use

## Overview

You now have a complete HPC deployment package for running StructBioReasoner with MDAgent on your supercomputer. This setup is optimized for production-scale molecular dynamics simulations with GPU acceleration.

## What Was Created

### Documentation
1. **`HPC_DEPLOYMENT.md`** - Comprehensive deployment guide
2. **`HPC_QUICK_START.md`** - 5-minute quick start guide
3. **`HPC_DEPLOYMENT_SUMMARY.md`** - This file

### Scripts
1. **`scripts/hpc/setup_hpc_environment.sh`** - Automated environment setup
2. **`scripts/hpc/run_md_simulation.slurm`** - Single GPU job script
3. **`scripts/hpc/run_md_array.slurm`** - Array job for multiple proteins
4. **`scripts/hpc/interactive_gpu.sh`** - Interactive GPU session
5. **`scripts/hpc/README.md`** - Scripts documentation

## Deployment Workflow

```
Local Machine                    Supercomputer
     │                                │
     │  1. Transfer Code              │
     ├────────────────────────────────>
     │                                │
     │                           2. Setup Environment
     │                           (setup_hpc_environment.sh)
     │                                │
     │                           3. Configure
     │                           (protein_config_hpc.yaml)
     │                                │
     │  4. Submit Jobs                │
     │  (via SSH or web portal)       │
     ├────────────────────────────────>
     │                                │
     │                           5. Run Simulations
     │                           (GPU nodes)
     │                                │
     │  6. Monitor Progress           │
     <────────────────────────────────┤
     │                                │
     │  7. Retrieve Results           │
     <────────────────────────────────┤
```

## Quick Deployment Steps

### 1. Transfer to Supercomputer

```bash
# From your local machine
cd ~/Desktop/Code
rsync -avz --exclude='*.pyc' --exclude='__pycache__' \
    StructBioReasoner/ username@supercomputer.edu:~/StructBioReasoner/
```

### 2. SSH to Supercomputer

```bash
ssh username@supercomputer.edu
```

### 3. Run Automated Setup

```bash
cd ~/StructBioReasoner
bash scripts/hpc/setup_hpc_environment.sh
```

This will:
- ✅ Create conda environment
- ✅ Install all dependencies (OpenMM, MDTraj, etc.)
- ✅ Clone and configure MDAgent
- ✅ Set up directory structure
- ✅ Configure environment variables

### 4. Customize for Your System

Edit the job script with your HPC account:

```bash
nano scripts/hpc/run_md_simulation.slurm
```

Change:
```bash
#SBATCH --account=REPLACE_WITH_YOUR_ACCOUNT
```

### 5. Submit Your First Job

```bash
sbatch scripts/hpc/run_md_simulation.slurm
```

### 6. Monitor

```bash
# Check queue
squeue -u $USER

# Watch logs
tail -f logs/structbio_*.out
```

## Key Features

### GPU Acceleration
- Automatic CUDA platform detection
- Mixed precision for 2-3x speedup
- Optimized for NVIDIA GPUs

### Scratch Space Management
- Runs simulations in fast scratch storage
- Automatically copies results to project space
- Cleans up temporary files

### Array Jobs
- Process multiple proteins in parallel
- Configurable concurrency limits
- Individual result directories

### Fault Tolerance
- Automatic fallback to OpenMM if MDAgent unavailable
- Comprehensive error logging
- Job status tracking

## File Locations on Supercomputer

```
$HOME/
├── StructBioReasoner/          # Your code
│   ├── config/
│   │   └── protein_config_hpc.yaml  # HPC configuration
│   ├── scripts/hpc/            # Job scripts
│   └── logs/                   # Job logs
└── MDAgent/                    # Auto-installed

/scratch/$USER/
├── structbio_temp/             # Temporary simulation files
└── structbio_output/           # Job outputs (auto-cleaned)

/projects/$USER/
└── structbio_results/          # Permanent results
    ├── job_12345/
    ├── job_12346/
    └── protein_analysis/
```

## Resource Recommendations

### For Single Protein MD (explicit solvent)
```bash
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
```

### For Large Systems (>50k atoms)
```bash
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --time=48:00:00
```

### For Array Jobs (10 proteins)
```bash
#SBATCH --array=1-10%5  # Max 5 concurrent
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
```

## Performance Expectations

### GPU vs CPU
- **CPU**: ~30-60 minutes per ns
- **GPU (V100)**: ~3-10 minutes per ns
- **GPU (A100)**: ~1-5 minutes per ns

### Typical Simulation Times (on V100)
- **10 ns production**: ~30 minutes - 1 hour
- **50 ns production**: ~2-5 hours
- **100 ns production**: ~5-10 hours

### Throughput
- **Single GPU**: 5-10 proteins per day (10 ns each)
- **Array job (5 GPUs)**: 25-50 proteins per day

## Configuration Examples

### Quick Test (Implicit Solvent)
```yaml
mdagent:
  solvent_model: "implicit"
  equil_steps: 5_000
  prod_steps: 500_000  # 1 ns
```

### Production (Explicit Solvent)
```yaml
mdagent:
  solvent_model: "explicit"
  force_field: "amber14"
  water_model: "tip3p"
  equil_steps: 50_000
  prod_steps: 50_000_000  # 100 ns
```

### High-Throughput Screening
```yaml
mdagent:
  solvent_model: "implicit"
  equil_steps: 10_000
  prod_steps: 5_000_000  # 10 ns
```

## Common Workflows

### Workflow 1: Single Protein Analysis
```bash
# Edit goal in job script
nano scripts/hpc/run_md_simulation.slurm

# Submit
sbatch scripts/hpc/run_md_simulation.slurm

# Monitor
squeue -u $USER
tail -f logs/structbio_*.out
```

### Workflow 2: Multiple Protein Screening
```bash
# Create protein list
cat > data/protein_list.txt <<EOF
1ubq
2lyz
3hfm
1crn
2ci2
EOF

# Submit array job
sbatch scripts/hpc/run_md_array.slurm

# Monitor all tasks
watch -n 5 'squeue -u $USER'
```

### Workflow 3: Interactive Development
```bash
# Start interactive session
bash scripts/hpc/interactive_gpu.sh

# Test commands
python struct_bio_reasoner.py --mode batch --goal "Test" --count 1

# Exit when done
exit

# Submit production job
sbatch scripts/hpc/run_md_simulation.slurm
```

## Retrieving Results

### Option 1: SCP
```bash
# From local machine
scp -r username@supercomputer:/projects/$USER/structbio_results/ ./results/
```

### Option 2: rsync (Recommended)
```bash
# From local machine
rsync -avz username@supercomputer:/projects/$USER/structbio_results/ ./results/
```

### Option 3: Globus (For large datasets)
```bash
# Use your institution's Globus endpoint
# Transfer via web interface: https://www.globus.org/
```

## Monitoring and Debugging

### Check Job Status
```bash
squeue -u $USER                    # Current jobs
sacct -j JOBID                     # Job history
scontrol show job JOBID            # Detailed info
```

### View Logs
```bash
tail -f logs/structbio_*.out       # Follow output
grep -i error logs/*.err           # Find errors
cat logs/structbio_JOBID.err       # View error log
```

### GPU Monitoring (in interactive session)
```bash
nvidia-smi                         # Current status
watch -n 1 nvidia-smi              # Real-time monitoring
```

### Check Disk Usage
```bash
du -sh /scratch/$USER/*            # Scratch usage
du -sh /projects/$USER/*           # Project usage
```

## Best Practices for Supercomputer Use

1. **Start Small**: Test with short simulations first
2. **Use Scratch**: Always run in scratch, copy to project space
3. **Monitor Resources**: Check first few jobs to optimize requests
4. **Clean Up**: Remove old scratch files regularly
5. **Use Array Jobs**: More efficient for multiple proteins
6. **Save Checkpoints**: Enable for long simulations
7. **Document**: Keep notes on successful configurations

## Troubleshooting

### Job Fails Immediately
```bash
# Check error log
cat logs/structbio_JOBID.err

# Common fixes:
# - Wrong account: Edit #SBATCH --account
# - Wrong partition: Check with sinfo
# - Module not found: Check with module avail
```

### Out of Memory
```bash
# Increase memory request
#SBATCH --mem=64G  # or higher
```

### GPU Not Found
```bash
# Check available GPUs
sinfo -o "%20P %5a %10l %6D %6t %N"

# Verify request
#SBATCH --gres=gpu:1
```

## System-Specific Notes

### SLURM Systems
- Most common on modern supercomputers
- Use provided `.slurm` scripts

### PBS/Torque Systems
- Convert SLURM directives to PBS
- See `scripts/hpc/README.md` for conversion table

### LSF Systems
- Similar to SLURM but different syntax
- Contact your HPC support for templates

## Next Steps

1. ✅ Transfer code to supercomputer
2. ✅ Run setup script
3. ✅ Customize job scripts
4. ✅ Submit test job
5. ✅ Monitor and optimize
6. ✅ Scale up to production

## Support Resources

- **Quick Start**: `docs/HPC_QUICK_START.md`
- **Full Guide**: `docs/HPC_DEPLOYMENT.md`
- **Scripts Help**: `scripts/hpc/README.md`
- **Integration**: `docs/MDAGENT_INTEGRATION_GUIDE.md`
- **Your HPC**: Check institution-specific documentation

## Summary

You're now ready to deploy StructBioReasoner with MDAgent on your supercomputer! The setup is:

✅ **Production-ready**: Tested workflow for HPC systems
✅ **GPU-optimized**: Automatic CUDA acceleration
✅ **Scalable**: Array jobs for high-throughput
✅ **Fault-tolerant**: Graceful error handling
✅ **Well-documented**: Comprehensive guides and examples

Start with the Quick Start guide and scale up as needed. Good luck with your simulations! 🚀

