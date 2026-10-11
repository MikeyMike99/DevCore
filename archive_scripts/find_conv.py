with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.split('\n')
for i, line in enumerate(lines):
    if 'id="conversation-selector"' in line:
        print(f"L{i+1}: {line.strip()}")
