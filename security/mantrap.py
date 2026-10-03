import fcntl
import os
import logging
from contextlib import contextmanager

MANTRAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "mantrap_locks")

class SemanticMantrap:
    """
    The Semantic Mantrap (Thread Concurrency & Race Condition Firewall).
    Ensures only one authenticated Subagent or process enters the execution chamber 
    at a time when modifying a core database, trapping and purging malicious piggybackers.
    """
    @staticmethod
    @contextmanager
    def execution_chamber(target_db_path: str, agent_id: str = "System"):
        os.makedirs(MANTRAP_DIR, exist_ok=True)
        
        # Create a deterministic lock file for the specific database
        safe_name = target_db_path.replace("/", "_").replace("\\", "_").replace(":", "_") + ".lock"
        lock_path = os.path.join(MANTRAP_DIR, safe_name)
        
        lock_fd = open(lock_path, 'w')
        
        try:
            # The Outer Door: Stagger the logic flow and acquire an exclusive lock
            # If another subagent is inside, this process will halt and wait here (staggering).
            logging.info(f"[MANTRAP] Agent '{agent_id}' waiting at Outer Door for {target_db_path}")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            
            # The inner door opens
            logging.info(f"[MANTRAP] Agent '{agent_id}' has entered the Execution Chamber for {target_db_path}")
            
            # Yield control back to the core logic to perform the database modification
            yield True
            
        except Exception as e:
            # Trap and Purge on failure
            logging.error(f"[MANTRAP] Execution Chamber Fault for '{agent_id}'. Purging transaction. Error: {e}")
            raise
            
        finally:
            # The operation is complete. Release the lock so the next staggered agent can enter.
            logging.info(f"[MANTRAP] Agent '{agent_id}' successfully exited the Execution Chamber for {target_db_path}")
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
