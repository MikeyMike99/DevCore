with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.split('\n')
for i, line in enumerate(lines):
    if '<script' in line or '</script' in line or '<dialog' in line or '</dialog' in line:
        print(f"L{i+1}: {line.strip()}")
