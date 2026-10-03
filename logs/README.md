# Swarm Onion (SIEM) Logging Architecture

This directory acts as the central ingestion point for the DevCore **Swarm Onion SIEM (Security Information and Event Management)**.

Instead of writing to dozens of scattered text files, the entire DevCore ecosystem (WebSockets, Web Server, File System, AI Agents, and OS crashes) routes all logs through a centralized JSON Formatter. The output is stored in `devcore_master.jsonl`.

## Event Categories

Because reading a massive JSON stream can be difficult, the SIEM automatically analyzes the origin and semantic meaning of every log and assigns it an `event_category`. 

You can use standard command-line tools to instantly filter the master log by category. For example:
`grep '"category": "FAULT"' devcore_master.jsonl`

### The 8 SIEM Log Categories

| Category | Description | Triggers & Examples |
| :--- | :--- | :--- |
| **`STARTUP`** | Tracks the boot sequence of the engine. Crucial for verifying that encryption modules, Raugus maps, and servers loaded correctly. | "Central SIEM Logger Initialized", "Server booting on port 5000" |
| **`FAULT`** | **Critical.** Captures hard crashes, unhandled OS exceptions, and catastrophic system failures. | Python tracebacks, `sys.excepthook` captures, `CRITICAL` log levels. |
| **`SECURITY_AUDIT`** | Tracks the Next-Gen Prompt Firewall (NGPF). Logs any attempts to breach Tiers or modify locked Sub-File AST nodes. | "Raugus Firewall Interception", Path traversal blocks, Unauthorized file access. |
| **`AUTH`** | Tracks the authentication lifecycle of human users and their RBAC tier assignments. | "Admin logged in", "Token generated for user: mod", "Session expired". |
| **`AGENTIC`** | Tracks AI Swarm behavior, tool usage, Agentic 5-Tuples, and LLM telemetry. | "Agent invoked tool: write_to_file", "SwarmFlow token consumption". |
| **`NETWORK`** | Tracks HTTP traffic, WebSocket connections, and external API routing. | Hypercorn/Quart routing, "WebSocket connected", IP address logging. |
| **`WARNING`** | Traps non-fatal deprecation warnings and minor internal errors that did not crash the system. | `warnings.showwarning` captures, SSL deprecation notices. |
| **`SYSTEM`** | The default baseline. General operational events that do not fit into the specialized categories above. | Database saves, config reloads, background syncs. |

## Log Schema

Every line in `devcore_master.jsonl` is perfectly synchronized to UTC (Chrono-Syncing) and follows this strict JSON schema:

```json
{
  "timestamp": "2026-10-03T18:18:52.656021+00:00",
  "level": "INFO",
  "category": "STARTUP",
  "logger": "root",
  "module": "central_logger",
  "message": "Central SIEM Logger Initialized. Swarm Onion architecture is active.",
  "exception": null
}
```
*(Note: If the category is `FAULT`, the `exception` key will contain the full multi-line stack trace of the crash.)*
