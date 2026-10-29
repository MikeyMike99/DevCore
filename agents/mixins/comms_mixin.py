import asyncio
import json
import logging
import time

class CommsMixin:
    """Provides non-blocking direct frame broadcasting to connected WebSockets.
    Eliminates monotonic sequence numbers, ACK throttling, and chunk replay queues.
    """

    async def broadcast(self, message: dict):
        msg_type = message.get("type")
        if hasattr(self, "message_queue") and isinstance(self.message_queue, list):
            self.current_seq = getattr(self, "current_seq", 0) + 1
            self.message_queue.append({"seq": self.current_seq, "msg": message})
            max_q = getattr(self, "max_queue_size", 1000)
            if len(self.message_queue) > max_q:
                del self.message_queue[:-max_q]
        payload = json.dumps(message)
        is_system_msg = msg_type in ("system", "agent_stop", "agent_start", "heartbeat", "init_conv_id", "model_fallback")
        for client_queue, username in list(self.connected_clients.items()):
            is_owner = self.active_task_owner is None or username == self.active_task_owner or username == "admin"
            if is_system_msg or is_owner:
                try:
                    client_queue.put_nowait(payload)
                except Exception:
                    pass

    def handle_ack(self, ack_seq: int = None):
        pass

    async def sync_client(self, client_queue, last_seq: int = 0):
        try:
            if self.is_running():
                latest_act = self.actions[-1] if getattr(self, "actions", None) else None
                elapsed = round(time.time() - self.start_time, 1) if getattr(self, "start_time", None) else 0
                await client_queue.put(json.dumps({
                    "type": "task_active",
                    "status": "running",
                    "prompt": getattr(self, "current_prompt", ""),
                    "model": getattr(self, "current_model", ""),
                    "start_time": getattr(self, "start_time", 0),
                    "elapsed": elapsed,
                    "latest_action": latest_act,
                    "actions_count": len(self.actions) if getattr(self, "actions", None) else 0,
                    "conversation_id": getattr(self, "current_conversation_id", None),
                    "is_running": True
                }))

            await client_queue.put(json.dumps({
                "type": "init",
                "connected": True,
                "is_running": self.is_running()
            }))
        except Exception as e:
            logging.error(f"[CommsMixin] Error syncing client: {e}")

    async def register_client(self, ws):
        self.connected_clients.setdefault(ws, None)

    async def authenticate_client(self, ws, username: str):
        if ws in self.connected_clients:
            self.connected_clients[ws] = username

    async def unregister_client(self, ws):
        self.connected_clients.pop(ws, None)
