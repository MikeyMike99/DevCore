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

class TranscriptMixin:
    @staticmethod
    def _strip_aria_noise(text: str) -> str:
        if not text:
            return ""
        import os
        import re
        s = str(text)
        # Convert markdown links [label](url) -> label
        s = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', s)
        # Strip bare file:// URIs to basename without line anchors
        s = re.sub(
            r'file:///[^\s)>\]]+',
            lambda m: os.path.basename(re.sub(r'#L\d+(?:-L?\d+)?', '', m.group(0)).rstrip('/')),
            s,
            flags=re.IGNORECASE,
        )
        # Collapse raw Unix/Windows paths (/mnt/c/.../foo.py#L10-L20, /home/.../bar.py) to basename only
        s = re.sub(
            r'(?:/mnt/[a-zA-Z]/|/home/|/var/|/tmp/|/etc/|/opt/|/usr/|[A-Za-z]:\\)[^\s)>\]"\'`,;]+',
            lambda m: os.path.basename(
                re.sub(r'#L\d+(?:-L?\d+)?', '', re.sub(r':\d+(?:-\d+)?$', '', m.group(0))).replace('\\', '/').rstrip('/')
            ),
            s,
        )
        # Strip line number anchors and line range phrases
        s = re.sub(r'#L\d+(?:-L?\d+)?\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'(\.[a-zA-Z0-9]{1,6}):\d+(?:-\d+)?\b', r'\1', s)
        s = re.sub(r'\(\s*lines?\s+L?\d+(?:\s*(?:-|–|to)\s*L?\d+)?\s*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\blines?\s+L?\d+\s*(?:-|–|to)\s*L?\d+\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'([a-zA-Z0-9])_([a-zA-Z0-9])', r'\1 \2', s)
        s = re.sub(r'([a-zA-Z0-9])_([a-zA-Z0-9])', r'\1 \2', s)
        s = re.sub(r'[*`#_()\[\]{}]', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    async def _get_narrative_context(self, conversation_id, expected_tool_name=None):
        deep_insight = ""
        tool_args = {}
        try:
            import json, os, re, time
            from collections import deque
            conv_id = getattr(self, "current_conversation_id", None) or conversation_id
            t_path = os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript_full.jsonl")
            
            for _ in range(10): # Poll up to 1 second
                if os.path.exists(t_path):
                    with open(t_path, 'r', encoding='utf-8') as tf:
                        last_lines = deque(tf, maxlen=100)
                        for line in reversed(last_lines):
                            try:
                                d = json.loads(line)
                                if d.get("type") == "PLANNER_RESPONSE":
                                    tool_calls = d.get("tool_calls", [])
                                    if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                                        # Try to find the matching tool call
                                        for t in reversed(tool_calls):
                                            if expected_tool_name and t.get("name") != expected_tool_name:
                                                continue
                                            if "thinking" in d:
                                                deep_insight = d["thinking"]
                                            tool_args = t.get("args", {})
                                            break
                                        if tool_args:
                                            break
                            except:
                                pass
                if deep_insight:
                    break
                await asyncio.sleep(0.1)
                
            if deep_insight:
                deep_insight = re.sub(r'CRITICAL INSTRUCTION.*?\n', '', deep_insight)
                deep_insight = re.sub(r'<planning_mode>.*?</planning_mode>', '', deep_insight, flags=re.DOTALL)
                deep_insight = re.sub(r'<bash_command_reminder>.*?</bash_command_reminder>', '', deep_insight, flags=re.DOTALL)
                paras = [p.strip() for p in deep_insight.split('\n') if p.strip()]
                if paras:
                    deep_insight = self._strip_aria_noise(" ".join(paras))
                    if len(deep_insight) > 600:
                        deep_insight = deep_insight[:600] + "..." 
        except Exception:
            pass
        return deep_insight, tool_args

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

    async def tail_transcript(self, conv_id):
        import asyncio
        import os
        import platform
        
        # Always read from the WSL path since Antigravity runs in WSL
        wsl_path = os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl")
        
        # Wait a brief moment to allow the conversation to initialize
        await asyncio.sleep(2)
        
        if platform.system() == 'Windows':
            process = await asyncio.create_subprocess_exec(
                'wsl.exe', 'bash', '-c', f'stdbuf -oL tail -n 0 -F {wsl_path}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                'tail', '-n', '0', '-F', wsl_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        try:
            while self.current_conversation_id == conv_id:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace')
                if "Stop hook blocked termination" in line_str:
                    pass
                elif "automatically approved" in line_str:
                    pass
                elif "has gone idle" in line_str or "killed" in line_str or "terminated" in line_str:
                    await self.broadcast({"type": "audio", "sound": "completed"})
                elif "invoked subagent" in line_str or "message to another agent" in line_str:
                    await self.broadcast({"type": "audio", "sound": "incoming"})
        except asyncio.CancelledError:
            process.terminate()
        except Exception as e:
            import logging
            logging.error(f"[TranscriptMixin] Transcript tailer failed: {e}")
            try:
                process.terminate()
            except:
                pass

