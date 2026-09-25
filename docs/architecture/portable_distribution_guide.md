# Portable Executable Distribution & Stamping Guide

## Overview
The DevCore application has been completely decoupled from the developer's local environment. It now operates as a 100% self-contained, portable Windows executable (`.exe`). This document details the infrastructure that makes this portability possible, and the workflows for distributing customized, time-locked versions of the app to clients.

---

## 1. The Bundled Engine Architecture (Zero-Install)
Previously, the Python backend relied on the host computer having the Google Antigravity CLI (`agy`) installed via `pip`. This broke portability.
- **The Solution:** During the automated SSH compilation phase, the new `remote_compiler.py` script actively hunts down the `agy.exe` binary on the Windows build server.
- **Nuitka Injection:** It injects `agy.exe` directly into the Nuitka compilation payload using the `--include-data-file` flag. 
- **Dynamic Routing:** When the final `.exe` boots on a fresh machine, `agent_manager.py` and `server.py` check `sys.frozen`. If compiled, they extract the hidden `agy.exe` from the internal temporary payload and use it as the AI brain. No external dependencies are required.

---

## 2. Client Authentication & Quota Protection
To prevent distributed clients from draining the Master Developer's personal Google AI API quota, the authentication flow was overhauled:
1. **API Key Injection:** The `login.html` screen now features a "Google API Key" input box. 
2. **OAuth Bypass:** When a client enters their API key, the Quart server seamlessly injects it into the environment variables (`os.environ["GEMINI_API_KEY"]`) and terminates the legacy terminal-based OAuth flow. The bundled `agy` engine instantly picks up this key and uses the client's billing quota.
3. **Smooth UX:** The "Login Required" prompt is rendered as a non-intrusive blurred overlay on the main dashboard. Clicking it opens the login screen in a new tab. Upon successful authentication, the tab automatically closes itself, and the original dashboard instantly reloads, granting access.

---

## 3. The Binary Stamping Engine (Time-Locked Trials)
Compiling a 40MB+ Nuitka executable takes time. It is highly inefficient to recompile the entire source code every time a client needs a custom trial date. To solve this, we implemented the **Binary Stamper** (`security/stamper.py`).

### How it Works
1. **The Magic Append:** An `.exe` file can have arbitrary data appended to the very end of its binary structure without corrupting the executable. 
2. **The Injection:** The `stamper.py` script copies the master `.exe` and appends a JSON payload wrapped in magic bytes (`---AGY_STAMP_START---` and `---AGY_STAMP_END---`) directly to the bottom of the new file. This takes 0.1 seconds.
3. **The Reader:** When a stamped `.exe` launches, the Python code inside opens its own binary file (`sys.executable`), seeks to the end, extracts the JSON, and evaluates the `expires` timestamp.
4. **The Lockout:** If the current date exceeds the stamped expiration date, `server.py` broadcasts an `expired: True` payload. The UI instantly throws an inescapable red "Trial Expired" lock screen.

---

## 4. Master Developer Auto-Bypass
*Crucial Rule: The creator must never be locked out of their own creation.*

Even if the Master Developer launches a Stamped/Expired client `.exe`, the application performs a zero-trust check on the host machine. 
1. It looks for `.devcore_master.key` in the local directory.
2. It hashes the file using SHA-256 and compares it against the hardcoded expected hash in `security_manager.py`.
3. If it matches, the app completely ignores the Binary Stamp, ignores the API Key requirement, and instantly grants full Master Admin access. 

---

## 5. Standard Operating Procedure: Distributing an App
When you want to give a customized trial version of the app to a friend or client:

**Step 1: Compile the Master EXE (Only needed when code changes)**
Run your standard build script to generate the generic `Siraugga.exe`.
```bash
./build_remote.sh
```

**Step 2: Stamp a Client Version (Instant)**
Run the stamper utility to duplicate the master `.exe` and inject the client's custom expiration payload.
```bash
python3 security/stamper.py --source Siraugga.exe --dest Client_John.exe --id JOHN-001 --days 7
```

**Step 3: Distribute**
Hand `Client_John.exe` to John. When John runs it, it will politely ask him for his Google API key, allow him to use it for exactly 7 days, and then permanently lock itself. 
