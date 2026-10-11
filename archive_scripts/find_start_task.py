with open('agent_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = re.finditer(r'async def start_task', text)
for m in matches:
    start = m.start()
    end = min(len(text), start + 800)
    print("---")
    print(text[start:end])
