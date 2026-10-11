with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()
script_start = html.find('<script>\n\n        // Custom UI Overrides')
script_end = html.find('</script>', script_start)
script_content = html[script_start:script_end]
with open('script_1.js', 'w', encoding='utf-8') as f:
    f.write(script_content)
