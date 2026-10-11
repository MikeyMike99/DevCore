import re
with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r'\s*document\.addEventListener\(\'keydown\', function\(e\) \{\s*if \(e\.altKey && e\.key\.toLowerCase\(\) === \'s\'\) \{\s*e\.preventDefault\(\);\s*document\.getElementById\(\'prompt\'\)\.value = \'Create a new Sandbox Environment\';\s*document\.getElementById\(\'prompt\'\)\.focus\(\);\s*\} else if \(e\.altKey && e\.key\.toLowerCase\(\) === \'l\'\) \{\s*e\.preventDefault\(\);\s*document\.getElementById\(\'prompt\'\)\.value = \'Analyze system logs for the last 24 hours\';\s*document\.getElementById\(\'prompt\'\)\.focus\(\);\s*\} else if \(e\.altKey && e\.key\.toLowerCase\(\) === \'c\'\) \{\s*e\.preventDefault\(\);\s*document\.getElementById\(\'prompt\'\)\.focus\(\);\s*\}\s*\}\);'

new_text = re.sub(pattern, '', text)
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(new_text)

print(f'Replaced {len(re.findall(pattern, text))} occurrences.')
