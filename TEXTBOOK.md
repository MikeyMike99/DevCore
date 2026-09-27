
## Siraugga.exe Startup Sequence & Architecture

When a user double-clicks the compiled \Siraugga.exe\ (which is generated from \desktop_app.py\ via Nuitka), the application undergoes a multi-staged startup sequence to bind the Python backend and the native frontend window together. 

Here is the exact step-by-step sequence of events:

### 1. Environment & Logging Initialization
- The executable starts as a windowless process (compiled with \--windows-disable-console\).
- Because standard output/error are disabled in the console, \desktop_app.py\ intercepts \sys.stdout\ and \sys.stderr\ and redirects them to \stdout.log\ and \stderr.log\ in the executable's directory. This is critical for post-crash debugging.

### 2. Backend Boot (Hypercorn & Quart)
- The main thread creates a background daemon thread \server_thread = threading.Thread(target=start_server, daemon=True)\.
- Inside \start_server\, the script initializes a new \syncio\ event loop.
- It imports the Quart application from \core/server.py\ (\import core.server as server\).
- It configures the production **Hypercorn ASGI Server** to bind to \127.0.0.1:5000\.
- \loop.run_until_complete(serve(...))\ is called, starting the headless DevCore backend.

### 3. Polling for Readiness
- While the background thread boots the backend, the main thread enters \wait_for_server()\.
- It polls \http://localhost:5000\ using \urllib.request.urlopen\ every 0.5 seconds (up to 30 times).
- Once it receives a successful HTTP response (Status 200), it knows the backend has safely booted and is ready to accept WebSocket connections.

### 4. Native UI Launch (PyWebView)
- With the backend confirmed online, the main thread calls \webview.create_window(...)\.
- It creates a native desktop window (using Edge Chromium/MSHTML rendering engine on Windows) wrapped around the URL \http://localhost:5000\.
- The native window loop starts (\webview.start()\), locking the main thread and displaying the UI.

### 5. Frontend Hydration & WebSocket Connection
- The pywebview browser engine parses \sandbox/templates/index.html\.
- The frontend JavaScript immediately creates a persistent WebSocket connection back to the Hypercorn server: \ws = new WebSocket('ws://localhost:5000/ws')\.
- A 4-second heartbeat (\ping/pong\) is established to keep the socket alive and prevent WSL2 or Windows network layers from quietly dropping idle sockets.
- The UI unlocks the Prompt bar and displays **"Connected"**.

### 6. Autonomous Self-Healing (Crash Handling)
- If the application hits a fatal exception at any point during this sequence (e.g., PyWebView failing to allocate EdgeWebView2, or a syntax error in an import), the global \	ry/except\ block at the bottom of \desktop_app.py\ catches it.
- The traceback is saved to \crash_log.txt\.
- \desktop_app.py\ imports \self_heal.py\ and fires \self_heal.heal_crash(tb_str)\.
- The self-heal module uses the Gemini AI to analyze the crash, generate a patch python file, hot-swap the broken code, and finally issues \os.execv\ to automatically restart \Siraugga.exe\, completely bypassing the user.


## Master Signature & First-Time Setup Sequence

To secure the local API without forcing the primary developer to constantly log in, the DevCore backend implements a cryptographic auto-provisioning system based on a hardware-bound master key.

### The Setup Sequence

1. **Master Key Hashing**: When the \Siraugga.exe\ engine starts, the \SecurityManager\ looks for a hidden file named \.devcore_master.key\ in the local execution directory. 
2. **Signature Verification**: \SecurityManager.check_master_signature()\ reads this file and computes its SHA-256 hash. If the hash matches the hardcoded \EXPECTED_HASH\ inside the application, it verifies that the app is running on the master hardware (Michael's machine). By hashing the key, reverse-engineers cannot extract the raw physical key from the compiled executable.
3. **Super Admin Elevation**: 
   - When the frontend (\index.html\) polls \/api/auth/system-status\, the backend detects the valid signature and returns \super_admin: true\.
   - The frontend immediately displays the \showSuperAdminSetupOverlay\.
4. **Auto-Login via Bypass**: The frontend silently issues a login request using the special \SUPER_ADMIN_AUTO\ bypass token. The backend verifies the master signature one last time and grants a temporary, full-privilege session token.
5. **Key Generation UI**: The Super Admin overlay provides a UI for the owner to generate permanent Role-Based Access Control (RBAC) keys.
   - The owner can create keys with specific roles (\dmin\, \gamedev\, \modder\).
   - They can scope keys to specific projects (e.g., \["game_demo"]\).
   - They set an expiration limit (e.g., \30\ days).
6. **Key Provisioning**: Clicking "Generate Key" hits the \/api/auth/keys\ POST endpoint. \SecurityManager.generate_key()\ creates a cryptographically secure token mapped to those exact RBAC restrictions and saves it to the local \keys.json\ database, returning the raw token to the frontend for the user to distribute.


## Zero-Downtime Over-The-Air (OTA) Updates

DevCore is designed with a "Self-Healing and Hot-Swappable" architecture that allows core engine modules to be updated in the field without needing to recompile the entire Siraugga.exe Nuitka binary or even disconnect active users.

### The Live Override System

Because Nuitka permanently bakes .py files into a compiled binary, hot-swapping code ordinarily requires restarting a newly compiled executable. DevCore circumvents this through the **LiveOverrideFinder**:

1. In desktop_app.py, a custom MetaPathFinder called LiveOverrideFinder is injected into the absolute front of sys.meta_path.
2. When the backend attempts to import a core module (like core.server or gents.agent_manager), the LiveOverrideFinder intercepts the import.
3. It checks if a loose .py script (e.g. core/server.py) exists in the same folder as the .exe.
4. If it does, it compiles and loads that loose Python script *instead* of the baked-in Nuitka binary module. 

This means a critical bug can be fixed instantly by dropping a hotfix script next to the executable.

### The Live Reload Sequence (/api/reload)

Dropping a file next to the .exe applies the fix on the *next* boot. To apply updates to an already running server with zero downtime:

1. A developer (or the AI Agent) issues a POST request to /api/reload.
2. The endpoint (core/server.py) checks gent_mgr.is_running() to see if AI agents are currently executing tasks, and saves gent_mgr.connected_clients to preserve active WebSockets.
3. It uses importlib.reload() on the core managers (SessionManager, ProjectManager, SecurityManager, AgentTaskManager).
4. It safely re-instantiates the manager classes in-memory. If an AI task is active, it only updates the manager references without killing the subprocess; if idle, it fully resets them.
5. The new code is now executing live without breaking the frontend connection.

## Engine Authentication & Host Isolation

Because Siraugga is designed to run locally, it relies on the underlying Antigravity CLI for Google OAuth 2.0 authentication. 

### Cross-Environment Isolation (WSL vs Windows)
The application strictly treats Windows and WSL as completely isolated environments with separate credentials:
1. **WSL (Linux Development)**: The CLI stores Google OAuth tokens in the Linux user's home directory (e.g., ~/.config/gcloud/...). 
2. **Windows (Native Deployment)**: When Siraugga.exe runs on a Windows machine, the bundled Windows gy.exe binary looks for credentials in the native Windows path (e.g., %APPDATA%\gcloud\...).

Because these environments do not cross-pollinate configurations, deploying the .exe to the Windows host inherently tests the "fresh install" unauthenticated experience, while leaving the developer's WSL server safely logged in.

### Testing the OAuth Setup Flow (Scrubbing)
To repeatedly test the first-time Google OAuth onboarding experience on a Windows host without having to manually hunt down Windows %APPDATA% folders:

1. Launch Siraugga.exe.
2. The backend will verify the hardware .devcore_master.key and log you in automatically as Super Admin.
3. Click the **key icon** in the top right to open the **Access Key Management** dashboard.
4. Under **Engine Testing Controls**, click **Scrub Authentication**.

The /api/auth/scrub endpoint will securely wipe all known Google Application Default Credentials and Antigravity tokens *exclusively on the host machine* (leaving WSL untouched). The backend will immediately detect the unauthenticated state, execute the bundled CLI to generate a fresh Google OAuth login URL, and gracefully redirect the UI to the /login deployment overlay.

### Agent Privilege Flags & Selective Artifact Approvals

When an Antigravity AI Agent needs to execute a potentially destructive action, generate an architecture plan, or perform a sensitive operation (like modifying core engine code), it utilizes the `RequestFeedback` flag.

- **The `RequestFeedback: true` Hook**: When an agent attaches this flag to an Artifact (e.g., an Implementation Plan), the Antigravity CLI's internal "Stop Hook" engages. This forcibly halts the agent's background execution process, preventing any further terminal commands or code writes until the user manually activates the **Proceed** button in the Web UI.
- **Global Auto-Approve Override**: If the host environment is launched with global admin override flags (such as `--dangerously-skip-permissions` or equivalent CLI settings), the Stop Hook is immediately bypassed. The CLI will automatically intercept the `RequestFeedback` flag, auto-approve the artifact, and wake the agent back up without waiting for frontend user interaction.
- **Selective Approval Workflow**: For optimal efficiency and safety, global auto-approve should be **disabled**. This delegates the decision-making power to the Agent: it will execute safe, routine code edits silently without requesting permission, but will intentionally trigger a hard pause (via `RequestFeedback: true`) when it detects a high-risk system modification that warrants mandatory human review.
