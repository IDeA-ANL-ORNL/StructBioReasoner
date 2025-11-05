# GPU Usage Guide for MDAgent Integration

## Why You're Not Seeing GPU Usage

### The Issue
When you ran Example 1, you saw:
```
Example 1 completed with mdagent backend
```

But **no GPU usage** because:
- ✅ Example 1 only **initializes** the agents
- ❌ Example 1 does **NOT run** a simulation
- 💡 No simulation = No GPU computation

## How MDAgent Integration Works

### Architecture Layers

```
User Request
    ↓
MolecularDynamicsAgent (StructBioReasoner)
    ↓
MDAgentAdapter (Adapter Pattern)
    ↓
Academy Manager
    ↓
MDAgent Components (Builder, Simulator, Coordinator)
    ↓
molecular_simulations library
    ↓
OpenMM
    ↓
CUDA/GPU
```

### What Each Example Does

| Example | What It Does | GPU Usage? |
|---------|--------------|------------|
| Example 1 | Initialize agents only | ❌ No |
| Example 2 | Initialize MDAgent Expert | ❌ No |
| Example 3 | Compare backends (init only) | ❌ No |
| Example 4 | **Run actual simulation** | ✅ **YES!** |

## How to See GPU Usage

### Option 1: Run Example 4 (Recommended)

Example 4 runs an actual simulation:

```bash
# Make sure you have a PDB file
mkdir -p data
cd data
wget https://files.rcsb.org/download/1UBQ.pdb
cd ..

# Run Example 4
python examples/mdagent_integration_example.py --backend mdagent --example 4
```

**In another terminal, monitor GPU:**
```bash
watch -n 0.5 nvidia-smi
```

### Option 2: Run the GPU Test Script

I created a dedicated GPU test script:

```bash
# Terminal 1: Run simulation
python examples/test_gpu_simulation.py

# Terminal 2: Monitor GPU
watch -n 0.5 nvidia-smi
```

### Option 3: Run Example 1 with PDB File

I modified Example 1 to automatically run a simulation if a PDB file exists:

```bash
# Download PDB file
mkdir -p data
cd data
wget https://files.rcsb.org/download/1UBQ.pdb
cd ..

# Run Example 1 (now it will simulate!)
python examples/mdagent_integration_example.py --backend mdagent --example 1
```

## Understanding GPU Usage

### What You'll See

When a simulation is running, `nvidia-smi` will show:

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 525.xx.xx    Driver Version: 525.xx.xx    CUDA Version: 12.0   |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ... Off  | 00000000:01:00.0  On |                  N/A |
| 30%   45C    P2    75W / 250W |   1234MiB /  8192MiB |     85%      Default |
+-------------------------------+----------------------+----------------------+
```

**Key indicators:**
- **GPU-Util**: Should be 50-100% during simulation
- **Memory-Usage**: Will increase when simulation starts
- **Pwr:Usage**: Power draw increases with GPU activity
- **Perf**: Should show P0-P2 (performance state)

### Timeline of GPU Usage

```
1. Initialize agents (Example 1 stops here)
   GPU: 0% ❌ No computation yet

2. Build molecular system
   GPU: 0-10% ⚠️ Minimal usage (CPU task)

3. Energy minimization
   GPU: 50-80% ✅ GPU starts working

4. Equilibration (10,000 steps)
   GPU: 80-100% ✅ Full GPU usage

5. Production MD (500,000+ steps)
   GPU: 80-100% ✅ Full GPU usage (THIS IS WHERE YOU SEE IT!)

6. Analysis
   GPU: 0-20% ⚠️ Mostly CPU task
```

## Checking GPU Availability

### Quick Check

```python
import openmm
from openmm import Platform

# List all platforms
for i in range(Platform.getNumPlatforms()):
    platform = Platform.getPlatform(i)
    print(f"{i}: {platform.getName()}")

# Check for CUDA
try:
    cuda = Platform.getPlatformByName('CUDA')
    print("✅ CUDA available!")
except:
    print("❌ CUDA not available")
```

### Expected Output (with GPU)

```
0: Reference
1: CPU
2: CUDA
3: OpenCL
✅ CUDA available!
```

### Expected Output (without GPU)

```
0: Reference
1: CPU
❌ CUDA not available
```

## Troubleshooting

### GPU Not Being Used

**Check 1: Is CUDA available?**
```bash
python -c "from openmm import Platform; print(Platform.getPlatformByName('CUDA'))"
```

**Check 2: Is OpenMM using CUDA?**
```python
# In your simulation code, add:
print(f"Platform: {simulation.context.getPlatform().getName()}")
```

**Check 3: CUDA toolkit installed?**
```bash
nvidia-smi
nvcc --version
```

### Installing GPU Support

If CUDA is not available:

```bash
# Reinstall OpenMM with CUDA support
conda install -c conda-forge openmm cudatoolkit=11.8
```

### Force GPU Usage

In your config:

```yaml
agents:
  molecular_dynamics:
    platform: "CUDA"  # Force CUDA platform
    precision: "mixed"  # Mixed precision for speed
```

Or in code:

```python
config = {
    "platform": "CUDA",
    "platform_properties": {
        "Precision": "mixed",
        "DeviceIndex": "0"  # Use first GPU
    }
}
```

## Performance Expectations

### CPU vs GPU

| System Size | CPU Speed | GPU Speed (V100) | Speedup |
|-------------|-----------|------------------|---------|
| Small (1K atoms) | 10 ns/day | 100 ns/day | 10x |
| Medium (10K atoms) | 1 ns/day | 50 ns/day | 50x |
| Large (50K atoms) | 0.1 ns/day | 20 ns/day | 200x |

### GPU Types

| GPU | Typical Performance | Use Case |
|-----|---------------------|----------|
| GTX 1080 | 50-100 ns/day | Desktop testing |
| RTX 3090 | 100-200 ns/day | Workstation |
| V100 | 200-500 ns/day | HPC |
| A100 | 500-1000 ns/day | HPC (best) |

## Example: Full Simulation with GPU Monitoring

### Terminal 1: Run Simulation

```bash
python examples/mdagent_integration_example.py --backend mdagent --example 4
```

### Terminal 2: Monitor GPU

```bash
# Real-time monitoring
watch -n 0.5 nvidia-smi

# Or log to file
nvidia-smi dmon -s u -d 1 > gpu_usage.log
```

### Terminal 3: Monitor Process

```bash
# Watch Python process
top -p $(pgrep -f mdagent_integration)

# Or htop for better view
htop -p $(pgrep -f mdagent_integration)
```

## What Happens During Simulation

### Phase 1: Initialization (0-5 seconds)
```
- Loading MDAgent
- Creating Academy manager
- Launching agents
GPU: 0% (no computation)
```

### Phase 2: System Building (5-30 seconds)
```
- Reading PDB file
- Adding hydrogens
- Adding solvent (if explicit)
- Creating force field
GPU: 0-10% (mostly CPU)
```

### Phase 3: Energy Minimization (10-60 seconds)
```
- Minimizing energy
- Relaxing structure
GPU: 50-80% (GPU starts working!)
```

### Phase 4: Equilibration (1-5 minutes)
```
- Heating system
- Equilibrating pressure
- Stabilizing
GPU: 80-100% (full GPU usage!)
```

### Phase 5: Production MD (5-60 minutes)
```
- Running production simulation
- Collecting trajectory
GPU: 80-100% (THIS IS THE MAIN PART!)
```

### Phase 6: Analysis (10-60 seconds)
```
- Calculating RMSD
- Calculating RMSF
- Analyzing trajectory
GPU: 0-20% (mostly CPU)
```

## Summary

### To See GPU Usage:

1. ✅ **Run Example 4** (or modified Example 1 with PDB file)
2. ✅ **Monitor with nvidia-smi** in another terminal
3. ✅ **Wait for production MD phase** (this is where GPU is used most)

### Why Example 1 Showed No GPU Usage:

- ❌ It only initializes agents
- ❌ It doesn't run a simulation
- ❌ No computation = No GPU usage

### Next Steps:

1. Download a PDB file to `data/1ubq.pdb`
2. Run Example 4 or the GPU test script
3. Monitor GPU with `nvidia-smi`
4. See 80-100% GPU utilization during MD phase!

## For HPC Deployment

On your supercomputer, GPU usage will be automatic:
- SLURM job requests GPU: `#SBATCH --gres=gpu:1`
- OpenMM detects CUDA automatically
- Full GPU acceleration for production runs
- Expected: 200-1000 ns/day depending on GPU type

See `docs/HPC_QUICK_START.md` for deployment instructions.

