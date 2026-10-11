with open('server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'elif data.get("type") == "prompt":' in line:
        print(f"Line {i+1}:")
        for j in range(i, i+30):
            print(lines[j].rstrip())
        break
