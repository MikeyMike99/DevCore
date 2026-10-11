with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's check where <dialog> is relative to <script>
script_pos = text.rfind('<script>')
dialog_pos = text.find('<dialog id="settings-panel"')
print(f"Main Script pos: {script_pos}")
print(f"Dialog pos: {dialog_pos}")
