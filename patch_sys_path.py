import os

with open("desktop_app.py", "r", encoding="utf-8") as f:
    content = f.read()

if "sys.path.insert(0, os.path.dirname(__file__))" not in content:
    patch = """
import sys
import os
try:
    sys.path.insert(0, os.path.dirname(__file__))
except NameError:
    pass
"""
    # Insert right after the first line (or top of file)
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            lines.insert(i, patch.strip())
            break
    
    with open("desktop_app.py", "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))
    print("Patched desktop_app.py with sys.path")
else:
    print("Already patched desktop_app.py")

with open("core/server.py", "r", encoding="utf-8") as f:
    content = f.read()

if "sys.path.insert(0, os.path.dirname(__file__))" not in content:
    patch = """
import sys
import os
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
except NameError:
    pass
"""
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            lines.insert(i, patch.strip())
            break
    
    with open("core/server.py", "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))
    print("Patched core/server.py with sys.path")
else:
    print("Already patched core/server.py")
