with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

count = text.count('id="settings-panel"')
print(f"Number of settings panels: {count}")
