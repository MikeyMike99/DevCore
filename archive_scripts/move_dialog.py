with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

import re
# Find the dialog
dialog_pattern = re.compile(r'    <!-- Settings & Sessions Side Panel \(A11y Dialog\) -->.*?<\/dialog>', re.DOTALL)
match = dialog_pattern.search(html)
if match:
    dialog_content = match.group(0)
    # Remove it from current position
    html = html.replace(dialog_content, '')
    
    # Insert it right before the main script tag
    # The main script tag starts with <script>\n        var isTaskRunning = false;
    script_pattern = r'<script>\s*var isTaskRunning = false;'
    
    if re.search(script_pattern, html):
        html = re.sub(script_pattern, dialog_content + '\n    <script>\n        var isTaskRunning = false;', html)
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("Successfully moved dialog BEFORE the script tag.")
    else:
        print("Could not find the script tag.")
else:
    print("Could not find the dialog.")
