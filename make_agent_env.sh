#!/bin/bash

ENV=$1

uv venv $ENV --system-site-packages

cd /flare/FoundEpidem/msinclair/github/Jnana
uv pip install -e .

cd ../StructBioReasoner
uv pip install -e .

cd ../MDAgent
uv pip install -e .

cd ../bindcraft
uv pip install -e .

cd ../../pkgs/openmm/build
./install_openmm.sh

uv pip install molecular-simulations rust-simulation-tools dm-tree academy-py

cd ../../chai-lab
uv pip install -e .

# Good up to here

uv pip install --no-deps sentence-transformers

cd ../distllm
uv pip install -e . --no-deps
