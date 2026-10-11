import re

with open("templates/index.html", "r") as f:
    html = f.read()

# 1. Remove ALL <dialog id="settings-panel"> blocks
# We use regex to find all matching blocks and remove them
dialog_pattern = re.compile(r'<!-- Settings & Sessions Side Panel.*?</dialog>\n*', re.DOTALL)
html = re.sub(dialog_pattern, '', html)

# 2. Extract model selector text (in case I need it, but I'll just write it cleanly)
model_selector_html = """            <!-- Model Selection Dropdown -->
            <div class="flex items-center gap-2 bg-slate-900/80 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs">
                <label for="model-selector" class="text-xs font-semibold text-teal-400 shrink-0">Model:</label>
                <select id="model-selector" onchange="onModelChange()" aria-label="Select AI Model" class="bg-transparent text-slate-200 text-xs font-medium focus:outline-none cursor-pointer pr-1">
                    <option value="gemini-3.8-flash-high" selected>Gemini 3.8 Flash (Fast &amp; Responsive)</option>
                    <option value="gemini-3.1-pro-high">Gemini 3.1 Pro (Deep Reasoning &amp; Planning)</option>
                    <option value="claude-sonnet-4-6">Claude Sonnet 4.6 (Thinking)</option>
                    <option value="claude-opus-4-6-thinking">Claude Opus 4.6 (Complex Coding)</option>
                    <option value="gpt-oss-120b-medium">GPT-OSS 120B (Medium)</option>
                </select>
            </div>"""

# 3. Add model selector to the main header right before the connection badge
header_insertion_point = '            <!-- Connection Status -->'
if header_insertion_point in html:
    html = html.replace(header_insertion_point, model_selector_html + '\n\n' + header_insertion_point)

# 4. Reconstruct the clean side panel without the admin bypass checkbox
clean_dialog = """
    <!-- Settings & Sessions Side Panel (A11y Dialog) -->
    <dialog id="settings-panel" class="bg-slate-950 text-slate-300 border-l border-slate-700 shadow-2xl h-full m-0 ml-auto w-80 backdrop:bg-slate-950/50 p-5 rounded-l-2xl open:flex flex-col gap-6" aria-label="Settings and Sessions">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-lg font-bold text-teal-400">Settings &amp; Sessions</h2>
            <button type="button" onclick="document.getElementById('settings-panel').close()" aria-label="Close Settings" class="text-slate-400 hover:text-white px-3 py-1 text-2xl font-bold rounded focus:ring-2 focus:ring-teal-500 focus:outline-none">&times;</button>
        </div>
        
        <div class="flex flex-col gap-4 overflow-y-auto">
            <!-- User Status & Role Badge (Without Bypass Checkbox) -->
            <div id="user-pill" class="flex flex-col gap-2 bg-slate-900/80 border border-slate-700/80 rounded-lg px-2.5 py-2 text-sm">
                <span id="user-role-badge" class="px-1.5 py-0.5 rounded text-xs font-bold bg-teal-900 text-teal-300 w-fit">ADMIN</span>
                <span id="user-display-name" class="font-medium text-slate-200">Guest</span>
                <div class="flex gap-2 mt-1">
                    <button onclick="toggleLoginModal()" id="login-btn" class="flex-1 text-xs text-teal-400 hover:text-teal-200 font-bold bg-slate-800 px-2 py-1.5 rounded border border-teal-800/50">Login</button>
                    <button onclick="logout()" id="logout-btn" class="hidden flex-1 text-xs text-rose-400 hover:text-rose-200 font-bold bg-slate-800 px-2 py-1.5 rounded border border-rose-800/50">Logout</button>
                </div>
            </div>

            <!-- Project Selector -->
            <div class="flex flex-col gap-2 bg-slate-900/80 border border-slate-700/80 rounded-lg p-3">
                <label for="project-selector" class="text-xs font-semibold text-teal-400 shrink-0">Project Workspace:</label>
                <select id="project-selector" onchange="switchProject()" aria-label="Select Project Workspace" class="bg-transparent border border-slate-700 rounded text-slate-200 text-sm font-medium focus:outline-none cursor-pointer p-1 w-full truncate">
                    <option value="">(Loading...)</option>
                </select>
                <div class="flex gap-2 mt-1">
                    <button onclick="newProject()" title="New Project" aria-label="Create New Project" class="flex-1 text-teal-400 hover:bg-slate-800 text-xs font-bold py-1 rounded border border-slate-700 transition-colors">+ New</button>
                    <button onclick="clearProjectSessions()" title="Clear Project Sessions" aria-label="Clear all sessions for this project" class="flex-1 text-rose-400 hover:bg-slate-800 text-xs font-bold py-1 rounded border border-slate-700 transition-colors">🗑️ Clear</button>
                </div>
            </div>

            <!-- Conversation Selector -->
            <div class="flex flex-col gap-2 bg-slate-900/80 border border-slate-700/80 rounded-lg p-3">
                <label for="conversation-selector" class="text-xs font-semibold text-teal-400 shrink-0">Current Session:</label>
                <select id="conversation-selector" onchange="switchConversation()" aria-label="Select Conversation" class="bg-transparent border border-slate-700 rounded text-slate-200 text-sm font-medium focus:outline-none cursor-pointer p-1 w-full truncate">
                </select>
                <div class="flex gap-2 mt-1">
                    <button onclick="renameConversation()" title="Rename Session" aria-label="Rename current session" class="flex-1 text-teal-400 hover:bg-slate-800 text-xs font-bold py-1 rounded border border-slate-700 transition-colors">✏️ Rename</button>
                    <button onclick="deleteSingleSession()" title="Delete Selected Session" aria-label="Delete selected session" class="flex-1 text-amber-400 hover:bg-slate-800 text-xs font-bold py-1 rounded border border-slate-700 transition-colors">🗑️ Delete</button>
                    <button onclick="sanitizeSessions()" title="Sanitize/Clear All Sessions" aria-label="Sanitize all sessions" class="flex-1 text-rose-500 hover:bg-slate-800 text-xs font-bold py-1 rounded border border-slate-700 transition-colors">🧹 Clear All</button>
                </div>
            </div>

            <div class="flex flex-col gap-2 mt-4 pt-4 border-t border-slate-800">
                <button onclick="newConversation()" aria-label="Start a new conversation" class="w-full text-sm px-3 py-2 text-teal-400 hover:text-teal-200 hover:bg-slate-800 rounded-lg border border-teal-700/60 transition-colors font-bold">New Session</button>
                <button onclick="clearHistory()" aria-label="Clear chat history display" class="w-full text-sm px-3 py-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg border border-slate-700/60 transition-colors font-medium">Clear View</button>
                <button onclick="reloadBackend()" aria-label="Hot reload backend modules without restarting server" class="w-full text-sm px-3 py-2 text-teal-400 hover:text-teal-200 hover:bg-slate-800 rounded-lg border border-teal-800/60 transition-colors font-medium">↻ Reload Scripts</button>
                <button onclick="simulateHotPatch()" aria-label="Simulate an automated security hot-patch" class="w-full text-sm px-3 py-2 text-amber-400 hover:text-amber-200 hover:bg-amber-900/30 rounded-lg border border-amber-700/60 transition-colors font-medium">🛡️ Auto-Patch Event</button>
            </div>
        </div>
    </dialog>
"""

# Insert the dialog precisely before the </body> tag instead of after random </header> tags.
if '</body>' in html:
    html = html.replace('</body>', clean_dialog + '\n</body>')
else:
    # Fallback just in case
    html += clean_dialog

with open("templates/index.html", "w") as f:
    f.write(html)
    
print("Successfully removed duplicate dialogs, moved model selector, and deleted admin bypass checkbox.")
