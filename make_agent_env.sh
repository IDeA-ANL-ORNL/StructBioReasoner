#!/bin/bash

#ENV=$1

#uv venv $ENV --system-site-packages

# These are already good
cd /lus/flare/projects/FoundEpidem/avasan/IDEAL/Agentics/Jnana
uv pip install -e .

cd /lus/flare/projects/FoundEpidem/avasan/IDEAL/Agentics/StructBioReasoner
uv pip install -e .

cd /lus/flare/projects/FoundEpidem/avasan/IDEAL/Agentics/MDAgent
uv pip install -e .

cd /lus/flare/projects/FoundEpidem/msinclair/github/bindcraft
uv pip install -e .

cd /lus/flare/projects/FoundEpidem/avasan/Software/OpenMM_Install
./install_openmm.sh

uv pip install molecular-simulations rust-simulation-tools dm-tree academy-py

cd /lus/flare/projects/FoundEpidem/msinclair/pkgs/chai-lab
uv pip install .

# Good up to here

uv pip install --no-deps sentence-transformers

cd /lus/flare/projects/FoundEpidem/avasan/IDEAL/Agentics/distllm
uv pip install -e . --no-deps
uv pip install faiss-cpu --no-deps
