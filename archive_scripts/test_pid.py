import os
import psutil

for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmdline = p.info.get('cmdline', [])
        if cmdline and 'python3' in cmdline and 'server.py' in cmdline:
            with open(f'/proc/{p.info["pid"]}/environ', 'rb') as f:
                env = f.read().decode('utf-8', errors='ignore').split('\0')
                gemini = [e for e in env if 'GEMINI' in e]
                print(f"PID {p.info['pid']} GEMINI variables: {gemini}")
    except Exception as e:
        pass
