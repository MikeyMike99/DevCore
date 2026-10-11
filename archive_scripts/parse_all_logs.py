import os
import json
import glob
from datetime import datetime

brain_dir = "/home/michael/.gemini/antigravity-cli/brain/"
all_prompts = []

for transcript_path in glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")):
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                # Look for user inputs
                if data.get('source') == 'USER_EXPLICIT' or data.get('type') == 'USER_INPUT':
                    content = data.get('content', '')
                    timestamp = data.get('created_at', '')
                    
                    if not content or not timestamp:
                        continue
                        
                    # Clean up the content (remove system instructions to reduce noise)
                    lines = content.split('\n')
                    clean_lines = [l for l in lines if not l.startswith('<') and not l.startswith('>')]
                    clean_content = '\n'.join(clean_lines).strip()
                    
                    if clean_content:
                        # Truncate giant copy-pastes
                        if len(clean_content) > 300:
                            clean_content = clean_content[:300] + " ... [TRUNCATED PASTED DATA]"
                        all_prompts.append({'time': timestamp, 'content': clean_content, 'file': transcript_path})
    except Exception as e:
        pass

# Sort chronologically
all_prompts.sort(key=lambda x: x['time'])

# Write out the timeline to a text file for analysis
with open("workspace_timeline.txt", "w", encoding="utf-8") as out:
    for p in all_prompts:
        out.write(f"[{p['time']}] {p['content']}\n")

print(f"Extracted {len(all_prompts)} prompts across all sessions. Saved to workspace_timeline.txt.")
