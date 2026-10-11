import re
with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

script_idx = html.find('<script>')
js_code = html[script_idx:]

ids_to_check = set(re.findall(r"getElementById\('([^']+)'\)", js_code))
print(f"IDs to check: {ids_to_check}")

missing = []
for id_ in ids_to_check:
    if f'id="{id_}"' not in html and f"id='{id_}'" not in html:
        missing.append(id_)

print(f"Missing IDs: {missing}")
