with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

import re
dialog_pattern = re.compile(r'    <!-- Settings & Sessions Side Panel \(A11y Dialog\) -->.*?<\/dialog>\n*', re.DOTALL)
match = dialog_pattern.search(html)
if match:
    dialog_content = match.group(0)
    # Remove from current (head) location
    html = html.replace(dialog_content, '')
    
    # Find the actual main <script> tag which starts with <script>\n\n        // Custom UI Overrides
    main_script_idx = html.find('<script>\n\n        // Custom UI Overrides')
    if main_script_idx != -1:
        # Insert right before it
        html = html[:main_script_idx] + dialog_content + '    ' + html[main_script_idx:]
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("Moved dialog to right before the main script tag.")
    else:
        print("Main script tag not found!")
else:
    print("Dialog not found!")
