
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

### Architecture Decision: File Path Handling (`os.path` vs `pathlib`)

Throughout the DevCore and Antigravity server backend, file paths are manipulated using the legacy `os.path` string-based module rather than the modern object-oriented `pathlib` library. This is a deliberate, critical architectural decision to preserve the Windows-to-WSL bridge.

- **The Danger of `pathlib`**: `pathlib` objects are highly OS-aware. If the Python backend running natively on Windows receives a raw Linux path (e.g., `/home/michael/.gemini/...`) from the frontend WebSocket, `pathlib` will automatically attempt to normalize it into a Windows format (converting forward slashes to backslashes and injecting drive letters like `C:\`). This instantly destroys the payload before it can be passed to the `wsl.exe` subsystem.
- **The Safety of `os.path`**: `os.path` treats file routes as "dumb strings". It allows the Windows Python backend to safely hold, concatenate, and evaluate raw Linux strings without mutating them. This ensures that logic like `path.startswith("/")` remains reliable for detecting WSL-bound payloads and routing them securely across the OS boundary.

## Swarm Orchestration Engine

When passing gigabytes of code, transcripts, or logs to a single Pro model, the token window will inevitably throttle or crash. To solve this, the \gents/swarm_orchestrator.py\ intercepts massive files and chunks them into ~7,000 token blocks.

**Under the Hood**: 
Instead of querying sequentially, the Swarm Orchestrator spawns an asynchronous fleet of 'Flash Sub-Agents' (\gemini-3.8-flash-low\). Each sub-agent compresses its designated chunk into a chronological summary. The Orchestrator stitches these distilled summaries back together, achieving 90%+ compression before passing the final payload to the Main Agent.

**How Developers Can Use & Test It**: 
The orchestrator handles this automatically when large payloads are detected by the Agent Manager. To test it, developers can manually instantiate \SwarmOrchestrator()\ in a script and pass it a massive text payload using \wait orchestrator.distill_massive_file(path)\. The terminal will log the parallel sub-agent deployment.

## Autonomous Self-Healing Loop

The \self_heal.py\ module is the fail-safe wrapper around the main engine to prevent the application from dropping the user into a broken state.

**Under the Hood**: 
When the core application catches a fatal exception (like an \AttributeError\ or \SyntaxError\ during a hot-patch), the crash traceback is caught by \heal_crash()\. This function makes a direct API call to Gemini, bypassing the standard agent architecture, and requests a raw Python patch script to fix the bug. It executes the patch via \subprocess\, and if successful, uses \os.execv()\ to completely reload the running Python process in-place.

**How Developers Can Use & Test It**: 
To test the self-heal loop, a developer can intentionally inject a syntax error into a non-critical module (e.g., \core/server.py\) and trigger a reload. Watch the console: the traceback will fire, the AI will generate the \	emp_repair.py\ script, execute it, and seamlessly restart the server without the process ever dying.

## Chapter X: Troubleshooting Cross-Origin Security in Zero-Trust
When embedding external plugins (e.g., YouTube IFrames) inside a secure environment:
1. **CSP Blind Spots**: If your `security_headers.py` lacks a `report-uri`, the browser will silently kill unauthorized scripts, leaving no backend logs. Always configure a telemetry pipeline to catch silent blocks.
2. **Iframe `postMessage` Blocking**: HTML buttons in a parent wrapper cannot programmatically command a child iframe unless the child API verifies the parent's origin (e.g., passing `origin: window.location.origin` to YouTube).
3. **Gesture Delegation**: A user clicking a button in a parent wrapper does not unlock unmuted media in a child iframe unless the parent explicitly delegates the gesture via `allow="autoplay"`.

## Enterprise Key Management System (KMS) & Encryption Architecture

DevCore implements a highly robust, dual-layer Zero-Trust encryption model designed to protect data at rest and data in transit without sacrificing backend readability or breaking UI integrations.

### 1. Data in Transit (Dual-Binding TLS)
The Hypercorn ASGI server (`desktop_app.py` & `server.py`) is configured with a custom Dual-Binding strategy:
- **`https://0.0.0.0:5001`**: Binds to all interfaces and is fully encrypted via a self-generated RSA-2048 TLS Certificate (`cert.pem`). This port is strictly used for external/network access.
- **`http://127.0.0.1:5000` (Insecure Bind)**: Binds exclusively to the localhost loopback. The native PyWebview desktop UI connects solely via this port to prevent "Invalid Certificate" blocks from the Edge Chromium engine while maintaining physical isolation from the network.

### 2. Token Hashing (At Rest)
Instead of storing plaintext credentials in JSON files, DevCore hashes all security tokens before they touch the disk:
- **API Keys (`.devcore_keys.json`)**: Uses `werkzeug.security` (scrypt/pbkdf2) for high-latency hashing against brute-force attacks.
- **Session Tokens (`sessions.json`)**: Uses fast `SHA-256` digests, ensuring high-frequency API authorization requests are processed instantly without lagging the server.
- **Backward Compatibility**: The authenticator automatically checks if a stored key begins with `scrypt:` to gracefully bridge legacy plaintext keys alongside new hashes, ensuring zero user lockout.

### 3. The `KeychainManager` (KMS)
The system leverages a dynamic, rotatable Key Management System located in `security/keychain.py`:
- **Hardware KEK**: The master hardware key (`.devcore_master.key`) acts as the root seed. PBKDF2 (100,000 iterations) derives a massive Key Encryption Key (KEK) from it.
- **Rotatable DEKs**: The KMS generates Fernet Data Encryption Keys (DEKs) wrapped by the KEK and stores them in `.devcore_keychain.json`. The active key can be rotated at any time.

### 4. Cold Storage Architecture
To protect the AI's Brain Transcripts (`transcript.jsonl`) without breaking the native Google Antigravity JSON parser, DevCore employs lifecycle "Cold Storage" hooks (`security/cold_storage.py`):
- **Lock (Shutdown)**: When the DevCore UI is closed, a background hook sweeps the `.gemini/antigravity-cli/brain/` directory and encrypts all transcripts into unreadable AES-128 ciphertext.
- **Unlock (Boot)**: When DevCore starts up, a pre-boot hook pulls the entire historical keychain to attempt decryption. If an old key unlocks a file, it is rewritten as plaintext. Upon the next shutdown, it is automatically re-encrypted using the *newest active key*, conferring immunity to cryptographic shredding during key rotations.

### 5. Risk Analysis: Benefits vs. Dangers
Encrypting internal system data (like AI transcripts and access tokens) introduces a sharp double-edged sword:

**The Security Benefits:**
- **Zero-Trust Hardening:** If an attacker compromises the host OS or physically steals the hard drive, they cannot read the agent's historical memory or hijack active sessions. 
- **Data Exfiltration Defense:** Ransomware or malware that attempts to silently exfiltrate `~/.gemini/` directories will only upload useless AES ciphertext.
- **Access Control Enforcement:** Even developers with physical file access cannot inject prompt-injection attacks into the AI's past memory or forge RBAC tokens, enforcing strict application-layer access controls.

**The Dangers (Self-Sabotage):**
- **Cryptographic Shredding:** If the hardware `.devcore_master.key` is accidentally deleted, corrupted, or regenerated, the KEK is permanently lost. Every single encrypted transcript in the system instantly becomes unrecoverable digital confetti, causing irreversible amnesia for the AI.
- **Process Crash Corruption:** If the DevCore Python process is forcefully killed (e.g., `SIGKILL` or power loss) *during* the `lock_brain` encryption sweep, the JSONL files may be left in a partially encrypted/corrupted state, fatally crashing the Antigravity JSON parser on the next boot.
- **Debugging Blindness:** Because the logs are locked into ciphertext when the server is powered down, system administrators cannot easily use native terminal tools (like `grep` or `tail`) to audit the AI's logs or debug crashes offline unless they manually invoke the `unlock_brain()` Python script first.

### 6. Risk Remediation Strategies
To mitigate the dangers of self-sabotage, DevCore employs the following strict remediations:
- **Mitigating Shredding (Key Backups)**: System Administrators *must* maintain an off-site, secure backup of the physical `.devcore_master.key` and `.devcore_keychain.json` files. If the primary OS drive fails, these files are the only way to recover the AI's Brain Transcripts from the cold storage ciphertext.
- **Mitigating Power-Loss (Atomic Writes)**: The `cold_storage.py` sweeps do NOT write ciphertext directly over the plaintext files. Instead, they write to a `.tmp` file and execute an OS-level `os.replace()` atomic swap. If the server loses power mid-write, the original file remains perfectly intact.
- **Mitigating Blindness (CLI Tooling)**: The `security/cold_storage.py` script is built as a standalone CLI tool. Admins can run `python3 security/cold_storage.py unlock` at any time while the server is down to instantly decrypt the logs for manual `grep` auditing, and `lock` to seal them back up.
- **Mitigating CWE-377 (Insecure Temporary Files)**: When executing the atomic swaps, the encryption sweeps do NOT use predictable string concatenation (like `file.tmp`). Instead, they leverage the native OS `tempfile.mkstemp()` API to securely allocate a randomized, collision-resistant file descriptor. This prevents rogue actors from launching symlink attacks (where a fake `.tmp` file is pointed at `/etc/passwd` to force the backend to overwrite sensitive OS files). If the atomic swap fails for any reason, a strict `try...except` wrapper instantly detonates the temporary file to prevent plaintext data from leaking to the disk.

## API Hardening & Raugus Architecture

To defend the backend against remote exploitation, DevCore implements strict API-level hardening alongside an abstracted path-resolution system.

### 1. Neutralizing CWE-78 (Command Injection)
System execution boundaries (such as passing arguments to `wsl.exe` for artifact operations) are strictly sanitized. Dynamic user inputs (like `path`) are wrapped in `shlex.quote()` to prevent breakout characters (e.g., `'; rm -rf /'`) from executing arbitrary bash commands. Furthermore, explicit boundary assertions (e.g., `startswith('/home/')`) guarantee the OS execution remains jailed to the intended directory.

### 2. Neutralizing CWE-284 (Broken Access Control)
All core utility endpoints are locked behind strict Bearer token authorization checks.
- **Artifact Protection**: The `/api/artifacts/save` endpoint explicitly verifies token validity to prevent unauthenticated users or CSRF scripts from overwriting system files.
- **DoS Defense**: Administrative endpoints, such as `/api/reload` (which triggers a high-overhead memory wipe of backend modules), strictly enforce the `can_reload_engine` Admin role check. This prevents unauthenticated actors from throwing the server into an endless Denial of Service loop.

### 3. The Raugus Resolver (Anti-Traversal)
Instead of exposing raw absolute filesystem paths to the frontend or network, the system utilizes the **Raugus Map** (`raugus_map.json`) and the **Raugus Resolver** (`security/raugus_resolver.py`). 
- **Alias Abstraction**: Critical system files are registered under an alias (e.g., `devcore.core.server.py`). 
- **Tier Verification**: When the frontend requests a file, it asks for the alias. The Raugus Resolver checks the map, verifies if the user's RBAC Tier is high enough to access that alias, and only then resolves it to a physical path internally. 
- **Traversal Immunity**: By abstracting the paths, attackers cannot use `../../../etc/passwd` because the resolver strictly matches hardcoded dictionary keys rather than traversing the OS filesystem.

## Option 2: Background Task Webhook
We added \/api/webhooks/agent_callback\ to \server.py\ to support long-running agent tasks without hitting timeouts. Agents can launch tasks via \
ohup\ and trigger the webhook using 
## Background Task Offloading (Asynchronous Webhooks)

To bypass standard API timeout limits and avoid blocking the AI Agent's execution thread during massive workloads (like heavy compilation, DAST vulnerability scans, or generating Cinematic TTS Audio), DevCore implements an **Asynchronous Webhook Callback** architecture.

### How It Works:
1. **Detached Execution (`nohup`)**: Instead of blocking, the agent executes long-running shell scripts detached in the background using `nohup bash -c "..." &`.
2. **Immediate Yield**: The agent immediately yields its turn back to the user, freeing up the system and preventing context-window timeouts.
3. **The Webhook Ping**: At the very end of the detached background script, a hardcoded `curl` payload executes, sending a POST request to `/api/webhooks/agent_callback` on the DevCore backend.
4. **Agent Wakeup**: The DevCore server intercepts this webhook and broadcasts a high-priority system message into the chat stream (`**Background Task Finished**`), physically waking the AI agent back up to analyze the log files and continue its work.
