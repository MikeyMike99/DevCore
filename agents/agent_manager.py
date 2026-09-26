import asyncio
import json
import os
import time

class AgentTaskManager:
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
        self.current_model: str = "gemini-3.8-flash-low"
        self.start_time: float = None
        self.output_buffer: list = []
        self.actions: list = []
        self.last_completed_task: dict = None
        self.connected_clients: set = set()
        self.current_conversation_id: str = None
        
        # Guaranteed Delivery & ACK Queue
        self.current_seq: int = 0
        self.message_queue: list = []  # [{ "seq": int, "msg": dict }]
        self.max_queue_size: int = 1000
        self._lock = asyncio.Lock()
        self._local_sec = None
        self.rate_limits = {}  # type: dict

    def _get_security(self):
        if self._local_sec is None:
            try:
                try:
                    from security.local_security import LocalSecurity
                except ImportError:
                    from local_security import LocalSecurity
                self._local_sec = LocalSecurity()
            except Exception as e:
                print(f"[Security] LocalSecurity init failed, using Dummy. Error: {e}")
                class Dummy:
                    def scrub_text(self, t): return t
                self._local_sec = Dummy()
        return self._local_sec

    def reinit(self, project_manager=None):
        """Re-initializes state while preserving client connections and pending queue."""
        if project_manager:
            self.project_manager = project_manager
        self.output_buffer = []
        self.actions = []

    def is_running(self) -> bool:
        return self.active_proc is not None and self.active_proc.returncode is None

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
        
        # Broadcast to all connected clients (which are asyncio.Queue objects)
        for client_queue in list(self.connected_clients):
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
            # First send initial status
            await client_queue.put(json.dumps({
                "type": "init",
                "connected": True,
                "current_seq": self.current_seq,
                "is_running": self.is_running()
            }))

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
        except Exception as e:
            print(f"[AgentTaskManager] Error syncing client: {e}")

    async def register_client(self, ws):
        self.connected_clients.add(ws)
        # Client will send its own sync message with last_seq; don't sync automatically to avoid duplicate seq=0 broadcast.

    async def unregister_client(self, ws):
        self.connected_clients.discard(ws)

    async def start_task(self, prompt: str, model: str = "gemini-3.8-flash-low", conversation_id: str = None, user: dict = None, admin_override: bool = False):
        if self.is_running():
            await self.broadcast({
                "type": "system",
                "level": "warning",
                "message": "A task is already actively running. Please wait for it to complete or click Cancel."
            })
            return
        is_admin = (user and user.get("role") == "admin") or admin_override
        
        # Financial DoS / Rate Limiting Protection (Max 15 requests per minute per user)
        if not is_admin:
            user_id = user.get("username", "anonymous") if user else "anonymous"
            now = time.time()
            if user_id not in self.rate_limits or now > self.rate_limits[user_id].get("reset_time", 0):
                self.rate_limits[user_id] = {"count": 0, "reset_time": now + 60}
            
            if self.rate_limits[user_id]["count"] >= 15:
                await self.broadcast({
                    "type": "system",
                    "level": "error",
                    "message": "Rate limit exceeded (15 req/min). Please wait to prevent API quota exhaustion."
                })
                return
            self.rate_limits[user_id]["count"] += 1
        if is_admin:
            scrubbed_prompt = prompt
        else:
            scrubbed_prompt = self._get_security().scrub_text(prompt)
            
        self.current_prompt = scrubbed_prompt
        self.current_model = model or "gemini-3.8-flash-low"
        self.start_time = time.time()
        self.output_buffer = []
        self.actions = []

        await self.broadcast({
            "type": "task_started",
            "prompt": prompt,
            "model": self.current_model,
            "start_time": self.start_time
        })

        self.active_task = asyncio.create_task(
            self._execute_agent(prompt, self.current_model, self.start_time, conversation_id, user=user, admin_override=admin_override)
        )

    async def _heartbeat_worker(self, start_time: float):
        """Sends periodic heartbeats to keep the TCP/WebSocket alive."""
        try:
            while True:
                elapsed = int(time.time() - start_time)
                await self.broadcast({
                    "type": "heartbeat",
                    "elapsed": elapsed
                })
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _execute_agent(self, prompt: str, model: str, task_time: float, conversation_id: str, user: dict = None, admin_override: bool = False):
        hb_task = asyncio.create_task(self._heartbeat_worker(task_time))
        try:
            workspace_dir = None
            if self.project_manager:
                workspace_dir = self.project_manager.get_active_workspace_path()
            if not workspace_dir:
                workspace_dir = os.path.dirname(os.path.abspath(__file__))

            # Sanitize environment: strip API keys and host secrets from subprocess
            safe_env = {
                k: v for k, v in os.environ.items()
                if k in ("PATH", "HOME", "USER", "LANG", "TERM", "SHELL", "GEMINI_API_KEY", "GOOGLE_API_KEY") or k.startswith("AGY_")
            }
            # Ensure ~/.local/bin is in PATH so PythonAnywhere WSGI can find the agy binary
            local_bin = os.path.expanduser("~/.local/bin")
            if "PATH" in safe_env and local_bin not in safe_env["PATH"]:
                safe_env["PATH"] = f"{local_bin}:{safe_env['PATH']}"
            elif "PATH" not in safe_env:
                safe_env["PATH"] = local_bin

            # Enforce sandbox for non-admin roles unless explicitly bypassed via UI override
            is_admin = (user and user.get("role") == "admin") or admin_override
            perm_flag = "--dangerously-skip-permissions" if is_admin else "--sandbox"
            
            # Instruct Antigravity to avoid the sandbox when running as admin and prevent quota-exhausting loops
            if is_admin:
                prompt = (
                    "<SYSTEM_MESSAGE>\n"
                    "1. You are running with ADMIN privileges.\n"
                    "2. DO NOT execute stuff in the sandbox.\n"
                    "3. CRITICAL RULE: If a tool call fails or returns an error, DO NOT repeat the exact same tool call. "
                    "Analyze the error and try a different approach. If you fail twice, STOP and ask the user for help.\n"
                    "</SYSTEM_MESSAGE>\n\n"
                ) + prompt

            # 1. Determine if a real agy executable is available (and NOT the 19-byte dummy)
            import shutil, sys
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bundled_exe = os.path.join(base_dir, "agy.exe")
            bundled_linux = os.path.join(base_dir, "agy")
            
            real_agy = None
            cand = shutil.which("agy")
            if cand and os.path.exists(cand) and os.path.getsize(cand) > 1024:
                real_agy = cand
            elif os.path.exists(bundled_exe) and os.path.getsize(bundled_exe) > 1024:
                real_agy = bundled_exe
            elif os.path.exists(bundled_linux) and os.path.getsize(bundled_linux) > 1024:
                real_agy = bundled_linux
            elif sys.platform != "win32":
                local_agy = os.path.expanduser("~/.local/bin/agy")
                if os.path.exists(local_agy) and os.path.getsize(local_agy) > 1024:
                    real_agy = local_agy

            # 2. If NO real working agy CLI binary exists, seamlessly use the native Gemini engine
            if not real_agy:
                await self._execute_native_gemini(prompt, model, task_time, conversation_id, is_admin)
                return

            cmd = [
                real_agy,
                perm_flag,
                "--model", model,
                "--output-format", "stream-json"
            ]
            if conversation_id:
                cmd.extend(["--conversation", conversation_id])
            cmd.extend(["--print", prompt])
            
            # Only use wsl if running a non-Windows binary on Windows
            if sys.platform == "win32" and not real_agy.endswith(".exe"):
                cmd = ["wsl.exe"] + cmd

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workspace_dir,
                env=safe_env,
                start_new_session=True, # Creates a Process Group for child subagents
                limit=1024 * 1024 * 100
            )
            self.active_proc = proc

            await self.broadcast({"type": "agent_start", "model": model})

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if not line_str:
                    continue

                try:
                    event_data = json.loads(line_str)
                    event_type = event_data.get("event")

                    if event_type == "init":
                        real_conv_id = event_data.get("conversation_id")
                        if real_conv_id:
                            self.current_conversation_id = real_conv_id
                            await self.broadcast({"type": "init_conv_id", "conversation_id": real_conv_id})
                            try:
                                from core import session_manager
                                sm_inst = session_manager.SessionManager()
                                proj_name = self.project_manager.active_project if self.project_manager else None
                                username = user.get("username") if user else "admin"
                                sm_inst.register_session_owner(real_conv_id, username, proj_name)
                            except Exception as e:
                                print(f"[AgentManager] Failed to register owner: {e}")

                    elif event_type == "step_update":
                        step = event_data.get("step_update", {})
                        stype = step.get("step_type")
                        state = step.get("state")

                        if stype == "tool":
                            tool_name = step.get("tool_name", "tool")
                            tool_info = step.get("tool_info", {})
                            if state == "ACTIVE":
                                raw_params = tool_info.get("parameters", {})
                                safe_params = {}
                                for k, v in raw_params.items():
                                    if isinstance(v, str) and len(v) > 2000:
                                        safe_params[k] = v[:2000] + "... [Truncated for UI]"
                                    else:
                                        safe_params[k] = v
                                act = {
                                    "id": step.get("step_index"),
                                    "tool": tool_name,
                                    "params": safe_params,
                                    "status": "running"
                                }
                                self.actions.append(act)
                                await self.broadcast({"type": "action_start", "action": act})
                            elif state == "DONE":
                                raw_output = tool_info.get("output", "")
                                if isinstance(raw_output, str) and len(raw_output) > 2000:
                                    raw_output = raw_output[:2000] + "\n\n... [Output truncated for UI] ..."
                                act = {
                                    "id": step.get("step_index"),
                                    "tool": tool_name,
                                    "duration": round(step.get("duration_seconds", 0), 2),
                                    "output": raw_output,
                                    "status": "done"
                                }
                                for idx, existing in enumerate(self.actions):
                                    if existing.get("id") == act["id"]:
                                        self.actions[idx] = act
                                        break
                                else:
                                    self.actions.append(act)
                                await self.broadcast({"type": "action_done", "action": act})

                        elif stype in ("system", "error"):
                            msg = step.get("text") or step.get("error") or ""
                            if msg:
                                await self.broadcast({
                                    "type": "system",
                                    "level": "warning" if stype == "system" else "error",
                                    "message": msg
                                })
                                # Send a specific model_fallback event if detected
                                lower_msg = msg.lower()
                                if "quota" in lower_msg or "fallback" in lower_msg or "falling back" in lower_msg:
                                    import re
                                    # Try to extract what model it fell back to, or default to flash
                                    fallback_model = "gemini-3.8-flash-low"
                                    match = re.search(r'model ([\w.-]+)', lower_msg)
                                    if match:
                                        fallback_model = match.group(1)
                                    await self.broadcast({
                                        "type": "model_fallback",
                                        "message": msg,
                                        "fallback_model": fallback_model
                                    })
                                    self.current_model = fallback_model

                        elif stype == "agent_response":
                            delta = step.get("text_delta", "")
                            if delta:
                                if not is_admin:
                                    delta = self._get_security().scrub_text(delta)
                                self.output_buffer.append(delta)
                                await self.broadcast({"type": "agent_chunk", "chunk": delta})

                    elif event_type == "result":
                        res = event_data.get("result", {})
                        final_resp = res.get("response", "")
                        if not self.output_buffer and final_resp:
                            if not is_admin:
                                final_resp = self._get_security().scrub_text(final_resp)
                            self.output_buffer.append(final_resp)
                            await self.broadcast({"type": "agent_chunk", "chunk": final_resp})

                except json.JSONDecodeError:
                    self.output_buffer.append(line_str + "\n")
                    await self.broadcast({"type": "agent_chunk", "chunk": line_str + "\n"})

            await proc.wait()
            elapsed = round(time.time() - task_time, 1)
            status_str = "SUCCESS" if proc.returncode == 0 else "ERROR"
            
            # Save to last_completed_task cache for reconnecting clients
            self.last_completed_task = {
                "prompt": prompt,
                "model": model,
                "actions": list(self.actions),
                "output": "".join(self.output_buffer),
                "elapsed": elapsed,
                "status": status_str,
                "timestamp": time.time()
            }

            await self.broadcast({
                "type": "agent_done",
                "exit_code": proc.returncode,
                "elapsed": elapsed,
                "status": status_str,
                "cancelled": False
            })
        except asyncio.CancelledError:
            if self.active_proc and self.active_proc.returncode is None:
                try:
                    self.active_proc.kill()
                except Exception:
                    pass
            await self.broadcast({"type": "agent_done", "cancelled": True})
        except Exception as e:
            await self.broadcast({"type": "system", "level": "warning", "message": f"Execution error: {str(e)}"})
            await self.broadcast({"type": "agent_done", "cancelled": True})
        finally:
            hb_task.cancel()
            self.active_proc = None
            self.active_task = None
            self.start_time = None

    async def _execute_native_gemini(self, prompt: str, model: str, task_time: float, conversation_id: str, is_admin: bool):
        await self.broadcast({"type": "agent_start", "model": model})

        if not conversation_id:
            import uuid
            conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
            self.current_conversation_id = conversation_id
            await self.broadcast({"type": "init_conv_id", "conversation_id": conversation_id})

        # Load API key from env or saved client key file
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            client_key_path = os.path.expanduser("~/.devcore_client_key.txt")
            if os.path.exists(client_key_path):
                try:
                    with open(client_key_path, "r", encoding="utf-8") as f:
                        api_key = f.read().strip()
                        if api_key:
                            os.environ["GEMINI_API_KEY"] = api_key
                except Exception:
                    pass

        if not api_key:
            err_msg = (
                "⚠️ **No Google Gemini API Key Configured**\n\n"
                "Siraugga is running in native desktop mode without external CLI dependencies.\n\n"
                "To chat with the AI:\n"
                "1. Open the **Authentication / Settings** screen.\n"
                "2. Enter your Google Gemini API key (`AIzaSy...`).\n"
                "3. Click **Authenticate Client**.\n\n"
                "*Tip: You can get a free API key at https://aistudio.google.com/app/apikey*"
            )
            self.output_buffer.append(err_msg)
            await self.broadcast({"type": "agent_chunk", "chunk": err_msg})
            elapsed = round(time.time() - task_time, 1)
            self.last_completed_task = {
                "prompt": prompt,
                "model": model,
                "actions": [],
                "output": err_msg,
                "elapsed": elapsed,
                "status": "SUCCESS",
                "timestamp": time.time()
            }
            await self.broadcast({
                "type": "agent_done",
                "exit_code": 0,
                "elapsed": elapsed,
                "status": "SUCCESS",
                "cancelled": False
            })
            return

        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            clean_prompt = prompt
            if clean_prompt.startswith("<SYSTEM_MESSAGE>"):
                parts = clean_prompt.split("</SYSTEM_MESSAGE>\n\n", 1)
                if len(parts) == 2:
                    clean_prompt = parts[1]

            # Candidate models for fallback
            candidate_models = []
            if model and model not in ("gemini-3.8-flash-low", "gemini-3.8-flash-high"):
                candidate_models.append(model)
            candidate_models.extend(["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest"])

            response_iter = None
            last_err = None
            for candidate in candidate_models:
                try:
                    response_iter = await client.aio.models.generate_content_stream(
                        model=candidate,
                        contents=clean_prompt
                    )
                    break
                except Exception as ex:
                    last_err = ex
                    continue

            if response_iter is None:
                raise last_err or RuntimeError("Failed to connect to Gemini models.")

            async for chunk in response_iter:
                if chunk.text:
                    delta = chunk.text
                    if not is_admin:
                        delta = self._get_security().scrub_text(delta)
                    self.output_buffer.append(delta)
                    await self.broadcast({"type": "agent_chunk", "chunk": delta})

            elapsed = round(time.time() - task_time, 1)
            full_output = "".join(self.output_buffer)
            self.last_completed_task = {
                "prompt": prompt,
                "model": model,
                "actions": [],
                "output": full_output,
                "elapsed": elapsed,
                "status": "SUCCESS",
                "timestamp": time.time()
            }
            await self.broadcast({
                "type": "agent_done",
                "exit_code": 0,
                "elapsed": elapsed,
                "status": "SUCCESS",
                "cancelled": False
            })
        except Exception as e:
            err_msg = f"\n\n❌ **AI Generation Error**: {str(e)}"
            self.output_buffer.append(err_msg)
            await self.broadcast({"type": "system", "level": "error", "message": str(e)})
            await self.broadcast({"type": "agent_chunk", "chunk": err_msg})
            elapsed = round(time.time() - task_time, 1)
            await self.broadcast({
                "type": "agent_done",
                "exit_code": 1,
                "elapsed": elapsed,
                "status": "ERROR",
                "cancelled": False
            })

    
    async def send_input(self, text: str):
        if self.active_proc and self.active_proc.stdin:
            self.active_proc.stdin.write((text + "\n").encode('utf-8'))
            await self.active_proc.stdin.drain()

    async def cancel_task(self):
        if self.is_running():
            try:
                import sys, os, signal
                if sys.platform == "win32":
                    # Native Windows: Kill process tree
                    import subprocess
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.active_proc.pid)], capture_output=True)
                else:
                    # Linux/WSL: Kill the entire Process Group (Main Agent + All Subagents)
                    os.killpg(os.getpgid(self.active_proc.pid), signal.SIGKILL)
            except Exception:
                try: self.active_proc.kill()
                except: pass
            if self.active_task and not self.active_task.done():
                self.active_task.cancel()
            await self.broadcast({
                "type": "system",
                "level": "info",
                "message": "Task cancelled by user."
            })
            await self.broadcast({
                "type": "agent_done",
                "cancelled": True
            })
