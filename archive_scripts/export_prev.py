import json
import re

path = '/home/michael/.gemini/antigravity-cli/brain/2292e072-e533-4e9a-8f00-722ba6d8acc7/.system_generated/logs/transcript_full.jsonl'
output = '/mnt/c/Users/michael/Documents/antigravity_test/previous_chat_export.md'

with open(path, 'r', encoding='utf-8') as f:
    msgs = [json.loads(line) for line in f]

with open(output, 'w', encoding='utf-8') as out:
    out.write("# Web Application Debugging (Previous Session Export)\n\n")
    for m in msgs:
        if m.get("type") == "USER_INPUT":
            out.write("### USER\n")
            content = m.get("content", "").replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
            out.write(content + "\n\n")
        elif m.get("type") == "PLANNER_RESPONSE":
            out.write("### AI\n")
            content = m.get("content", "").strip()
            content = re.sub(r'\[ARTIFACT: .*?\]\nPath: .*?\nLast Edited: .*?\n', '', content)
            out.write(content + "\n\n")
            
print("Export complete.")
