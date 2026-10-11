import json
import sys

log_path = "/home/michael/.gemini/antigravity-cli/brain/dc050622-f394-4dfb-9adc-0d1dfd2ea993/.system_generated/logs/transcript.jsonl"
try:
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            if data.get('source') == 'USER_EXPLICIT' or data.get('type') == 'USER_INPUT':
                content = data.get('content', '')
                if content:
                    lines = content.split('\n')
                    clean_content = '\n'.join([line for line in lines if not line.startswith('<')])
                    print("---")
                    print(clean_content.strip())
except Exception as e:
    print(e)
