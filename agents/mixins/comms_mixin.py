import asyncio
import contextvars
import json
import logging
import os
import sys as _sys
import time
from pathlib import Path

_existing_cm = _sys.modules.get(__name__)
_TASK_OWNER_CTX = getattr(_existing_cm, "_TASK_OWNER_CTX", None) or contextvars.ContextVar("devcore_task_owner", default=None)


def _get_shared_stream_file() -> Path:
    plugin_dir = Path(__file__).resolve().parent.parent.parent
    rt_dir = plugin_dir / ".runtime"
    try:
        rt_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return rt_dir / "stream_events.json"


def _normalize_base_owner(owner: str) -> str:
    if not owner:
        return ""
    base = str(owner).split("::", 1)[0].strip()
    if base.lower() in ("admin", "michael (admin)", "michael"):
        return "Michael (Admin)"
    return base


def _owners_match(client_owner: str, target_owner: str) -> bool:
    if not target_owner:
        return True
    if not client_owner:
        return _normalize_base_owner(target_owner) == "Michael (Admin)"
    if client_owner == target_owner:
        return True
    if "::" in client_owner and "::" in target_owner:
        c_base, c_cid = client_owner.split("::", 1)
        t_base, t_cid = target_owner.split("::", 1)
        return _normalize_base_owner(c_base) == _normalize_base_owner(t_base) and c_cid == t_cid
    return _normalize_base_owner(client_owner) == _normalize_base_owner(target_owner)


class CommsMixin:
    """Provides per-session isolated frame broadcasting to WebSockets and shared sequence queue."""

    def set_task_context(self, owner: str):
        if owner:
            _TASK_OWNER_CTX.set(owner)
        return owner

    def get_task_context(self):
        return _TASK_OWNER_CTX.get()

    async def broadcast(self, message: dict):
        target_owner = message.get("owner") or _TASK_OWNER_CTX.get() or getattr(self, "active_task_owner", None)
        self.current_seq = getattr(self, "current_seq", 0) + 1
        seq_val = self.current_seq
        msg_copy = dict(message)
        msg_copy["seq"] = seq_val
        if target_owner and "owner" not in msg_copy:
            msg_copy["owner"] = target_owner

        if hasattr(self, "message_queue") and isinstance(self.message_queue, list):
            self.message_queue.append({"seq": seq_val, "owner": target_owner, "msg": msg_copy, "ts": time.time()})
            max_q = getattr(self, "max_queue_size", 1000)
            if len(self.message_queue) > max_q:
                del self.message_queue[:-max_q]

            try:
                sf = _get_shared_stream_file()
                recent = self.message_queue[-150:]
                tmp_sf = sf.with_suffix(".tmp")
                tmp_sf.write_text(json.dumps(recent), encoding="utf-8")
                os.replace(tmp_sf, sf)
            except Exception:
                pass

        payload = json.dumps(msg_copy)
        for client_queue, client_owner in list(self.connected_clients.items()):
            if target_owner is None or _owners_match(client_owner, target_owner):
                try:
                    client_queue.put_nowait(payload)
                except Exception:
                    pass

    def handle_ack(self, ack_seq: int = None):
        pass

    async def sync_client(self, client_queue, last_seq: int = 0):
        try:
            client_owner = self.connected_clients.get(client_queue)
            is_user_running = self.is_running(client_owner) if client_owner else False
            if is_user_running:
                slot = self._get_slot(client_owner) if hasattr(self, "_get_slot") else {}
                actions = slot.get("actions") or []
                latest_act = actions[-1] if actions else None
                start_t = slot.get("start_time")
                elapsed = round(time.time() - start_t, 1) if start_t else 0
                await client_queue.put(json.dumps({
                    "type": "task_active",
                    "status": "running",
                    "prompt": slot.get("current_prompt") or "",
                    "model": slot.get("current_model") or "",
                    "start_time": start_t or 0,
                    "elapsed": elapsed,
                    "latest_action": latest_act,
                    "actions_count": len(actions),
                    "conversation_id": slot.get("current_conversation_id"),
                    "is_running": True
                }))

            if last_seq and hasattr(self, "message_queue") and isinstance(self.message_queue, list):
                for item in list(self.message_queue):
                    if isinstance(item, dict) and item.get("seq", 0) > last_seq:
                        item_owner = item.get("owner") or (item.get("msg") or {}).get("owner")
                        if _owners_match(client_owner, item_owner):
                            await client_queue.put(json.dumps(item.get("msg")))

            await client_queue.put(json.dumps({
                "type": "init",
                "connected": True,
                "is_running": is_user_running
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
