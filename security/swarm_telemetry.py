import os
import json
import logging
from datetime import datetime, timezone

LOG_FILE = "/mnt/c/Users/michael/Documents/devcore/logs/swarmflow.jsonl"

def setup_logger():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

class SwarmFlowLogger:
    """
    Implements Swarm Telemetry and Metadata Logging (SwarmFlow) 
    using the Agentic 5-Tuples defined in Module 3.
    """
    @staticmethod
    def log_tuple(modder_id: str, agent_id: str, target_namespace: str, model_tier: str, token_volume: int):
        setup_logger()
        
        # Chrono-Syncing (NTP): Rigid UTC timestamping
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # The Agentic 5-Tuple Record
        record = {
            "timestamp": timestamp,
            "modder_id": modder_id,
            "parent_agent_id": agent_id,
            "target_namespace": target_namespace,
            "model_tier": model_tier,
            "token_volume": token_volume
        }
        
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logging.error(f"[SwarmFlow] Failed to log telemetry: {e}")

    @staticmethod
    def log_intrusion_alert(modder_id: str, agent_id: str, target_namespace: str, reason: str):
        """
        Logs critical NGPF/Raugus Firewall alerts to the Master Alert Queue (MAQ) stream.
        """
        setup_logger()
        timestamp = datetime.now(timezone.utc).isoformat()
        
        record = {
            "timestamp": timestamp,
            "alert_type": "NGPF_INTRUSION",
            "modder_id": modder_id,
            "parent_agent_id": agent_id,
            "target_namespace": target_namespace,
            "reason": reason
        }
        
        alert_file = "/mnt/c/Users/michael/Documents/devcore/logs/master_alert_queue.jsonl"
        try:
            with open(alert_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

