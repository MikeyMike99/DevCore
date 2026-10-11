# Antigravity Security & Threat Model Documentation

## Threat Landscape for In-Game Developer Deployments

When embedding this AI portal inside developer workflows and game engines for unprivileged users, standard conversational guardrails are insufficient. Hard architectural controls must prevent sandbox escapes, data leakage, and system compromise.

---

### 1. Symlink Traversal (CWE-59)
- **Vulnerability**: An unprivileged developer creates a symlink within their assigned project folder pointing to sensitive host files:
  `ln -s ../../App Router Module safe_dialogue.json`
  Traditional path checking using `os.path.abspath()` only normalizes dot-dot strings without dereferencing filesystem links, allowing unauthorized reads and overwrites of core files.
- **Mitigation Applied**: `SecurityManager.resolve_safe_path()` now uses `os.path.realpath()`. It resolves all filesystem links to their canonical physical destination and asserts that the physical path resides strictly within the real project directory boundary.

---

### 2. Multi-Tenant WebSocket Bleed (CWE-200)
- **Vulnerability**: Global WebSocket broadcasting emits streaming agent tokens and tool outputs to every connected client indiscriminately, leaking private prompts and transcripts between different developers.
- **Mitigation Applied**: `AgentTaskManager` now tracks user context on each connected WebSocket (`connected_clients[ws] = user`). Tasks are tagged with the requesting `username`, and `broadcast()` routes chunks exclusively to that user's active sockets.

---

### 3. Subprocess Environment & Credential Exfiltration (CWE-214)
- **Vulnerability**: Subprocesses spawn with the parent process's full `os.environ`, exposing API keys (`GEMINI_API_KEY`), cloud tokens, and host variables if a prompt asks the agent to inspect the environment.
- **Mitigation Applied**: `_execute_agent()` constructs a strictly whitelisted environment dictionary. The root billing keys (`GEMINI_API_KEY`, `GOOGLE_API_KEY`) are completely stripped from the agent's memory space. Instead, the subprocess receives a dummy token and an internal `GEMINI_BASE_URL`. All LLM traffic is routed through our local Secure Proxy (`/api/proxy`), which securely attaches the encrypted root vault key server-side before forwarding to Google.

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

---

### 5. Dynamic Tool Feed Bleed (CWE-200 / CWE-497)
- **Vulnerability**: While file I/O operations are strictly blocked by the Raugus Firewall, the AI's internal "thinking process" (dynamic tool summaries, intended command line executions) is broadcasted live to the WebSocket accessibility feed. A malicious developer could use prompt injection to bait the AI into analyzing core files, relying on the `toolAction` or `CommandLine` stream to leak internal architectural paths before the firewall ultimately denies the request.
- **Mitigation Applied**: `AgentTaskManager` now features Stealth Obfuscation. Before any tool execution payload is broadcasted, the server scans the JSON for core architecture indicators (`/core`, `server.py`, etc.). If a non-admin triggers these indicators, the server silently scrubs the sensitive values and overwrites the screen reader announcement with a benign, innocuous string (`"Running a routine background check..."`). This neutralizes the user's ability to map the architecture via feed snooping.

---

### 6. Source Code Disclosure via Backup Files (CWE-530)
- **Vulnerability**: When automated tools (like the MCP Line Editor) dynamically modify configuration scripts or environment variables (`server.py`, `.env`), standard programming practice often dictates creating a quick `.bak` or `.orig` file as an undo mechanism. However, if these files are generated within directories served by a web server, the web server's security configurations may not recognize `.bak` extensions as restricted. This allows attackers to bypass execution controls and download raw source code, secrets, or API keys directly over HTTP.
- **Mitigation Applied**: The architecture strictly bans in-place artifact backups (`.bak`, `.tmp`) for file modifications. The MCP Line Editor modifies target files strictly in-place, relying exclusively on `git` for state recovery. This adheres to the Global Clean Workspace Protocol and ensures zero persistent digital clutter.

---

### 7. MCP Tool Evasion (CWE-284)
- **Vulnerability**: Custom Model Context Protocol (MCP) tools operate outside the standard built-in toolset (e.g. `replace_file_content`). An agent using a custom tool like `edit_lines` could bypass the AST Diffing and Semantic Firewall checks, modifying locked core functions simply because the interceptor doesn't recognize the tool name.
- **Mitigation Applied**: The `raugus_hook.py` PreToolUse interceptor and the `AgentTaskManager` orchestration engine explicitly whitelist and map arguments for custom MCP tools (`edit_lines`). The AST Diffing engine successfully extracts `start_line`, `end_line`, and `new_code`, projecting the edits into memory to verify function-level write permissions against the `raugus_map.json` before allowing execution.
