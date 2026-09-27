import os
import sys
import subprocess
import urllib.request
import json
import re

def heal_crash(traceback_str):
    print("\n=======================================================")
    print("      CRITICAL CRASH DETECTED - INITIATING SELF-HEAL    ")
    print("=======================================================")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Self-heal aborted: No GEMINI_API_KEY found in environment.")
        return False
        
    print("Booting temporary AI agent to analyze traceback...")
    
    prompt = f"""
You are an autonomous self-healing agent for the Siraugga/DevCore project.
The main application just crashed with the following traceback:

{traceback_str}

Analyze the traceback, locate the buggy file, and provide a python script that will FIX the file when executed.
Your response MUST contain exactly one ```python block with the repair script.
The script should read the file, fix the syntax/indentation/bug, and write it back.
"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        
        text = result['candidates'][0]['content']['parts'][0]['text']
        
        match = re.search(r'```python\n(.*?)\n```', text, re.DOTALL)
        if not match:
            print("Failed to extract repair script from AI response.")
            return False
            
        repair_script = match.group(1)
        
        repair_path = "temp_repair.py"
        with open(repair_path, "w", encoding="utf-8") as f:
            f.write(repair_script)
            
        print("Applying AI-generated repair patch...")
        subprocess.run([sys.executable, repair_path], check=True)
        
        os.remove(repair_path)
        print("Patch applied successfully! Restarting main agent...")
        
        os.execv(sys.executable, [sys.executable] + sys.argv)
        
    except Exception as e:
        print(f"Self-healing failed: {e}")
        return False
