import re

html_path = 'templates/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_hero = r"""            <!-- Initial Welcome Card -->
            <article class="p-4 rounded-xl bg-slate-900/90 text-slate-300 border border-slate-800 shadow-sm flex gap-3 message-welcome" aria-labelledby="welcome-heading">
                <div class="w-7 h-7 rounded bg-teal-900/60 border border-teal-700/50 text-teal-300 flex items-center justify-center shrink-0 text-xs font-bold mt-0.5" aria-hidden="true">
                    AG
                </div>
                <div class="text-sm">
                    <h2 id="welcome-heading" class="font-bold text-teal-400 text-sm mb-1">Antigravity Dev Portal Ready</h2>
                    <p class="mb-2">Accessible interface with live screen reader announcements, clean heading navigation (press <strong>H</strong> or <strong>2</strong> to navigate messages), collapsed action logs, and model selection.</p>
                    <p class="text-xs text-slate-400">Tasks run as resilient background processes. Page reloads or disconnections will not cancel active tasks.</p>
                </div>
            </article>"""

new_hero = """            <!-- Initial Welcome Card (A11y Optimized) -->
            <article class="p-5 rounded-xl bg-slate-900/90 text-slate-300 border border-slate-800 shadow-sm flex flex-col gap-4 message-welcome" aria-labelledby="welcome-heading">
                <header class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded bg-teal-900/60 border border-teal-700/50 text-teal-300 flex items-center justify-center shrink-0 text-sm font-bold" aria-hidden="true">AG</div>
                    <h2 id="welcome-heading" class="font-bold text-teal-400 text-lg m-0" aria-live="polite">Antigravity Dev Portal Ready</h2>
                </header>

                <div class="text-sm space-y-5">
                    <section aria-labelledby="status-heading">
                        <h3 id="status-heading" class="sr-only">System Status</h3>
                        <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm bg-slate-950 p-4 rounded-lg border border-slate-800">
                            <dt class="font-semibold text-slate-400">Connection Status:</dt>
                            <dd class="text-teal-300">Secure & Resilient</dd>
                            <dt class="font-semibold text-slate-400">Background Tasks:</dt>
                            <dd class="text-slate-200">0 Running</dd>
                            <dt class="font-semibold text-slate-400">Navigation:</dt>
                            <dd class="text-slate-200">Press <kbd class="bg-slate-800 px-1 rounded sr-only">H</kbd><span aria-hidden="true" class="bg-slate-800 px-1 rounded font-mono text-xs">H</span> or <kbd class="bg-slate-800 px-1 rounded sr-only">2</kbd><span aria-hidden="true" class="bg-slate-800 px-1 rounded font-mono text-xs">2</span> for messages</dd>
                        </dl>
                    </section>

                    <nav aria-label="Quick Actions">
                        <ul class="space-y-3">
                            <li>
                                <button type="button" class="w-full text-left px-4 py-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-teal-400 font-medium focus:ring-2 focus:ring-teal-500 focus:outline-none transition-colors flex flex-col gap-1" onclick="document.getElementById('prompt').value = 'Create a new Sandbox Environment'; document.getElementById('prompt').focus();" aria-keyshortcuts="Alt+S">
                                    <span class="text-base">Create Sandbox Environment</span>
                                    <span class="text-xs text-slate-400 sr-only">Shortcut: Alt plus S. Injects prompt into chat input.</span>
                                </button>
                            </li>
                            <li>
                                <button type="button" class="w-full text-left px-4 py-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-teal-400 font-medium focus:ring-2 focus:ring-teal-500 focus:outline-none transition-colors flex flex-col gap-1" onclick="document.getElementById('prompt').value = 'Analyze system logs for the last 24 hours'; document.getElementById('prompt').focus();" aria-keyshortcuts="Alt+L">
                                    <span class="text-base">Analyze System Logs</span>
                                    <span class="text-xs text-slate-400 sr-only">Shortcut: Alt plus L. Injects prompt into chat input.</span>
                                </button>
                            </li>
                            <li>
                                <button type="button" class="w-full text-left px-4 py-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-teal-400 font-medium focus:ring-2 focus:ring-teal-500 focus:outline-none transition-colors flex flex-col gap-1" onclick="document.getElementById('prompt').focus();" aria-keyshortcuts="Alt+C">
                                    <span class="text-base">Jump to Chat Input</span>
                                    <span class="text-xs text-slate-400 sr-only">Shortcut: Alt plus C. Moves focus to text area.</span>
                                </button>
                            </li>
                        </ul>
                    </nav>
                </div>
            </article>"""

content = content.replace(old_hero, new_hero)

update_ui_old = """        function updateUserUI() {
            var roleBadge = document.getElementById('user-role-badge');
            var displayName = document.getElementById('user-display-name');
            if (roleBadge) {"""

update_ui_new = """        function updateUserUI() {
            var roleBadge = document.getElementById('user-role-badge');
            var displayName = document.getElementById('user-display-name');
            var welcomeHeading = document.getElementById('welcome-heading');
            
            if (welcomeHeading && currentUser && currentUser.role) {
                let roleName = currentUser.role.replace('_', ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                welcomeHeading.innerText = roleName + " Dashboard Ready";
            }
            
            if (roleBadge) {"""

content = content.replace(update_ui_old, update_ui_new)

# Add keyboard shortcuts listener globally
shortcut_script = """        document.addEventListener('keydown', function(e) {
            if (e.altKey && e.key.toLowerCase() === 's') {
                e.preventDefault();
                document.getElementById('prompt').value = 'Create a new Sandbox Environment';
                document.getElementById('prompt').focus();
            } else if (e.altKey && e.key.toLowerCase() === 'l') {
                e.preventDefault();
                document.getElementById('prompt').value = 'Analyze system logs for the last 24 hours';
                document.getElementById('prompt').focus();
            } else if (e.altKey && e.key.toLowerCase() === 'c') {
                e.preventDefault();
                document.getElementById('prompt').focus();
            }
        });
"""
# Insert before </script>
content = content.replace('</script>', shortcut_script + '\n    </script>')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Hero section and JS updated for A11y.")
