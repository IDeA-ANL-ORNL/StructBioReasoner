#!/usr/bin/env bash
# Setup script for StructBioReasoner OpenClaw environment
# Installs OpenClaw (Node.js), Jnana (Python), and project dependencies.

set -euo pipefail

DRY_RUN=false
JNANA_DIR="${JNANA_DIR:-./Jnana}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show commands without executing"
    echo "  --help       Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  JNANA_DIR    Directory for Jnana clone (default: ./Jnana)"
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] $*"
    else
        echo "+ $*"
        "$@"
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

echo "=== StructBioReasoner OpenClaw Setup ==="
echo ""

# 1. Check Node.js
echo "--- Step 1: Check Node.js (>= 22 required) ---"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    echo "Found Node.js v${NODE_VERSION}"
    if [ "$NODE_MAJOR" -lt 22 ]; then
        echo "WARNING: Node.js >= 22 required. Current: v${NODE_VERSION}"
        echo "Please upgrade Node.js before continuing."
    fi
else
    echo "WARNING: Node.js not found. Install Node.js >= 22 first."
    echo "  https://nodejs.org/"
fi
echo ""

# 2. Install OpenClaw
echo "--- Step 2: Install OpenClaw ---"
run_cmd npm install -g openclaw@latest
echo ""

# 3. Clone and install Jnana
echo "--- Step 3: Install Jnana ---"
if [ ! -d "$JNANA_DIR" ]; then
    run_cmd git clone https://github.com/acadev/Jnana.git "$JNANA_DIR"
else
    echo "Jnana directory already exists at $JNANA_DIR"
fi
run_cmd pip install -e "$JNANA_DIR"
echo ""

# 4. Install StructBioReasoner with optional deps
echo "--- Step 4: Install StructBioReasoner ---"
run_cmd pip install -e ".[jnana,dev]"
echo ""

# 5. Verify installation
echo "--- Step 5: Verify ---"
run_cmd openclaw --version
run_cmd python -c "import struct_bio_reasoner; print('StructBioReasoner OK')"
run_cmd python -c "import json; json.load(open('.openclaw.json')); print('.openclaw.json valid')"
echo ""

echo "=== Setup complete ==="
echo "Run 'openclaw onboard' to complete OpenClaw configuration."
