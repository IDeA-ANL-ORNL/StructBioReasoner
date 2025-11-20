import gc
import multiprocessing
from queue import PriorityQueue, Queue  # Standard library queues
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_all_queues():
    """Clean up ALL queues and workers"""
    
    print("🧹 Cleaning up multiprocessing resources...\n")
    
    # 1. Find and close all queue objects
    logger.info("1. Finding queue objects...")
    queues_found = 0
    for obj in gc.get_objects():
        # Check for both standard and multiprocessing queues
        if isinstance(obj, (PriorityQueue, Queue)):
            queues_found += 1
            try:
                if hasattr(obj, 'close'):
                    obj.close()
                if hasattr(obj, 'join_thread'):
                    obj.join_thread()
                logger.info(f"   ✓ Closed queue: {type(obj).__name__}")
            except Exception as e:
                logger.info(f"   ✗ Error closing queue: {e}")
    
    logger.info(f"   Total queues closed: {queues_found}\n")
    
    # 2. Terminate active child processes
    logger.info("2. Terminating child processes...")
    active = multiprocessing.active_children()
    for proc in active:
        logger.info(f"   Terminating {proc.name} (PID: {proc.pid})")
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
    
    logger.info(f"   Terminated {len(active)} processes\n")
    
    # 3. Force garbage collection
    logger.info("3. Running garbage collection...")
    gc.collect()
    time.sleep(1)
    
    logger.info("✅ Cleanup complete!")


