with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

count = text.count('id="prompt"')
print(f"Number of prompt elements: {count}")
