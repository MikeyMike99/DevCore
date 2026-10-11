---
name: background-task-offloading
description: >-
  Orchestrate long-running background tasks securely by running commands
  detached and automatically waking up the agent via a webhook ping when complete.
  Prevents strict timeouts and data loss.
---

# Background Task Offloading

## Overview
This skill allows the agent to safely execute massive, long-running processes (like DAST scans, large test suites, or repo sweeps) without hitting the 3-minute hard timeout limit. It relies on the `run_command` tool (using `IsDaemon=True`) and a dedicated `/api/webhooks/agent_callback` endpoint on the local server to wake the agent back up.

## Dependencies
- DevCore API (`/api/webhooks/agent_callback`) must be active on `http://localhost:5000`

## Workflow

### 1. Launch the Command in the Background
When asked to run a long-running command, you must execute it using the `run_command` tool.
- Set `IsDaemon=True` and a very short `WaitMsBeforeAsync` (e.g. 500) so it detaches immediately.
- Wrap the execution in a shell command that executes the workload, redirects output to a file, and then physically curls the webhook to wake you up.

Example Bash Command Payload:
```bash
nohup bash -c "your_long_command > scan_results.txt 2>&1 ; curl -X POST http://localhost:5000/api/webhooks/agent_callback -H 'Content-Type: application/json' -d '{\"message\":\"Task complete\", \"task_id\":\"scan_123\"}'" &
```

### 2. End Your Turn Immediately
After starting the command, immediately reply to the user stating that the task is running in the background and end your turn. **DO NOT** loop, wait, or poll for the result.

### 3. Await the Webhook
When the background command finishes, the `curl` payload will trigger the DevCore server's webhook. The server will automatically inject a `<SYSTEM_MESSAGE>` into your context window waking you up. 

### 4. Analyze Results
Once awakened, read the generated output file (e.g. `scan_results.txt`) and present the findings to the user.

## Common Mistakes
- **Forgetting to Redirect Output:** Background tasks won't easily pipe to your standard stream when detached. ALWAYS redirect to a file like `results.txt`.
- **Polling:** Never use `manage_task` to poll for completion. You must end your turn and let the system wake you via the webhook.
- **Forgetting the Curl Ping:** If you don't chain the `curl` webhook ping at the end of the `nohup bash -c "..."` payload, the system will never wake you up when it finishes!
