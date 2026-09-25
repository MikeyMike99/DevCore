import os
import sys
import shutil
import subprocess

print("==========================================")
print("  Antigravity Remote Compiler Initiated   ")
print("==========================================")

# 1. Dynamically locate the agy.exe engine on Robert's machine
agy_path = shutil.which('agy')

if not agy_path:
    # Fallback to checking the standard Python Scripts directory
    scripts_dir = os.path.join(os.path.dirname(sys.executable), 'Scripts')
    agy_path = os.path.join(scripts_dir, 'agy.exe')

if not agy_path or not os.path.exists(agy_path):
    print(f"CRITICAL ERROR: Could not find agy.exe at {agy_path}")
    sys.exit(1)

print(f"Found core AI engine at: {agy_path}")
print("Injecting AI engine into executable bundle...")

# 2. Build the Nuitka compilation command, dynamically injecting agy.exe
cmd = [
    "python", "-m", "nuitka", 
    "--assume-yes-for-downloads", 
    "--standalone", 
    "--onefile", 
    "--windows-disable-console", 
    "--include-data-dir=sandbox/templates=sandbox/templates",
    "--include-data-dir=sandbox/static=sandbox/static",
    "--include-data-file=core/ui_config.json=core/ui_config.json",
    f"--include-data-file={agy_path}=agy.exe",
    "--output-filename=Siraugga.exe",
    "desktop_app.py"
]

# 3. Execute Nuitka
subprocess.run(" ".join(cmd), shell=True)
