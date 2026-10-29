#!/usr/bin/env python3
"""Headless Google OAuth Unix Domain Socket daemon for Antigravity CLI authentication."""
import os
import sys
import time
import json
import socket
import shutil
import select
import tempfile
import subprocess
import re

SOCK_PATH = "/tmp/agy_auth.sock"
STATE_PATH = "/tmp/agy_auth_state.json"


def cleanup(staging_dir=None, server_sock=None):
    if server_sock:
        try:
            server_sock.close()
        except Exception:
            pass
    if os.path.exists(SOCK_PATH):
        try:
            os.unlink(SOCK_PATH)
        except Exception:
            pass
    if os.path.exists(STATE_PATH):
        try:
            os.unlink(STATE_PATH)
        except Exception:
            pass
    if staging_dir and os.path.exists(staging_dir):
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass


def main():
    print(f"[auth_daemon] Started at {time.time()} (pid={os.getpid()}, python={sys.executable})", flush=True)
    if os.path.exists(SOCK_PATH):
        try:
            os.unlink(SOCK_PATH)
        except Exception:
            pass

    staging_dir = tempfile.mkdtemp(prefix="agy_oauth_")
    print(f"[auth_daemon] Created staging dir: {staging_dir}", flush=True)

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["HOME"] = staging_dir
    env["GEMINI_CLI_HOME"] = staging_dir
    local_bin = os.path.expanduser("~/.local/bin")
    if "PATH" in env and local_bin not in env["PATH"]:
        env["PATH"] = f"{local_bin}:{env['PATH']}"

    pa_proxy = "http://proxy.server:3128"
    is_pa = False
    try:
        socket.gethostbyname("proxy.server")
        is_pa = True
    except Exception:
        pass

    if not is_pa:
        is_pa = (
            "PYTHONANYWHERE_DOMAIN" in os.environ
            or "PYTHONANYWHERE_SITE" in os.environ
            or "mikeymike" in os.path.abspath(__file__).lower()
            or "pythonanywhere" in os.path.abspath(__file__).lower()
            or os.path.exists("/var/www")
        )

    if is_pa:
        env["http_proxy"] = pa_proxy
        env["https_proxy"] = pa_proxy
        env["HTTP_PROXY"] = pa_proxy
        env["HTTPS_PROXY"] = pa_proxy
        env["all_proxy"] = pa_proxy
        env["ALL_PROXY"] = pa_proxy
        env["no_proxy"] = "localhost,127.0.0.1"
        env["NO_PROXY"] = "localhost,127.0.0.1"

    agy_bin = shutil.which("agy")
    if not agy_bin:
        fallback = os.path.expanduser("~/.local/bin/agy")
        agy_bin = fallback if os.path.exists(fallback) else None

    if not agy_bin:
        print("[auth_daemon] ERROR: agy binary not found!", flush=True)
        cleanup(staging_dir)
        sys.exit(1)

    print(f"[auth_daemon] Using agy binary: {agy_bin}", flush=True)
    cmd = ["script", "-q", "-c", f"{agy_bin} --print ping", "/dev/null"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except Exception as e:
        print(f"[auth_daemon] ERROR spawning proc: {e}", flush=True)
        cleanup(staging_dir)
        sys.exit(1)

    url = None
    start_time = time.time()
    expires_at = start_time + 60.0

    print("[auth_daemon] Reading agy output...", flush=True)
    for _ in range(30):
        line = proc.stdout.readline()
        if not line:
            break
        print(f"[agy] {line.strip()}", flush=True)
        match = re.search(r"(https://accounts\.google\.com/[^\s'\"<>]+)", line)
        if match:
            url = match.group(1)
            break
        if "pong" in line.lower():
            print("[auth_daemon] Already authenticated!", flush=True)
            cleanup(staging_dir)
            sys.exit(0)

    if not url:
        print("[auth_daemon] ERROR: Failed to extract OAuth URL from output", flush=True)
        try:
            proc.kill()
        except Exception:
            pass
        cleanup(staging_dir)
        sys.exit(1)

    print(f"[auth_daemon] OAuth URL captured: {url[:60]}...", flush=True)
    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCK_PATH)
        server.listen(5)
        server.setblocking(False)
        print(f"[auth_daemon] Bound UDS socket at {SOCK_PATH}", flush=True)
    except Exception as e:
        print(f"[auth_daemon] ERROR binding socket: {e}", flush=True)
        try:
            proc.kill()
        except Exception:
            pass
        cleanup(staging_dir)
        sys.exit(1)

    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "pid": os.getpid(),
                    "url": url,
                    "created_at": start_time,
                    "expires_at": expires_at,
                    "status": "waiting",
                },
                f,
            )
    except Exception as e:
        print(f"[auth_daemon] WARNING writing state file: {e}", flush=True)

    print("[auth_daemon] Entering server loop...", flush=True)
    while time.time() < expires_at:
        if proc.poll() is not None:
            print(f"[auth_daemon] agy proc exited with code {proc.poll()}", flush=True)
            break

        r, _, _ = select.select([server], [], [], 0.5)
        if server in r:
            try:
                conn, _ = server.accept()
                conn.settimeout(15.0)
                raw_data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw_data += chunk
                    if b"\n" in raw_data:
                        break
                if not raw_data:
                    conn.close()
                    continue

                req = json.loads(raw_data.decode("utf-8"))
                action = req.get("action")
                print(f"[auth_daemon] Handling action: {action}", flush=True)

                if action == "status":
                    rem = max(0, int(expires_at - time.time()))
                    resp = {
                        "url": url,
                        "remaining": rem,
                        "active": proc.poll() is None and rem > 0,
                    }
                    conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                    conn.close()
                    continue

                elif action == "submit":
                    token = req.get("token", "").strip()
                    if not token:
                        conn.sendall(json.dumps({"success": False, "error": "No token provided"}).encode("utf-8") + b"\n")
                        conn.close()
                        continue

                    print("[auth_daemon] Writing token to proc.stdin...", flush=True)
                    proc.stdin.write(token + "\n")
                    proc.stdin.flush()

                    success = False
                    error_msg = None

                    for _ in range(35):
                        line = proc.stdout.readline()
                        if not line:
                            if proc.poll() is not None:
                                break
                            time.sleep(0.1)
                            continue
                        line_str = line.strip()
                        print(f"[agy-exchange] {line_str}", flush=True)
                        out = line_str.lower()
                        if any(
                            err in out
                            for err in [
                                "authentication failed",
                                "invalid code",
                                "invalid_grant",
                                "malformed",
                                "expired",
                                "bad request",
                                "token exchange failed",
                            ]
                        ):
                            error_msg = line_str
                            break
                        if any(
                            ok in out
                            for ok in [
                                "authentication successful",
                                "select ",
                                "project",
                                "workspace",
                                "pong",
                                "logged in",
                                "credentials saved",
                            ]
                        ):
                            success = True
                            break

                    scope = req.get("scope", "root")
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    src_token_path = os.path.join(staging_dir, ".gemini/antigravity-cli/antigravity-oauth-token")

                    if scope == "demo":
                        demo_dirs = [
                            os.path.join(base_dir, "demo"),
                            os.path.abspath(os.path.join(base_dir, "..", "..", "demo")),
                        ]
                        target_paths = []
                        for d_dir in demo_dirs:
                            target_paths.append(os.path.join(d_dir, ".gemini", "antigravity-cli", "antigravity-oauth-token"))
                            target_paths.append(os.path.join(d_dir, "antigravity-oauth-token"))
                    else:
                        eprofile_root = os.path.abspath(os.path.join(base_dir, "..", "..", ".."))
                        target_paths = [
                            os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token"),
                            os.path.join(eprofile_root, ".gemini", "antigravity-cli", "antigravity-oauth-token"),
                        ]

                    if os.path.exists(src_token_path):
                        try:
                            for dest_token_path in target_paths:
                                os.makedirs(os.path.dirname(dest_token_path), exist_ok=True)
                                shutil.copy2(src_token_path, dest_token_path)
                            print(f"[auth_daemon] Copied antigravity-oauth-token to {scope} destination(s)!", flush=True)
                            success = True
                        except Exception as copy_err:
                            error_msg = f"Failed to persist token: {copy_err}"

                    if success:
                        conn.sendall(
                            json.dumps({"success": True, "message": "Google OAuth authorization successful!"}).encode("utf-8") + b"\n"
                        )
                        conn.close()
                        break
                    else:
                        msg = error_msg or "Authentication failed or token rejected."
                        conn.sendall(json.dumps({"success": False, "error": msg}).encode("utf-8") + b"\n")
                        conn.close()
                        break
            except Exception as e:
                print(f"[auth_daemon] Exception in connection: {e}", flush=True)

    print("[auth_daemon] Shutting down and cleaning up...", flush=True)
    try:
        proc.kill()
    except Exception:
        pass
    cleanup(staging_dir, server)


if __name__ == "__main__":
    main()
