with open('session_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()
import re
match = re.search(r'def get_transcript.*?return', text, re.DOTALL)
if match:
    print(match.group(0))
else:
    print("Not found")
