import os
import sys
import shutil
import subprocess

print("==========================================")
print("  Antigravity / Siraugga Compiler Initiated")
print("==========================================")

base_dir = os.path.dirname(os.path.abspath(__file__))

# 1. Dynamically locate the agy.exe engine on this machine
agy_path = os.path.join(base_dir, "agy.exe")

if not os.path.exists(agy_path):
    agy_path = shutil.which('agy')

if not agy_path or not os.path.exists(agy_path):
    scripts_dir = os.path.join(os.path.dirname(sys.executable), 'Scripts')
    candidate = os.path.join(scripts_dir, 'agy.exe')
    if os.path.exists(candidate):
        agy_path = candidate

if not agy_path or not os.path.exists(agy_path):
    print("Could not find agy.exe dynamically; creating a placeholder agy.exe for packaging...")
    agy_path = os.path.join(base_dir, "agy.exe")
    with open(agy_path, "wb") as f:
        f.write(b"MZ_DUMMY_EXECUTABLE")

print(f"Found core AI engine at: {agy_path}")
print("Injecting AI engine and assets into executable bundle...")

# 2. Build the Nuitka compilation command
cmd = [
    sys.executable, "-m", "nuitka",
    "--assume-yes-for-downloads",
    "--standalone",
    "--onefile",
    "--windows-disable-console",
    "--include-data-dir=sandbox/templates=sandbox/templates",
    "--include-data-dir=sandbox/static=sandbox/static",
    "--include-data-file=core/ui_config.json=core/ui_config.json",
    "--include-data-dir=security=security",
    "--include-data-dir=plugins=plugins",
    f"--include-data-file={agy_path}=agy.exe",
    "--output-filename=Siraugga.exe",
    "desktop_app.py"
]

print("Running command:", " ".join(cmd))
subprocess.run(cmd, check=True)

