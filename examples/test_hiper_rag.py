import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add Jnana to path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import gc
import multiprocessing
from queue import PriorityQueue, Queue  # Standard library queues
import time

async def test_hiper_rag_implement():
    from struct_bio_reasoner.core.binder_design_system import BinderDesignSystem
    system = BinderDesignSystem(
        config_path="config/binder_config.yaml",
        jnana_config_path="config/test_jnana_config.yaml",
        enable_agents=['computational_design', 'molecular_dynamics']
    )
    
    await system.start()
    logger.info(f"Initialized system")
    logger.info("\n[STEP 2] Setting research goal...")
    
    research_goal = """
    Design binders for Q9BZQ4|NMNA2_HUMAN Nicotinamide/nicotinic acid mononucleotide adenylyltransferase 2 OS=Homo sapiens which can inhibit cellular processes involved in cancer by mimicking protein-protein binding interfaces. 
    Optimize binding affinity, stability, and mimicking of binding interfaces. Target sequence: 
    MTETTKTHVILLACGSFNPITKGHIQMFERARDYLHKTGRFIVIGGIVSPVHDSYGKQGLVSSRHRLIMCQLAVQNSDWIRVDPWECYQDTWQTTCSVLEHHRDLMKRVTGCILSNVNTPSMTPVIGQPQNETPQPIYQNSNVATKPTAAKILGKVGESLSRICCVRPPVERFTFVDENANLGTVMRYEEIELRILLLCGSDLLESFCIPGLWNEADMEVIVGDFGIVVVPRDAADTDRIMNHSSILRKYKNNIMVVKDDINHPMSVVSSTKSRLALQHGDGHVVDYLSQPVIDYILKSQLYINASG
    
    Goals:
    - Binding affinity < 10 nM
    - Stable complex in MD simulation (RMSD < 3 Å)
    - High success rate (>5% of generated sequences)
    - Mimic binding interface of interacting partner
    """
    
    session_id = await system.set_research_goal(research_goal)
    logger.info(f"✓ Research goal set (session: {session_id})")
    user_prompt = "Identify proteins that are involved with physical interactions with NMNAT-2 in at least one pathway involved in cancer. Return this as a json with this format: {interacting_protein_name: string, interacting_protein_uniprot_id: string}"
    data = {'prompt': user_prompt}
    rag_agent = system.design_agents['rag']
    rag_results = await rag_agent.generate_rag_hypothesis(data)
