#!/usr/bin/env bash
# Setup script for StructBioReasoner OpenClaw environment
# Installs OpenClaw (Node.js), Jnana (Python), and project dependencies.

set -euo pipefail

DRY_RUN=false

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show commands without executing"
    echo "  --help       Show this help message"
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

# 3. Install Jnana
# NOTE: Jnana requires biomni>=1.0.0 which is not yet on PyPI (latest: 0.0.8).
# We install with --no-deps to avoid the unresolvable biomni dependency.
echo "--- Step 3: Install Jnana (--no-deps to work around biomni version) ---"
run_cmd pip install git+https://github.com/acadev/Jnana.git --no-deps
echo ""

# 4. Install StructBioReasoner with dev deps
echo "--- Step 4: Install StructBioReasoner ---"
run_cmd pip install -e ".[dev]"
echo ""

# 5. Verify installation
echo "--- Step 5: Verify ---"
run_cmd openclaw --version
run_cmd python -c "import struct_bio_reasoner; print('StructBioReasoner OK')"
run_cmd python -c "import json; json.load(open('.openclaw.json')); print('.openclaw.json valid')"
echo ""

echo "=== Setup complete ==="
echo "Run 'openclaw onboard' to complete OpenClaw configuration."
