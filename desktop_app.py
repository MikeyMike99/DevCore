import threading
import time
import urllib.request
import sys
import os
import subprocess

# Safeguard for --windows-disable-console where stdout/stderr can be None
if sys.stdout is None:
    sys.stdout = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stdout.log"), "a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stderr.log"), "a", encoding="utf-8", buffering=1)

try:
    import webview
except ImportError:
    print("CRITICAL ERROR: 'pywebview' is not installed.")
    print("Please run: pip install pywebview")
    sys.exit(1)

import asyncio

shutdown_event = asyncio.Event()

def start_server():
    """Starts the DevCore backend in a background thread using Hypercorn ASGI."""
    try:
        from hypercorn.config import Config
        from hypercorn.asyncio import serve
        import core.server as server
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        config = Config()
        config.bind = ["127.0.0.1:5000"]
        
        print("Starting DevCore Backend on 5000 (Hypercorn ASGI Thread)")
        # Explicit shutdown_trigger bypasses Hypercorn signal installation in worker threads
        loop.run_until_complete(serve(server.app, config, shutdown_trigger=shutdown_event.wait))
    except Exception as e:
        with open("crash_log.txt", "w") as crash_file:
            import traceback
            crash_file.write(traceback.format_exc())
        print(f"CRASH: {e}")

def wait_for_server():
    """Polls localhost until the backend is fully booted and responsive."""
    print("Waiting for DevCore backend to boot...")
    max_retries = 30
    for _ in range(max_retries):
        try:
            urllib.request.urlopen("http://localhost:5000", timeout=1)
            print("Backend is online! Launching Desktop UI...")
            return True
        except Exception:
            time.sleep(0.5)
    
    print("ERROR: Backend failed to start in time.")
    with open("crash_log.txt", "a") as crash_file:
        crash_file.write("ERROR: Backend failed to start in time.\n")
    return False

if __name__ == '__main__':
    # 1. Start the backend daemon in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Wait for the server to be ready
    if wait_for_server():
        try:
            # 3. Create the Native Desktop Window wrapper around our web UI
            webview.create_window(
                title="Siraugga", 
                url="http://localhost:5000",
                width=1280,
                height=800,
                min_size=(800, 600),
                background_color='#0f172a' # Matches Tailwind slate-900 background
            )
            
            # 4. Start the native window event loop
            webview.start(gui='edgechromium,mshtml')
        except Exception as e:
            import traceback
            with open("crash_log_ui.txt", "w") as crash_file:
                crash_file.write(traceback.format_exc())
            print(f"UI CRASH: {e}")
        finally:
            shutdown_event.set()
