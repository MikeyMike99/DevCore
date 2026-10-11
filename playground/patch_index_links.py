import os
path = "/mnt/c/Users/michael/Documents/DevCore/sandbox/templates/index.html"
with open(path, "r") as f: c = f.read()

target = """                    <div class="text-sm text-slate-400 break-all">
                        <a href="${escapeHtml(href)}" target="_blank" class="text-teal-400 hover:underline flex items-center gap-1 inline-flex">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            View Source File
                        </a>
                    </div>"""

repl = """                    <div class="text-sm text-slate-500 break-all font-mono">
                        <span class="flex items-center gap-1 inline-flex">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            ${escapeHtml(href)}
                        </span>
                    </div>"""

if target in c:
    c = c.replace(target, repl)
    with open(path, "w") as f: f.write(c)
    print("Frontend link patch applied")
else:
    print("Frontend link target not found")
