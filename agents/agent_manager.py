from .mixins.comms_mixin import CommsMixin
from .mixins.execution_mixin import ExecutionMixin
from .mixins.transcript_mixin import TranscriptMixin
import logging
import asyncio
import json
import os
import time
import sys
import shutil
import random
import re
import traceback

class AgentTaskManager(CommsMixin, ExecutionMixin, TranscriptMixin):
    """
    Manages Antigravity background tasks independently of client WebSocket connections.
    Uses an ACK-backed message queue to guarantee zero message loss:
      - Every event is assigned a monotonic sequence number (seq).
      - All broadcast events are retained in a server buffer until explicitly ACKed by the client.
      - Reconnecting clients can replay all unacknowledged events seamlessly.
      - Periodic heartbeats prevent connection drops on WSL 2 and high-latency networks.
    """
    def __init__(self, project_manager=None):
        self.project_manager = project_manager
        self.active_task: asyncio.Task = None
        self.active_proc: asyncio.subprocess.Process = None
        self.current_prompt: str = None
        self.current_model: str = "Gemini 3.8 Flash (Low)"
        self.start_time: float = None
        self.output_buffer: list = []
        self.actions: list = []
        self.last_completed_task: dict = None
        self.connected_clients: dict = {}
        self.active_task_owner: str = None
        self.current_conversation_id: str = None
        
        # Guaranteed Delivery & ACK Queue
        self.current_seq: int = 0
        self.message_queue: list = []  # [{ "seq": int, "msg": dict }]
        self.max_queue_size: int = 1000
        self._lock = asyncio.Lock()
        self._local_sec = None


        self.rate_limits = {}  # type: dict
        


    @property
    def active_task_id(self):
        return self.active_task
        
    @active_task_id.setter
    def active_task_id(self, val):
        self.active_task = val


    def reinit(self, project_manager=None):
        """Re-initializes state while preserving client connections and pending queue."""
        if project_manager:
            self.project_manager = project_manager
        self.output_buffer = []
        self.actions = []

    def is_running(self) -> bool:
        return self.active_proc is not None and self.active_proc.returncode is None




        # Client will send its own sync message with last_seq; don't sync automatically to avoid duplicate seq=0 broadcast.
        






    


