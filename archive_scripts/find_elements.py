with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

for el in ['id="task-banner"', 'id="current-task-prompt"', 'id="task-model-badge"', 'id="timer-display"']:
    print(f"{el}: {'Found' if el in text else 'Not Found'}")
