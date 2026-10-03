import logging
import json
import os
import sys
import warnings
from datetime import datetime, timezone

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "devcore_master.jsonl")

class SIEMJsonFormatter(logging.Formatter):
    def format(self, record):
        if record.name.startswith("httpx") or record.name.startswith("httpcore"):
            return ""
            
        # Determine Advanced Event Category based on logger, level, and message content
        event_category = "SYSTEM"
        msg_lower = record.getMessage().lower()
        
        if record.levelname in ["CRITICAL", "FATAL"] or record.exc_info:
            event_category = "FAULT"
        elif "startup" in msg_lower or "initialized" in msg_lower or "boot" in msg_lower:
            event_category = "STARTUP"
        elif "agent" in record.name or "swarm" in record.name or "tool" in msg_lower or "token" in msg_lower:
            event_category = "AGENTIC"
        elif "login" in msg_lower or "token" in msg_lower or "auth" in msg_lower or "role" in msg_lower:
            event_category = "AUTH"
        elif "security" in record.name or "intrusion" in msg_lower or "raugus" in msg_lower or "unauthorized" in msg_lower:
            event_category = "SECURITY_AUDIT"
        elif record.levelname == "WARNING":
            event_category = "WARNING"
        elif "quart" in record.name or "hypercorn" in record.name or "websocket" in msg_lower:
            event_category = "NETWORK"

            
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "category": event_category,
            "logger": record.name,
            "module": record.module,
            "message": record.getMessage()
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("Unhandled system fault (Crash)", exc_info=(exc_type, exc_value, exc_traceback))

def handle_warnings(message, category, filename, lineno, file=None, line=None):
    logging.warning(f"{category.__name__}: {message} ({filename}:{lineno})")

def init_central_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(SIEMJsonFormatter())
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(SIEMJsonFormatter())
    logger.addHandler(console_handler)

    # 1. Catch all hard OS/Python crashes (FAULTS)
    sys.excepthook = handle_unhandled_exception
    
    # 2. Catch all internal Python warnings (WARNINGS)
    warnings.showwarning = handle_warnings

    logging.info("Central SIEM Logger Initialized. Swarm Onion architecture is active.")

if __name__ == "__main__":
    init_central_logging()
    logging.info("Testing central SIEM logger setup.")
