# Antigravity Security & Threat Model Documentation

## Threat Landscape for In-Game Developer Deployments

When embedding this AI portal inside developer workflows and game engines for unprivileged users, standard conversational guardrails are insufficient. Hard architectural controls must prevent sandbox escapes, data leakage, and system compromise.

---

### 1. Symlink Traversal (CWE-59)
- **Vulnerability**: An unprivileged developer creates a symlink within their assigned project folder pointing to sensitive host files:
  `ln -s ../../server.py safe_dialogue.json`
  Traditional path checking using `os.path.abspath()` only normalizes dot-dot strings without dereferencing filesystem links, allowing unauthorized reads and overwrites of core files.
- **Mitigation Applied**: `SecurityManager.resolve_safe_path()` now uses `os.path.realpath()`. It resolves all filesystem links to their canonical physical destination and asserts that the physical path resides strictly within the real project directory boundary.

---

### 2. Multi-Tenant WebSocket Bleed (CWE-200)
- **Vulnerability**: Global WebSocket broadcasting emits streaming agent tokens and tool outputs to every connected client indiscriminately, leaking private prompts and transcripts between different developers.
- **Mitigation Applied**: `AgentTaskManager` now tracks user context on each connected WebSocket (`connected_clients[ws] = user`). Tasks are tagged with the requesting `username`, and `broadcast()` routes chunks exclusively to that user's active sockets.

---

### 3. Subprocess Environment & Credential Exfiltration (CWE-214)
- **Vulnerability**: Subprocesses spawn with the parent process's full `os.environ`, exposing API keys (`GEMINI_API_KEY`), cloud tokens, and host variables if a prompt asks the agent to inspect the environment.
- **Mitigation Applied**: `_execute_agent()` constructs a strictly whitelisted environment dictionary (`PATH`, `HOME`, `LANG`, `TERM`, `SHELL`, `AGY_*`). Host secrets, internal keys, and system environment variables are stripped prior to execution.

---

### 4. Indirect Prompt Injection via Game Assets (CWE-74)
- **Vulnerability**: Poisoned 3D model metadata, Lua scripts, or dialogue files imported from third parties contain hidden instructions that hijack the agent's behavior when read.
- **Mitigation Applied**: 
  - File viewing is strictly sandboxed to `TIER_SAFE_WORKSPACE`.
  - The model prompt is wrapped with strict untrusted-content delimiters (`<user_data_untrusted>`), establishing that file contents are passive data, not executable directives.

---

### 5. Localhost & Private Subnet SSRF (CWE-918)
- **Vulnerability**: An unprivileged user instructs the agent to query local loopback ports (`127.0.0.1:5000/api/reload`, internal debug servers, cloud metadata endpoints `169.254.169.254`).
- **Mitigation Applied**: Non-admin executions are locked into `--sandbox` mode, preventing arbitrary network tool invocations and loopback scanning.

---

### 6. Resource Exhaustion & Runaway Subprocesses (CWE-400)
- **Vulnerability**: Prompts triggering runaway loops, massive disk writes, or exhausting API token quotas.
- **Mitigation Applied**:
  - Maximum 180-second hard timeout enforced on agent execution (`--print-timeout 180s`).
  - Maximum file write size capped at 500 KB per transaction in `SecurityManager`.
  - Memory-safe sequence queue with bounded capacity (1,000 messages maximum).
