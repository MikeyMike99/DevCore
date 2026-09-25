# Architecture Guide: Game Engine Integration & Plugin Pipeline
**Date:** 2026-09-25
**Purpose:** Defines the standard operating procedure for integrating the DevCore Agent into third-party applications (Game Engines like Unity, Unreal, Godot, or standalone developer tools).

## 1. The Headless Daemon (Boot Sequence)
The agent is explicitly designed NOT to function as a traditional desktop application when deployed as a plugin. 
Instead, the entire Python backend (Quart server, Agent Manager, Security Manager) is compiled into a single, native machine-code executable using a C-compiler (e.g., Nuitka).
* **Execution:** The parent Game Engine triggers this executable as a background subprocess.
* **Visibility:** The executable is compiled with terminal-suppression flags (`--windows-disable-console`). It runs completely invisibly.
* **Binding:** Upon launch, it instantly binds to `http://localhost:5000` (and `ws://localhost:5000`) on the host machine.

## 2. The WebSocket Bridge (Communication)
The Game Engine and the Agent do not share memory; they communicate exclusively over a local WebSocket.
* **State Injection:** Game Engines can silently feed real-time environmental context to the agent behind the scenes via hidden JSON payloads (e.g., `{"player_health": 40, "location": "Dark Forest"}`). This grants the agent full situational awareness before the player ever sends a prompt.
* **Event Streaming:** The agent streams its thought processes, tool executions, and final text back to the Game Engine chunk-by-chunk via `stream-json` NDJSON formatting.

## 3. Sandbox Constraints (Zero-Trust Security)
Because the agent runs locally on the player's machine, it is highly restricted to prevent rogue code execution or OS-level damage.
* When the game invokes the agent, the backend `security_manager.py` jails the agent's operations strictly to a designated Safe Workspace (e.g., the game's `/playground`, `/mods/`, or `/saves/` directory).
* The agent is fundamentally blocked from accessing System32, the user's personal documents, or the game's core compiled engine files. It may only read/write dynamic assets (JSON, Lua, dialogue trees) within the safe tier.

## 4. UI Rendering Strategies
The parent Game Engine is entirely responsible for rendering the agent to the player. Two supported methodologies exist:
1. **In-Game Web Browser (CEF):** The game engine embeds a Chromium Embedded Framework (CEF) overlay. The CEF frame simply targets `http://localhost:5000`, instantly rendering the HTML/Tailwind web interface as a 2D or 3D holographic UI inside the game world.
2. **Native Parsing:** The game engine ignores the HTML interface, connects directly to the WebSocket, and parses the raw JSON text to drive native game UI elements (like traditional RPG dialogue boxes or terminal screens).

## 5. Protecting Host Source Code (Zero-Trust Injection)
A critical requirement of plugging this agent into third-party projects is guaranteeing that the AI cannot accidentally (or maliciously) modify the parent application's proprietary source code.
* **Workspace Confinement:** When the parent application starts the daemon, it designates a strictly confined directory (e.g., `C:\MyGame\Player_Mods\`). 
* **Path Traversal Defense:** The internal `security_manager.py` uses strict `os.path.realpath` boundary checks. If the agent attempts to use directory traversal (e.g., reading `../../src/main_engine.cpp`) to look at the host application's source code, the backend intercepts the filesystem call, instantly blocks the execution, and returns a `PermissionError`.
* **The Guarantee:** The parent application's source code, host OS files, and intellectual property remain 100% invisible and physically inaccessible to the AI agent. It can only "see" the exact sandbox folder the parent application gives it.
