import re

html_path = 'templates/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = '            <button type="button" aria-controls="settings-panel"'
new_button = '            <button onclick="clearHistory()" aria-label="Clear chat history display" class="text-sm px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 font-bold focus:ring-2 focus:ring-teal-500 focus:outline-none transition-colors">Clear View</button>\n'

if target in content:
    content = content.replace(target, new_button + target)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Clear View button added to top header.")
else:
    print("Could not find insertion point.")
