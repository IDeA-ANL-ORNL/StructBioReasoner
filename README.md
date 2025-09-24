# 🧬 StructBioReasoner

**AI-Powered Protein Engineering with Multi-Agent Reasoning and PyMOL Visualization**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyMOL Integration](https://img.shields.io/badge/PyMOL-Integrated-green.svg)](https://pymol.org/)
[![AI Powered](https://img.shields.io/badge/AI-Multi--Agent-purple.svg)](https://openai.com/)

> **A comprehensive AI system for protein engineering that combines structural biology insights, multi-agent reasoning, and advanced visualization capabilities.**

## 🎯 Overview

StructBioReasoner is a cutting-edge AI-powered system for protein engineering that integrates:

- **🤖 Multi-Agent AI System**: ProtoGnosis tournament-based hypothesis generation
- **🧬 PyMOL Integration**: Publication-quality protein structure visualization  
- **📊 Predictive Modeling**: Quantitative thermodynamic and structural predictions
- **🔬 Literature Integration**: Knowledge-driven mutation design
- **⚡ Real-time Analysis**: Interactive and batch processing modes

## ✨ Key Features

### 🧠 **AI-Powered Hypothesis Generation**
- Multi-agent tournament system with 5 generation agents
- Protein-specific strategies (structural, evolutionary, energetic, design)
- Automatic hypothesis ranking and evaluation
- Session management with persistent storage

### 🎨 **Advanced Visualization**
- **PyMOL Integration**: Homebrew, Python module, and command-line interfaces
- **Multiple Styles**: Cartoon, surface, sticks, spheres representations
- **Mutation Highlighting**: Automatic identification and coloring of mutation sites
- **Publication Quality**: High-resolution images (1600x1200) suitable for research

### 📈 **Predictive Capabilities**
- **Thermostability Predictions**: ΔΔG and ΔTm calculations
- **Structural Analysis**: Core stability, surface interactions, loop rigidification
- **Biophysical Modeling**: Hydrophobic packing, electrostatic optimization
- **Literature Validation**: Evidence-based mutation recommendations

### 🔄 **Multiple Operation Modes**
- **Interactive Mode**: Real-time hypothesis refinement
- **Batch Mode**: High-throughput hypothesis generation
- **Hybrid Mode**: Combined batch generation with interactive refinement
- **Status Mode**: System health and capability checking

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd StructBioReasoner

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your OpenAI API key
```

### Basic Usage

```bash
# Check system status
python struct_bio_reasoner.py --mode status

# Generate protein engineering hypotheses
python struct_bio_reasoner.py --mode batch \
  --goal "Design thermostable mutations for enzyme optimization" \
  --count 3

# Interactive hypothesis refinement
python struct_bio_reasoner.py --mode interactive \
  --goal "Improve protein stability"
```

### 🧬 **Ubiquitin Thermostability Demo**

Run our comprehensive demonstration:

```bash
python examples/ubiquitin_thermostability_design.py
```

**Results:**
- ✅ 4 beneficial mutations identified (T11I, Q27E, Q48E, D36E)
- ✅ Average predicted stabilization: 0.93 kcal/mol  
- ✅ Estimated melting temperature increase: 2.3°C
- ✅ Publication-quality visualizations generated

## 📊 **Demonstrated Capabilities**

### **🎯 Successful Ubiquitin Engineering**
Our system successfully designed thermostability-enhancing mutations for ubiquitin:

| Mutation | ΔΔG (kcal/mol) | Rationale |
|----------|----------------|-----------|
| **T11I** | 1.3 | Hydrophobic core stabilization |
| **Q27E** | 0.7 | Salt bridge formation |
| **Q48E** | 0.9 | Surface electrostatics |
| **D36E** | 0.9 | Hydrogen bonding optimization |

### **📈 Performance Metrics**
- **Hypothesis Generation**: 10 hypotheses in ~3 minutes
- **Tournament Evaluation**: 15 matches completed successfully  
- **Visualization**: 4 high-quality images (1.4MB total)
- **Prediction Accuracy**: Literature-validated mutation strategies

## 🛠️ **System Architecture**

### **Core Components**
- **`struct_bio_reasoner/`**: Main system modules
  - `core/`: Protein engineering system and knowledge foundation
  - `agents/`: Specialized analysis agents (structural, evolutionary, energetic)
  - `tools/`: PyMOL wrapper, BioPython utilities
- **`examples/`**: Demonstration scripts and tutorials
- **`docs/`**: Comprehensive documentation and guides
- **`config/`**: System configuration files

### **AI Integration**
- **ProtoGnosis**: Multi-agent hypothesis generation system
- **Jnana Framework**: Knowledge management and reasoning
- **OpenAI GPT-4**: Natural language processing and analysis
- **Tournament System**: Competitive hypothesis evaluation

## 📚 **Documentation**

- **[PyMOL Integration Guide](docs/PYMOL_INTEGRATION_GUIDE.md)**: Complete PyMOL setup and usage
- **[Usage Guide](docs/USAGE_GUIDE.md)**: Comprehensive system usage instructions  
- **[Ubiquitin Results](docs/UBIQUITIN_THERMOSTABILITY_RESULTS.md)**: Detailed analysis of thermostability design
- **[No-Biomni Setup](docs/NO_BIOMNI_SETUP.md)**: Standalone system configuration

## 🔧 **Requirements**

### **Core Dependencies**
- **Python 3.8+**
- **OpenAI API key** (for AI-powered analysis)
- **PyMOL** (for structure visualization)
- **BioPython** (for structural analysis)
- **Matplotlib** (for plotting and analysis)

### **System Status**
```bash
python struct_bio_reasoner.py --mode status
```
Expected output:
```
✓ pymol          # PyMOL visualization available
✓ biopython      # Structural analysis available  
✓ esm            # Protein language models available
```

## 🎨 **Example Outputs**

### **Generated Visualizations**
- **Protein Structures**: Wild-type and mutated protein visualizations
- **Mutation Highlights**: Color-coded mutation site identification
- **Predictive Plots**: 4-panel thermostability analysis charts
- **Surface Representations**: Molecular surface with mutation accessibility

### **Quantitative Predictions**
- **ΔΔG Values**: Thermodynamic stability predictions
- **ΔTm Estimates**: Melting temperature changes
- **Success Rates**: Percentage of beneficial mutations identified
- **Regional Analysis**: Structural region-specific effects

## 🤝 **Contributing**

We welcome contributions! Please see our contributing guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit changes**: `git commit -m 'Add amazing feature'`
4. **Push to branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- **Jnana Framework**: Multi-agent reasoning system
- **ProtoGnosis**: Hypothesis generation and tournament evaluation
- **PyMOL**: Molecular visualization and analysis
- **OpenAI**: GPT-4 language model integration
- **BioPython**: Structural biology tools and utilities

## 📞 **Support**

- **Issues**: [GitHub Issues](../../issues)
- **Documentation**: [docs/](docs/)
- **Examples**: [examples/](examples/)

---

**🧬 Ready to revolutionize protein engineering with AI? Get started with StructBioReasoner today!** 🚀
