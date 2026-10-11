with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print("File size:", len(text))
print("Script tag count:", text.count('<script'))
print("Body tag count:", text.count('</body'))
