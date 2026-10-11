import json
import re

path = 'C:/Users/michael/.gemini/antigravity/brain/f5e3c6ba-71ee-403b-8619-b0e1792b8d20/.system_generated/logs/transcript_full.jsonl'
output = 'C:/Users/michael/Documents/antigravity_test/chat_export.md'

with open(path, 'r', encoding='utf-8') as f:
    msgs = [json.loads(line) for line in f]

with open(output, 'w', encoding='utf-8') as out:
    out.write("# Web Application Debugging Chat Export\n\n")
    for m in msgs:
        if m.get("type") == "USER_INPUT":
            out.write("### USER\n")
            content = m.get("content", "").replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
            out.write(content + "\n\n")
        elif m.get("type") == "PLANNER_RESPONSE":
            out.write("### AI\n")
            content = m.get("content", "").strip()
            # Strip out artifact headers just to make it cleaner
            content = re.sub(r'\[ARTIFACT: .*?\]\nPath: .*?\nLast Edited: .*?\n', '', content)
            out.write(content + "\n\n")
            
print("Export complete.")
