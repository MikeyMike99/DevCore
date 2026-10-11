with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx_start = content.find("@app.route('/api/auth_check')")
idx_end = content.find("        except Exception as e:\n            return {\"success\": False, \"error\": str(e)}")
if idx_start == -1 or idx_end == -1:
    print("NOT FOUND", idx_start, idx_end)
    exit(1)
idx_end += len("        except Exception as e:\n            return {\"success\": False, \"error\": str(e)}")

replacement = '''GLOBAL_AUTH_PROC = None

@app.route('/api/auth_check')
async def auth_check():
    """Proactively tests if the CLI needs authentication by running a dummy command."""
    import sys
    import subprocess
    cmd = ['script', '-q', '-c', '/home/michael/.local/bin/agy --print ping', '/dev/null']
    if sys.platform == 'win32':
        cmd = ['wsl.exe'] + cmd
        
    def run_check():
        global GLOBAL_AUTH_PROC
        import subprocess
        import os
        import re
        
        # Kill any existing dangling process
        if GLOBAL_AUTH_PROC:
            try: GLOBAL_AUTH_PROC.kill()
            except: pass
            
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["WSLENV"] = "PYTHONUNBUFFERED/u"
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            
            # Read line by line synchronously
            for _ in range(5): # Don't read forever
                line = proc.stdout.readline()
                if not line:
                    break
                
                if "Authentication required" in line or "oauth2" in line or "Waiting for authentication" in line or "https://accounts.google.com" in line:
                    match = re.search(r'(https://accounts\.google\.com/[^\\s]+)', line)
                    if match:
                        GLOBAL_AUTH_PROC = proc
                        return {"authenticated": False, "url": match.group(1)}
                        
                if "pong" in line.lower():
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"authenticated": True}
                    
            try: proc.kill()
            except: pass
            GLOBAL_AUTH_PROC = None
            # If we get here, no URL or pong found
            return {"authenticated": False, "url": "#"}
        except Exception as e:
            print(f"Auth check error in thread: {e}")
            return {"authenticated": False, "url": "#"}
                
    try:
        result = await asyncio.to_thread(run_check)
        return jsonify(result)
    except Exception as e:
        print(f"Auth check error: {e}")
        return jsonify({"authenticated": False, "url": "#"})

@app.route('/login')
async def login_page():
    login_file = os.path.join(BASE_DIR, "templates", "login.html")
    if not os.path.exists(login_file):
        return "Login template not found", 404
    with open(login_file, 'r', encoding='utf-8') as f:
        return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/auth_submit', methods=['POST'])
async def auth_submit():
    print("[auth_submit] Starting request...")
    data = await request.get_json() or {}
    token = data.get('token', '').strip()
    if not token:
        print("[auth_submit] No token provided")
        return jsonify({"success": False, "error": "No token provided"})
        
    def run_submit():
        global GLOBAL_AUTH_PROC
        if not GLOBAL_AUTH_PROC:
            return {"success": False, "error": "No auth check process running"}
            
        proc = GLOBAL_AUTH_PROC
        try:
            proc.stdin.write(token + "\\n")
            proc.stdin.flush()
            
            for _ in range(15): # Max 15 lines
                line = proc.stdout.readline()
                if not line:
                    break
                    
                out = line.lower()
                if "authentication failed" in out or "invalid code" in out or "error" in out or "timed out" in out or "invalid_grant" in out or "malformed" in out:
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"success": False}
                    
                if "authentication successful" in out or "select " in out or "project" in out or "workspace" in out or "pong" in out:
                    try: proc.kill()
                    except: pass
                    GLOBAL_AUTH_PROC = None
                    return {"success": True}
                    
            try: proc.kill()
            except: pass
            GLOBAL_AUTH_PROC = None
            return {"success": True}
        except Exception as e:
            GLOBAL_AUTH_PROC = None
            return {"success": False, "error": str(e)}'''

new_content = content[:idx_start] + replacement + content[idx_end:]
with open('server.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patched!")
