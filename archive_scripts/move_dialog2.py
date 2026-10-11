with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

import re
dialog_pattern = re.compile(r'    <!-- Settings & Sessions Side Panel \(A11y Dialog\) -->.*?<\/dialog>', re.DOTALL)
match = dialog_pattern.search(html)
if match:
    dialog_content = match.group(0)
    html = html.replace(dialog_content, '')
    
    # Just insert it before <script>
    html = html.replace('<script>', dialog_content + '\n    <script>', 1)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Moved successfully")
