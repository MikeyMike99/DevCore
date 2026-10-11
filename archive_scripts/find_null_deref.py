with open('script_0.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'convSelector.' in line or 'projSelector.' in line or 'modelSelector.' in line:
        print(f"L{i+1}: {line.strip()}")
