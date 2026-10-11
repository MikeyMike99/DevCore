import re

files = [
    "/mnt/c/Users/michael/Documents/antigravity_test/previous_chat_export.md",
    "/mnt/c/Users/michael/Documents/antigravity_test/chat_export.md"
]

keywords = ["desktop", "application", "mistake", "broken", "fix", "failed", "crash"]
context_lines = 3

for file in files:
    print(f"\n--- Searching {file} ---")
    try:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                # We specifically want instances where the user mentions falling back to the desktop app
                if "desktop" in line.lower() and ("app" in line.lower() or "fix" in line.lower() or "broken" in line.lower() or "mistake" in line.lower()):
                    print(f"Match found at line {i}:")
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    print("".join(lines[start:end]))
                    print("-" * 40)
    except Exception as e:
        print(f"Error reading {file}: {e}")
