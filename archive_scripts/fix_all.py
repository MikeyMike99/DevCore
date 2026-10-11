import os
import json
import time

brain_dir = '/home/michael/.gemini/antigravity-cli/brain'
conv_dir = '/home/michael/.gemini/antigravity-cli/conversations'
meta_file = os.path.join(brain_dir, "session_ownership.json")

# Load existing
d = {}
if os.path.exists(meta_file):
    with open(meta_file, 'r') as f:
        d = json.load(f)

# Scan DBs
for f in os.listdir(conv_dir):
    if f.endswith('.db') and not f.startswith('conversation_summaries'):
        conv_id = f.replace('.db', '')
        if conv_id not in d:
            d[conv_id] = {
                "owner": "admin",
                "project": "default",
                "created_at": time.time()
            }
        else:
            d[conv_id]["project"] = "default"

with open(meta_file, 'w') as f:
    json.dump(d, f, indent=2)

print(f"Added {len(d)} sessions to ownership!")
