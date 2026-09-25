import threading
import time
import urllib.request
import sys
import os
import subprocess

try:
    import webview
except ImportError:
    print("CRITICAL ERROR: 'pywebview' is not installed.")
    print("Please run: pip install pywebview")
    sys.exit(1)

def start_server():
    """Starts the DevCore backend (Bootstrap Gateway) in a background process."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gateway_path = os.path.join(base_dir, "core", "bootstrap_gateway.py")
    
    # We spawn it as a subprocess to keep the architecture perfectly isolated
    subprocess.run([sys.executable, gateway_path], cwd=base_dir)

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
    return False

if __name__ == '__main__':
    # 1. Start the backend daemon in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 2. Wait for the server to be ready
    if wait_for_server():
        # 3. Create the Native Desktop Window wrapper around our web UI
        webview.create_window(
            title="Antigravity DevCore", 
            url="http://localhost:5000",
            width=1280,
            height=800,
            min_size=(800, 600),
            background_color='#0f172a' # Matches Tailwind slate-900 background
        )
        
        # 4. Start the native window event loop
        webview.start()
