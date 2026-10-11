import asyncio
import json
import os
import time
import sys
import shutil
import random
import re
import traceback
import logging

class CommsMixin:
    async def broadcast(self, message: dict):
        """Buffers message with monotonic seq and broadcasts to all active clients via asyncio.Queue."""
        async with self._lock:
            self.current_seq += 1
            seq = self.current_seq
            message_with_seq = dict(message)
            message_with_seq["seq"] = seq

            # Always buffer the message regardless of client connection state
            self.message_queue.append({"seq": seq, "msg": message_with_seq})
            if len(self.message_queue) > self.max_queue_size:
                self.message_queue.pop(0)

        payload = json.dumps(message_with_seq)
        
        # Broadcast only to the active task owner or admin (CWE-200)
        is_system_msg = message_with_seq.get("type") in ("system", "agent_stop", "agent_start")
        for client_queue, username in list(self.connected_clients.items()):
            is_owner = self.active_task_owner is None or username == self.active_task_owner or username == "admin"
            if is_system_msg or is_owner:
                try:
                    client_queue.put_nowait(payload)
                except Exception as e:
                    print(f"[AgentTaskManager] Failed to push to client queue: {e}")

    def handle_ack(self, ack_seq: int):
        """Prunes messages from the queue that have been confirmed received by the client."""
        if ack_seq is None:
            return
        # Keep only messages with seq > ack_seq
        self.message_queue = [item for item in self.message_queue if item["seq"] > ack_seq]

    async def sync_client(self, client_queue, last_seq: int = 0):
        """Replays all buffered messages since last_seq to guarantee no message is dropped."""
        try:
            # Find unacked messages since last_seq
            pending = [item["msg"] for item in self.message_queue if item["seq"] > last_seq]
            if pending:
                for msg in pending:
                    await client_queue.put(json.dumps(msg))
            else:
                # If no queue items match (e.g. fresh connection or queue pruned), fallback to state snapshot
                if self.is_running():
                    await client_queue.put(json.dumps({
                        "type": "task_active",
                        "prompt": self.current_prompt,
                        "model": self.current_model,
                        "start_time": self.start_time,
                        "actions": self.actions,
                        "buffered_output": "".join(self.output_buffer),
                        "conversation_id": self.current_conversation_id,
                        "seq": self.current_seq
                    }))
                elif self.last_completed_task:
                    await client_queue.put(json.dumps({
                        "type": "task_last_result",
                        "task": self.last_completed_task,
                        "seq": self.current_seq
                    }))

            # Finally send initial status so the UI knows we are done replaying chunks
            await client_queue.put(json.dumps({
                "type": "init",
                "connected": True,
                "current_seq": self.current_seq,
                "is_running": self.is_running()
            }))
        except Exception as e:
            print(f"[AgentTaskManager] Error syncing client: {e}")

    async def register_client(self, ws):
        self.connected_clients.setdefault(ws, None)

    async def authenticate_client(self, ws, username: str):
        if ws in self.connected_clients:
            self.connected_clients[ws] = username

    async def unregister_client(self, ws):
        self.connected_clients.pop(ws, None)

