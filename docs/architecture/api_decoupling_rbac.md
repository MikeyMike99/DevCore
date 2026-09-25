# Architectural Decision Record: API Decoupling & Directory-Level Tiering
**Date:** 2026-09-25
**Phase:** Security & RBAC Lockdown (Tier 1 Sandbox Isolation)

## 1. Vulnerability Finding: The File-Level Classification Flaw
During our audit of `security_manager.py`, we identified a massive structural flaw in how `classify_file()` worked. Originally, the system only matched against a flat list of `CORE_FILES` (e.g., `server.py`). 

Because it did not recursively check directory trees, files like `core/ui_config.json` or `sandbox/templates/index.html` were falsely classified as `TIER_SAFE_WORKSPACE` merely because they had a `.json` or `.html` extension. If a lower-tier agent (like a `gamedev` role) managed to bypass the path-anchoring jail, they would have had the required permissions to modify the entire frontend interface or backend configuration files.

## 2. The Solution: Directory-Level Tiering
We injected a new constant `CORE_DIRECTORIES` into the Security Manager, explicitly listing `core`, `security`, `sandbox`, `plugins`, `docs`, `archives`, and `scripts`. 

The `classify_file` algorithm was rewritten to iteratively scan every part of a file path (e.g., `sandbox/templates/index.html`). The moment it detects a protected directory namespace (`sandbox`), the entire downward tree is permanently stamped as `TIER_CORE_ENGINE`, instantly blocking all non-admin access. 

## 3. The Architecture Shift: API-Driven Agent Contracts
By completely sealing off the core code from lower-tier agents, a new problem arose: **How do sandboxed subagents execute complex tasks (like building an exam) if they are physically barred from reading the server code to learn how the database works?**

The solution is **API Decoupling via Skills**:
1. We stripped the Swarm subagents of all codebase read privileges. They are now spawned with the `--sandbox` flag and jailed exclusively in their target data directory (e.g., `C:\Study`).
2. We generated an "API Contract" in the form of an Antigravity Skill (`exam-generator`). 
3. When the subagent activates, it reads the Skill, which provides the precise JSON schema and the API endpoint (`POST /api/plugin/exam/save`).
4. The subagent streams the parsed data over the local network via HTTP requests. 

## 4. Conclusion & Results
This architectural shift completely eliminates the risk of prompt-injection or AI hallucination destroying the DevCore engine. A compromised or hallucinating subagent is completely blind to the engine's existence; it is trapped in a sandboxed folder, and its only vector of interaction with the system is a highly sanitized, validation-backed HTTP API endpoint. 
