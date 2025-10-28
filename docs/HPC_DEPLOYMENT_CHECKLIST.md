# HPC Deployment Checklist

Use this checklist to ensure successful deployment of StructBioReasoner with MDAgent on your supercomputer.

## Pre-Deployment (Local Machine)

### Information Gathering
- [ ] Supercomputer hostname: `_________________`
- [ ] Your username: `_________________`
- [ ] Your account/allocation: `_________________`
- [ ] GPU partition name: `_________________`
- [ ] Available modules (python, cuda, gcc): `_________________`
- [ ] Scratch directory path: `_________________`
- [ ] Project directory path: `_________________`

### Code Preparation
- [ ] All code changes committed
- [ ] Tests passing locally
- [ ] Configuration files reviewed
- [ ] Example data prepared (if needed)

## File Transfer

- [ ] Code transferred to supercomputer
  ```bash
  rsync -avz StructBioReasoner/ username@hpc:~/StructBioReasoner/
  ```
- [ ] Transfer completed successfully
- [ ] File permissions correct

## Initial Setup on Supercomputer

### Environment Setup
- [ ] SSH to supercomputer successful
- [ ] Navigated to StructBioReasoner directory
- [ ] Ran setup script: `bash scripts/hpc/setup_hpc_environment.sh`
- [ ] Setup completed without errors
- [ ] Conda environment created: `structbio_env`
- [ ] Environment activated successfully

### Dependency Verification
- [ ] Python 3.9+ available
- [ ] OpenMM installed
- [ ] CUDA/GPU support available
- [ ] MDAgent cloned
- [ ] MDAgent in PYTHONPATH
- [ ] MDTraj installed (optional)
- [ ] NumPy installed

### Test Installation
- [ ] Ran test script: `python scripts/test_mdagent_installation.py`
- [ ] All required tests passed
- [ ] Optional dependencies noted

## Configuration

### HPC Configuration File
- [ ] Created `config/protein_config_hpc.yaml`
- [ ] Updated output directories:
  - [ ] `output_dir` points to scratch
  - [ ] Logging configured
- [ ] MD backend set to "mdagent"
- [ ] Solvent model configured
- [ ] Simulation parameters set
- [ ] GPU platform configured

### Job Scripts
- [ ] Edited `scripts/hpc/run_md_simulation.slurm`:
  - [ ] Account name updated
  - [ ] Partition name correct
  - [ ] Resource requests appropriate
  - [ ] Time limit set
  - [ ] Module loads correct
  - [ ] Paths updated for your system
- [ ] Edited `scripts/hpc/run_md_array.slurm` (if using):
  - [ ] Same as above
  - [ ] Array parameters configured
- [ ] Edited `scripts/hpc/interactive_gpu.sh`:
  - [ ] Account name updated

## Testing

### Interactive Session Test
- [ ] Started interactive GPU session:
  ```bash
  bash scripts/hpc/interactive_gpu.sh
  ```
- [ ] GPU detected: `nvidia-smi` works
- [ ] Environment activated
- [ ] PYTHONPATH correct
- [ ] Can import MDAgent:
  ```bash
  python -c "from agents import Builder; print('OK')"
  ```
- [ ] Ran quick test:
  ```bash
  python struct_bio_reasoner.py --mode batch --goal "Test" --count 1
  ```
- [ ] Test completed successfully
- [ ] Exited interactive session

### Test Job Submission
- [ ] Created test job with short runtime
- [ ] Submitted test job: `sbatch scripts/hpc/run_md_simulation.slurm`
- [ ] Job accepted by scheduler
- [ ] Job ID noted: `_________________`
- [ ] Job started running
- [ ] Monitored with: `squeue -u $USER`
- [ ] Checked logs: `tail -f logs/structbio_*.out`
- [ ] Job completed successfully
- [ ] Results in expected location
- [ ] No errors in error log

## Production Deployment

### Directory Structure
- [ ] Scratch directories created:
  - [ ] `/scratch/$USER/structbio_temp`
  - [ ] `/scratch/$USER/structbio_output`
  - [ ] `/scratch/$USER/structbio_logs`
- [ ] Project directories created:
  - [ ] `/projects/$USER/structbio_results`
- [ ] Logs directory exists: `logs/`

### Data Preparation
- [ ] Input PDB files transferred (if needed)
- [ ] Protein list created (for array jobs)
- [ ] Data validated

### Job Submission
- [ ] Final configuration reviewed
- [ ] Resource requests optimized
- [ ] Submitted production job(s)
- [ ] Job ID(s) recorded: `_________________`

## Monitoring

### Job Status
- [ ] Set up monitoring:
  ```bash
  watch -n 5 'squeue -u $USER'
  ```
- [ ] Logs being written
- [ ] No immediate errors
- [ ] GPU utilization checked (if possible)

### Resource Usage
- [ ] Memory usage acceptable
- [ ] Time estimate reasonable
- [ ] Disk space sufficient

## Post-Job

### Results Verification
- [ ] Job completed successfully
- [ ] Exit code: 0
- [ ] Results in project directory
- [ ] Output files present:
  - [ ] Hypothesis files
  - [ ] Session files
  - [ ] Log files
- [ ] Results look correct

### Data Management
- [ ] Results copied to local machine (if needed)
- [ ] Scratch space cleaned up
- [ ] Important files backed up

## Optimization (After First Jobs)

### Performance Review
- [ ] Actual runtime vs requested: `_________________`
- [ ] Memory usage vs requested: `_________________`
- [ ] GPU utilization: `_________________`
- [ ] Identified bottlenecks: `_________________`

### Adjustments Made
- [ ] Resource requests optimized
- [ ] Configuration tuned
- [ ] Workflow improved

## Documentation

### Record Keeping
- [ ] Successful configuration saved
- [ ] Job parameters documented
- [ ] Performance metrics recorded
- [ ] Issues and solutions noted

### Team Communication
- [ ] Deployment documented for team
- [ ] Best practices shared
- [ ] Common issues documented

## Troubleshooting Checklist

If something goes wrong, check:

### Job Won't Start
- [ ] Account name correct
- [ ] Partition exists and accessible
- [ ] Resource request reasonable
- [ ] Allocation has hours remaining

### Job Fails Immediately
- [ ] Error log checked
- [ ] Module loads successful
- [ ] Conda environment activates
- [ ] PYTHONPATH set correctly
- [ ] Input files exist

### Job Runs But Fails
- [ ] Sufficient memory
- [ ] Sufficient time
- [ ] Disk space available
- [ ] GPU accessible
- [ ] Configuration valid

### Import Errors
- [ ] MDAgent in PYTHONPATH
- [ ] All dependencies installed
- [ ] Correct Python version
- [ ] Conda environment activated

### GPU Not Found
- [ ] GPU partition correct
- [ ] GPU requested in job script
- [ ] CUDA module loaded
- [ ] GPU available on node

## Maintenance

### Regular Tasks
- [ ] Clean scratch space weekly
- [ ] Monitor disk usage
- [ ] Update code as needed
- [ ] Review job efficiency monthly

### Updates
- [ ] Pull latest code changes
- [ ] Update dependencies if needed
- [ ] Test after updates
- [ ] Document changes

## Sign-Off

### Deployment Complete
- [ ] All tests passed
- [ ] Production jobs running
- [ ] Monitoring in place
- [ ] Documentation complete
- [ ] Team notified

**Deployed by:** `_________________`  
**Date:** `_________________`  
**Supercomputer:** `_________________`  
**Notes:** `_________________`

---

## Quick Reference

### Essential Commands
```bash
# Activate environment
conda activate structbio_env

# Submit job
sbatch scripts/hpc/run_md_simulation.slurm

# Check queue
squeue -u $USER

# View logs
tail -f logs/structbio_*.out

# Cancel job
scancel JOBID

# Interactive session
bash scripts/hpc/interactive_gpu.sh
```

### Important Paths
```
Code:     ~/StructBioReasoner
MDAgent:  ~/MDAgent
Scratch:  /scratch/$USER/structbio_*
Results:  /projects/$USER/structbio_results
Logs:     ~/StructBioReasoner/logs
```

### Support
- Quick Start: `docs/HPC_QUICK_START.md`
- Full Guide: `docs/HPC_DEPLOYMENT.md`
- Scripts: `scripts/hpc/README.md`
- HPC Support: `_________________` (your institution)

