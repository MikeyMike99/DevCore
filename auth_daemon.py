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
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / ".runtime"
try:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

_rt_sock = str(RUNTIME_DIR / "agy_auth.sock")
SOCK_PATH = _rt_sock if (not _rt_sock.startswith("/mnt/") and len(_rt_sock) < 95) else "/tmp/agy_auth.sock"
STATE_PATH = str(RUNTIME_DIR / "agy_auth_state.json")


def _iter_relative_roots():
    seen = set()
    for cand in (
        BASE_DIR,
        Path.cwd(),
        BASE_DIR.parent,
        BASE_DIR.parent.parent,
        BASE_DIR.parent.parent.parent,
        Path.home(),
    ):
        try:
            resolved = cand.resolve()
            if resolved not in seen and resolved.exists():
                seen.add(resolved)
                yield resolved
        except Exception:
            continue


def _find_agy_binary():
    for root in _iter_relative_roots():
        for rel in (
            Path(".local/bin/agy_real"),
            Path(".local/bin/agy"),
            Path("agy_real"),
            Path("agy"),
            Path("bin/agy"),
            Path("agy.exe"),
        ):
            cand = root / rel
            try:
                if cand.is_file() and cand.stat().st_size > 50:
                    if cand.name == "agy" and (cand.parent / "agy_real").is_file() and cand.stat().st_size < 4096:
                        return str(cand.parent / "agy_real")
                    return str(cand)
            except Exception:
                continue
    which_agy = shutil.which("agy")
    if which_agy and os.path.exists(which_agy) and os.path.getsize(which_agy) > 50:
        return which_agy
    return None


def cleanup(staging_dir=None, server_sock=None):
    if server_sock:
        try:
            server_sock.close()
        except Exception:
            pass
    for sp in (SOCK_PATH, "/tmp/agy_auth.sock"):
        if os.path.exists(sp):
            try:
                os.unlink(sp)
            except Exception:
                pass
    for st in (STATE_PATH, "/tmp/agy_auth_state.json"):
        if os.path.exists(st):
            try:
                os.unlink(st)
            except Exception:
                pass
    if staging_dir and os.path.exists(staging_dir):
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass


def main():
    print(f"[auth_daemon] Started at {time.time()} (pid={os.getpid()}, python={sys.executable})", flush=True)
    for sp in (SOCK_PATH, "/tmp/agy_auth.sock"):
        if os.path.exists(sp):
            try:
                os.unlink(sp)
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
    for root in _iter_relative_roots():
        bin_cand = root / ".local" / "bin"
        if bin_cand.is_dir():
            b_str = str(bin_cand)
            if "PATH" in env and b_str not in env["PATH"]:
                env["PATH"] = f"{b_str}:{env['PATH']}"
            elif "PATH" not in env:
                env["PATH"] = b_str

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

    agy_bin = _find_agy_binary()
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
    expires_at = start_time + 600.0

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

    state_payload = {
        "pid": os.getpid(),
        "url": url,
        "created_at": start_time,
        "expires_at": expires_at,
        "status": "waiting",
    }
    for st in (STATE_PATH, "/tmp/agy_auth_state.json"):
        try:
            with open(st, "w", encoding="utf-8") as f:
                json.dump(state_payload, f)
        except Exception as e:
            print(f"[auth_daemon] WARNING writing state file {st}: {e}", flush=True)

    print("[auth_daemon] Entering server loop...", flush=True)
    while time.time() < expires_at:
        if proc.poll() is not None:
            print(f"[auth_daemon] agy proc exited with code {proc.poll()}", flush=True)
            break

        r, _, _ = select.select([server], [], [], 0.5)
        if server in r:
            try:
                conn, _ = server.accept()
                conn.settimeout(30.0)
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

                    for _ in range(80):
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
                    src_candidates = [
                        os.path.join(staging_dir, ".gemini", "antigravity-cli", "antigravity-oauth-token"),
                        os.path.join(staging_dir, ".gemini", "antigravity", "antigravity-oauth-token"),
                        os.path.join(staging_dir, "antigravity-oauth-token"),
                    ]
                    src_token_path = next((p for p in src_candidates if os.path.exists(p) and os.path.getsize(p) > 8), None)

                    if scope == "demo":
                        demo_dirs = [
                            BASE_DIR / "demo",
                            Path.cwd() / "content" / "projects" / "demo",
                            BASE_DIR.parent.parent / "demo",
                        ]
                        target_paths = []
                        for d_dir in demo_dirs:
                            target_paths.append(str(d_dir / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"))
                            target_paths.append(str(d_dir / "antigravity-oauth-token"))
                    else:
                        target_paths = [
                            str(Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"),
                            str(BASE_DIR / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"),
                        ]
                        for root in _iter_relative_roots():
                            if (root / "server.py").is_file() and (root / "projects_mod.py").is_file():
                                target_paths.append(str(root / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"))

                    if src_token_path:
                        try:
                            for dest_token_path in dict.fromkeys(target_paths):
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
