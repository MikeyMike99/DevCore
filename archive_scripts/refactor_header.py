import re

html_path = 'templates/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the start of the controls div
start_marker = '        <div class="flex items-center gap-3">\n            <!-- User Status & Role Badge -->'
end_marker = '            </button>\n        </div>\n    </header>'

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker) + len(end_marker)
    
    original_controls = content[start_idx:end_idx]
    
    # We need to extract the Connection Status out of it to keep it in the header
    conn_start = original_controls.find('<!-- Connection Status -->')
    conn_end = original_controls.find('<!-- New Conversation Button -->')
    connection_badge = original_controls[conn_start:conn_end].strip()
    
    new_header_controls = f"""        <div class="flex items-center gap-3">
            {connection_badge}
            <button type="button" aria-controls="settings-panel" aria-expanded="false" onclick="document.getElementById('settings-panel').showModal()" class="text-sm px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-teal-400 font-bold focus:ring-2 focus:ring-teal-500 focus:outline-none transition-colors">
                Settings &amp; Sessions
            </button>
        </div>
    </header>"""

    # Replace the header part
    content = content.replace(original_controls, new_header_controls)
    
    # Now build the dialog body using the extracted controls.
    # We will strip the connection badge out of it, and fix some of the flex-row stuff to flex-col.
    dialog_controls = original_controls.replace('        <div class="flex items-center gap-3">\n', '')
    dialog_controls = dialog_controls.replace(connection_badge, '')
    dialog_controls = dialog_controls.replace('        </div>\n    </header>', '')
    
    # Make the inner controls flex-col for the sidebar
    dialog_controls = dialog_controls.replace('class="flex items-center gap-2 bg-slate-950/80', 'class="flex flex-col gap-2 bg-slate-900/80')
    dialog_controls = dialog_controls.replace('class="flex items-center gap-2 bg-slate-950/80 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs"', 'class="flex flex-col gap-2 bg-slate-900/80 border border-slate-700/80 rounded-lg p-3 text-sm"')
    dialog_controls = dialog_controls.replace('w-28', 'w-full').replace('w-32', 'w-full')
    
    # Bundle the loose buttons (New Session, Clear, Reload, Patch) into a flex row/col block
    loose_buttons_start = dialog_controls.find('<!-- New Conversation Button -->')
    if loose_buttons_start != -1:
        loose_buttons = dialog_controls[loose_buttons_start:]
        dialog_controls = dialog_controls[:loose_buttons_start]
        loose_buttons_wrapped = f"""            <div class="flex flex-col gap-2 mt-4 pt-4 border-t border-slate-800">\n    {loose_buttons}\n            </div>"""
        dialog_controls += loose_buttons_wrapped

    dialog_html = f"""
    <!-- Settings & Sessions Side Panel (A11y Dialog) -->
    <dialog id="settings-panel" class="bg-slate-950 text-slate-300 border-l border-slate-700 shadow-2xl h-full m-0 ml-auto w-80 backdrop:bg-slate-950/50 p-5 rounded-l-2xl open:flex flex-col gap-6" aria-label="Settings and Sessions">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-lg font-bold text-teal-400">Settings &amp; Sessions</h2>
            <button type="button" onclick="document.getElementById('settings-panel').close()" aria-label="Close Settings" class="text-slate-400 hover:text-white px-3 py-1 text-2xl font-bold rounded focus:ring-2 focus:ring-teal-500 focus:outline-none">&times;</button>
        </div>
        
        <div class="flex flex-col gap-4 overflow-y-auto">
{dialog_controls}
        </div>
    </dialog>
"""

    # Inject dialog right after header
    content = content.replace('    </header>', '    </header>\n' + dialog_html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Refactor successful.")
else:
    print("Could not find the target block.")

