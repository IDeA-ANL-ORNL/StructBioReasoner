# StructBioReasoner Usage Guide

## 🎉 **System Status: FULLY OPERATIONAL**

StructBioReasoner is now working perfectly with:
- ✅ **API Key Authentication**: OpenAI API properly configured
- ✅ **Strategy Mapping**: Protein-specific strategies work with ProtoGnosis
- ✅ **Multi-Agent System**: Full tournament-based hypothesis generation
- ✅ **No Biomni Dependency**: Works without biomedical verification system

---

## 🚀 **Usage Modes**

### **1. Batch Mode - Multi-Agent Hypothesis Generation**

Generate multiple hypotheses using the tournament-based multi-agent system:

```bash
# Basic batch generation
python struct_bio_reasoner.py --mode batch --goal "Improve protein thermostability" --count 3

# With specific strategies
python struct_bio_reasoner.py --mode batch \
  --goal "Enhance enzyme activity" \
  --strategies structural_analysis evolutionary_conservation \
  --count 5

# For specific protein
python struct_bio_reasoner.py --mode batch \
  --goal "Design mutations for improved binding" \
  --protein "1ABC" \
  --count 3
```

**Available Strategies:**
- `structural_analysis` → Literature exploration approach
- `evolutionary_conservation` → Scientific debate approach  
- `energetic_analysis` → Assumptions identification approach
- `mutation_design` → Research expansion approach
- `literature_analysis` → Literature exploration approach

### **2. Interactive Mode - Hypothesis Refinement**

Launch interactive mode for iterative hypothesis development:

```bash
python struct_bio_reasoner.py --mode interactive --goal "Protein stability improvement"
```

### **3. Status Mode - System Health Check**

Check system status and configuration:

```bash
python struct_bio_reasoner.py --mode status
```

### **4. Hybrid Mode - Combined Approach**

Combine batch generation with interactive refinement:

```bash
python struct_bio_reasoner.py --mode hybrid \
  --goal "Optimize protein folding" \
  --strategies structural_analysis energetic_analysis \
  --count 3
```

---

## 🧬 **Python API Usage**

### **Basic Usage**

```python
import asyncio
from struct_bio_reasoner import ProteinEngineeringSystem

async def main():
    # Initialize system
    system = ProteinEngineeringSystem(
        config_path="config/protein_config.yaml",
        enable_tools=["biopython", "pymol"],
        enable_agents=["structural", "evolutionary", "energetic", "design"]
    )
    
    # Start system
    await system.start()
    
    # Set research goal
    session_id = await system.set_research_goal("Improve protein thermostability")
    
    # Generate hypotheses
    hypotheses = await system.generate_hypotheses(
        count=3,
        strategies=["structural_analysis", "evolutionary_conservation"]
    )
    
    print(f"Generated {len(hypotheses)} hypotheses")
    for i, hypothesis in enumerate(hypotheses, 1):
        print(f"\nHypothesis {i}:")
        print(f"Title: {hypothesis.title}")
        print(f"Description: {hypothesis.description[:200]}...")
        print(f"Confidence: {hypothesis.confidence_score}")
    
    # Stop system
    await system.stop()

# Run the example
asyncio.run(main())
```

### **Advanced Usage with Protein-Specific Features**

```python
import asyncio
from struct_bio_reasoner import ProteinEngineeringSystem
from struct_bio_reasoner.data.protein_hypothesis import ProteinHypothesis

async def protein_engineering_workflow():
    system = ProteinEngineeringSystem()
    await system.start()
    
    # Set protein-specific research goal
    session_id = await system.set_research_goal(
        "Design mutations to improve thermostability of TEM-1 β-lactamase"
    )
    
    # Generate protein-specific hypotheses
    protein_hypotheses = await system.generate_protein_hypotheses(
        count=5,
        protein_id="1BTL",  # TEM-1 β-lactamase PDB ID
        strategies=["structural_analysis", "evolutionary_conservation", "energetic_analysis"]
    )
    
    # Analyze results
    for hypothesis in protein_hypotheses:
        if isinstance(hypothesis, ProteinHypothesis):
            print(f"\nProtein Hypothesis: {hypothesis.title}")
            print(f"Target Protein: {hypothesis.protein_id}")
            print(f"Mutations: {len(hypothesis.target_mutations)}")
            
            for mutation in hypothesis.target_mutations:
                print(f"  - {mutation.wild_type}{mutation.position}{mutation.mutant}: {mutation.rationale}")
    
    await system.stop()

asyncio.run(protein_engineering_workflow())
```

---

## 🔧 **Configuration Options**

### **System Configuration**

Edit `config/protein_config.yaml`:

```yaml
# Core Jnana integration
jnana:
  config_path: "../Jnana/config/models.yaml"
  enable_protognosis: true
  enable_biomni: false  # Disabled for faster operation
  enable_wisteria_ui: true

# Protein engineering settings
protein_engineering:
  mutation_design:
    max_mutations_per_hypothesis: 5
    consider_conservative_mutations: true
    energy_cutoff_kcal_mol: 2.0

# Available tools
tools:
  pymol:
    enabled: true
    headless_mode: true
  biopython:
    enabled: true
  esm:
    enabled: true
    model_name: "esm2_t33_650M_UR50D"

# Available agents
agents:
  structural_analysis:
    enabled: true
  evolutionary_conservation:
    enabled: true
  energetic_analysis:
    enabled: true
  mutation_design:
    enabled: true
```

### **Model Configuration**

Your OpenAI API key is configured in `.env`:

```bash
OPENAI_API_KEY=your_api_key_here
```

---

## 📊 **Output and Results**

### **Session Files**

Results are saved in `sessions/` directory:
- `jnana_session_YYYYMMDD_HHMMSS.json` - Complete session data
- Contains all generated hypotheses, rankings, and metadata

### **Database Storage**

Persistent storage in `data/jnana.db`:
- Hypothesis history
- Agent states
- Tournament results

---

## 🎯 **Example Workflows**

### **Workflow 1: Enzyme Optimization**

```bash
# Generate hypotheses for enzyme improvement
python struct_bio_reasoner.py --mode batch \
  --goal "Improve catalytic efficiency of β-lactamase" \
  --strategies structural_analysis energetic_analysis mutation_design \
  --count 5

# Results will include:
# - Structural analysis of active site
# - Energy calculations for stability
# - Specific mutation recommendations
```

### **Workflow 2: Protein Stability**

```bash
# Focus on thermostability
python struct_bio_reasoner.py --mode batch \
  --goal "Enhance protein thermostability for industrial applications" \
  --strategies evolutionary_conservation energetic_analysis \
  --count 3

# Results will include:
# - Conservation analysis across species
# - Stability predictions
# - Temperature-resistant mutations
```

### **Workflow 3: Interactive Research**

```bash
# Start interactive session
python struct_bio_reasoner.py --mode interactive \
  --goal "Design novel protein binding sites"

# Then interactively:
# - Refine hypotheses based on feedback
# - Explore different approaches
# - Iterate on promising directions
```

---

## 🚀 **Performance Tips**

1. **Start Small**: Begin with `--count 1-3` for faster results
2. **Choose Strategies**: Select 2-3 relevant strategies instead of all
3. **Use Status Mode**: Check system health with `--mode status`
4. **Monitor Sessions**: Check `sessions/` directory for saved results
5. **API Limits**: Be mindful of OpenAI API usage with large batch sizes

---

## 🎉 **You're Ready to Go!**

StructBioReasoner is now fully operational for protein engineering research. The system combines:

- **Multi-Agent AI**: Tournament-based hypothesis generation
- **Protein Expertise**: Specialized structural, evolutionary, and energetic analysis
- **Flexible Interface**: Command-line and Python API options
- **Persistent Storage**: Session and database management
- **No External Dependencies**: Works without Biomni or other complex systems

Start with simple batch commands and explore the interactive features as you become more familiar with the system!
