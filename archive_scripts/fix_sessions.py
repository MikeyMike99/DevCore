import json
import os

path = '/home/michael/.gemini/antigravity-cli/brain/session_ownership.json'
with open(path, 'r') as f:
    d = json.load(f)

for k, v in d.items():
    v['project'] = 'default'

with open(path, 'w') as f:
    json.dump(d, f, indent=2)

print("Fixed!")
