import os
path = "/mnt/c/Users/michael/Documents/DevCore/core/server.py"
with open(path, "r") as f: c = f.read()

target = """    if sys.platform == "win32" and path.startswith("/"):
        try:
            redirect_op = ">>" if append_mode else ">"
            process = subprocess.Popen(
                ["wsl.exe", "-e", "bash", "-c", f"cat {redirect_op} {safe_path}"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = process.communicate(input=content)
            if process.returncode == 0:
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"WSL Artifact write failed: {stderr}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500"""

repl = """    if sys.platform == "win32" and path.startswith("/"):
        import tempfile
        try:
            # Mitigation for Broken Pipes on WSL: write to a Windows temp file first
            fd, tmp_path = tempfile.mkstemp(suffix=".md")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Use wsl.exe to copy the file into the Linux environment
            # wslpath -a converts the Windows path to a WSL path
            if append_mode:
                cmd = f"cat $(wslpath -a '{tmp_path}') >> {safe_path}"
            else:
                cmd = f"cp $(wslpath -a '{tmp_path}') {safe_path}"
                
            process = subprocess.Popen(
                ["wsl.exe", "-e", "bash", "-c", cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = process.communicate()
            
            try:
                os.remove(tmp_path)
            except:
                pass
                
            if process.returncode == 0:
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"WSL Artifact write failed: {stderr}"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Server patch applied")
else:
    print("Server target not found")
