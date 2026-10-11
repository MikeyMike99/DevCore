with open('test_script.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.strip().startswith('//'):
        continue
    l = line.replace('\\\"', '').replace('\\\'', '')
    if l.count('\"') % 2 != 0:
        print(f'Double quote mismatch at line {i+1}: {line.strip()}')
    if l.count('\'') % 2 != 0:
        print(f'Single quote mismatch at line {i+1}: {line.strip()}')
