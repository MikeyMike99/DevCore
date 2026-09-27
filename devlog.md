
## [2026-09-27 12:15] Fixed Server Boot Sequence & Documented Startup
- **What was changed**: 
  - Restored the missing \if __name__ == '__main__':\ block to \core/server.py\.
  - Migrated the standalone execution of \core/server.py\ from Quart's flaky built-in dev server to the production-grade Hypercorn ASGI server for stable WebSocket connections.
  - Added a bypass hook to \uth_check\ that allows immediate frontend-to-backend connection if \GEMINI_API_KEY\ is present, skipping the fragile WSL-based dummy command check.
  - Documented the exact execution sequence of \Siraugga.exe\ inside \TEXTBOOK.md\.
- **Reasoning**: 
  - Running \core/server.py\ directly was failing silently without an entrypoint, and when added, the Quart WebSocket handshake was disconnecting immediately causing infinite "Connection Status" loading.
  - The CLI auth check was hanging and failing for local testing without WSL.
- **Next Steps**: Monitor the frontend connection stability for the user and proceed with Nuitka compiling once the python layer is fully verified as bug-free.


## [2026-09-27 12:35] Documented Master Signature Setup Sequence
- **What was changed**: Added documentation to \TEXTBOOK.md\ explaining the new Super Admin setup flow, hardware key signature verification, and RBAC key generation.
- **Reasoning**: Ensures the zero-config local authentication bootstrap mechanism and security model (SHA-256 verification of \.devcore_master.key\) is fully documented for future agent reference and testing.
- **Next Steps**: Maintain RBAC compliance in all newly generated backend endpoints.


## [2026-09-27 13:20] Documented Future OTA Update Sequence
- **What was changed**: Appended documentation for the LiveOverrideFinder and /api/reload OTA hot-patch sequence to TEXTBOOK.md.
- **Reasoning**: To explicitly detail the zero-downtime hot-swapping mechanism, fulfilling the "Maintain the Textbook" rule for dynamic module updates without recompiling Siraugga.exe.
- **Next Steps**: Continue writing and integrating dynamic self-healing patches utilizing this infrastructure.


## [2026-09-27 13:48] Restored Native Google OAuth Flow
- **What was changed**: Removed the manual GEMINI_API_KEY text input bypass from core/server.py and index.html. Refactored uth_check to dynamically resolve the location of the bundled gy.exe (or WSL binary) instead of hardcoding the developer's local WSL path. 
- **Reasoning**: The manual API key entry was too complicated for end users. The application should rely entirely on Antigravity's native Google OAuth flow. When deployed to a new PC, the engine will execute the bundled CLI, intercept the generated Google OAuth login URL, and render it in the UI so the user can sign in securely via Google.
- **Next Steps**: Continue testing the frontend OAuth interception sequence.


## [2026-09-27 14:32] Added Scrub Engine Authentication Control
- **What was changed**: Added /api/auth/scrub endpoint in core/server.py to wipe all known Google ADC credentials across both Windows Host paths and WSL paths. Integrated a red 'Scrub Authentication' button inside the Super Admin Settings dashboard.
- **Reasoning**: The primary developer requested a way to cleanly wipe the native Google OAuth state to reliably test the fresh-install Google Auth login sequence on the host without needing to manually hunt down Windows %APPDATA% or WSL ~/.config files.
- **Next Steps**: Continue monitoring the native OAuth interception in production.


## [2026-09-27 14:34] Fixed Scrub Authentication Host Isolation
- **What was changed**: Removed the WSL credential deletion logic (wsl.exe bash -c rm ...) from the /api/auth/scrub endpoint in core/server.py.
- **Reasoning**: The Windows native .exe should not interfere with the WSL development server's authentication state. The scrub function is now strictly isolated to the native Windows host credentials (e.g., %APPDATA%/gcloud/...), allowing the developer to safely simulate a fresh unauthenticated PC without breaking their active WSL environment.


## [2026-09-27 15:27] Fixed WSL RPC Crash (0x8007072c)
- **What was changed**: Removed creationflags=0x08000000 (CREATE_NO_WINDOW) when invoking wsl.exe across gents/agent_manager.py, gents/swarm_orchestrator.py, and core/server.py. Modified safe_env in gent_manager.py to preserve Windows environment variables (os.environ.copy()) instead of stripping them.
- **Reasoning**: The user encountered Wsl/Service/0x8007072c (The RPC call contains a handle that differs from the declared handle type). This is a known WSL2 inter-process communication defect caused by executing wsl.exe in a hidden console (via CREATE_NO_WINDOW) while piping standard handles. Additionally, WSL requires underlying Windows system variables (like SystemRoot) to successfully boot the LxssManager link, which was previously stripped by security measures.
- **Next Steps**: Await completion of uild_windows_native.bat to verify the fix natively.


## [2026-09-27 15:58] Fixed WSL Multiline Argument Parsing
- **What was changed**: Appended the -e (or --exec) flag to all wsl.exe subprocess invocations (["wsl.exe", "-e", ...]).
- **Reasoning**: By default, wsl.exe passes arguments to /bin/bash -c. If any argument contains newlines (such as a <SYSTEM_MESSAGE> prompt block), Bash splits the argument and attempts to execute the newline as a separate command, resulting in unexpected argument "" or command not found errors. Using -e forces WSL to bypass shell evaluation and execute the target binary directly with raw arguments preserved.

## [2026-09-27 15:45] Overhauled Artifact Viewer Accessibility & Fixed WSL Pipeline Bug
- **What was changed**: 
  - Redesigned the Flip Card Artifact Viewer to use a raw `<textarea class="artifact-raw-editor">` for direct editing, entirely replacing the buggy HTML-to-Markdown `turndown.js` translation layer.
  - Implemented an automatic JavaScript `.focus()` hook that snaps the screen reader directly into the textarea upon flipping the card, ensuring the user hears immediate "Edit Box" feedback.
  - Re-routed the `POST /api/artifacts/save` endpoint to bypass Python's buggy `wsl.exe` stdin pipeline. It now writes to a temporary file natively on Windows and uses `wsl.exe cp` via `wslpath -a` to guarantee reliable saves into the Linux subsystem.
  - Removed the `contenteditable` attributes that broke standard screen-reader form traversal keys (like the E-key).
- **Reasoning**: 
  - `contenteditable` stripped essential screen-reader landmarks, and the raw textarea without focus left visually impaired users unable to find the correct edit box.
  - Subprocess piping to `wsl.exe` `stdin` on Windows from Quart's async loop was silently hanging and failing to overwrite the markdown files on disk.
- **Next Steps**: Monitor the new HTTP endpoint for stability during active artifact review phases, and proceed with further Web Portal UI/RBAC enhancements.
