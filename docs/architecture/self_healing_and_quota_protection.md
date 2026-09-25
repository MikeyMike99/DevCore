# Architectural Decision Record: Self-Healing Gateway & Quota Protection
**Date:** 2026-09-25
**Phase:** System Reliability, Token Optimization, and Auto-Recovery

## 1. Vulnerability Finding: Secret Token Exhaustion via Alias Routing
During an audit of the frontend UI and backend agent manager, we discovered a significant token exhaustion vulnerability. The frontend UI was configured to send `gemini-3.8-flash-high` when the user selected the "Fast & Responsive" Flash model.

**The Issue:** The `agy` CLI interprets the `-high` suffix as a directive to use **High Effort Reasoning**. In agentic systems, High Effort automatically provisions expensive "Pro" reasoning loops for planning, completely bypassing the user's intent to use a cheap, fast model. 

**The Fix:**
- Patched `ui_config.json` to strictly map to `gemini-3.8-flash-low` ("Fast & Cheap").
- Updated JavaScript fallbacks in `index.html` and the Python fallback in `agent_manager.py` to default to `-low`.

## 2. Event-Driven Fallback UI Reflection
Previously, if the internal CLI encountered an API Quota limit (HTTP 429) and forced a downgrade to a cheaper model, the frontend UI was blind to this change. 
We introduced a transparent `model_fallback` WebSocket event:
1. `agent_manager.py` now monitors the JSON stream for `step_type: "system"` or `"error"`. 
2. If it detects the words "quota" or "fallback", it extracts the downgraded model name and broadcasts a `model_fallback` event.
3. `index.html` intercepts this event, visibly forces the UI dropdown to the downgraded model, turns the Task Badge yellow with a `(Forced)` tag, and triggers a Screen Reader auditory warning.

## 3. Pre-Flight Diagnostics & Autonomous Self-Healing
To prevent the web server from silently failing due to rogue syntax errors introduced during development or by lower-tier AI modifications, we injected a complete Self-Healing Protocol into `bootstrap_gateway.py`.

**The Boot Sequence:**
1. **Diagnostic Phase:** The gateway runs strict Python compilation checks (`python3 -m py_compile`) on all Core Engine files (`server.py`, `security_manager.py`, `agent_manager.py`, etc.).
2. **Success State:** If all files compile cleanly, the web server boots normally.
3. **Emergency Auto-Repair (The Self-Healing Loop):** 
   - If a file fails compilation, the gateway halts the boot process.
   - It programmatically spawns a headless `agy` CLI agent directly in the host terminal, passing it the exact Python crash traceback.
   - The agent is instructed to locate the syntax error, rewrite the file, and exit.
   - The Gateway immediately loops back to step 1. If the AI fix passes the diagnostic check, the server seamlessly boots with zero manual intervention required. 

## Conclusion
The system is now completely immunized against accidental token drains, entirely transparent about automated model downgrades, and possesses the autonomous ability to repair its own architectural codebase if a syntax error occurs during boot.
