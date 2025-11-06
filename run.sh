#!/bin/bash

python binder_design_reasoner.py \
    --mode "matt" \
    --goal "Design binders for target protein" \
    --target "Slop" \
    --target-sequence "MKQHKAMIVALIVICITAVVAALVTRKDLCEVHIRTGQTEVAVF" \
    --binder-sequence "MSTGEELQK" \
    --count 3 \
    --strategies "research_expansion" \
    --tournament-matches 5 \
    --config "config/test_binder_config.yaml" \
    --jnana-config "config/test_jnana_config.yaml" \
    --no-knowledge-graph \
    --n-rounds 3 \
    --device "xpu" \
    --output "test/" \
    --log-file "test.log" > test.log 2> test.err
