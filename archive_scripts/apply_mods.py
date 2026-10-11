import os
import subprocess
import sys

def apply():
    print("[ApplyMods] Applying custom workflow modifications...")
    
    base_dir = "/mnt/c/Users/michael/Documents/antigravity_test"
    venv_python = os.path.join(base_dir, "venv", "bin", "python3")
    
    # 1. Install Presidio
    print("[ApplyMods] Installing Presidio...")
    if os.path.exists(venv_python):
        subprocess.run([venv_python, "-m", "pip", "install", "presidio-analyzer", "presidio-anonymizer", "spacy"], check=False)
        subprocess.run([venv_python, "-m", "spacy", "download", "en_core_web_lg"], check=False)
        
    # 2. Re-create local_security.py
    print("[ApplyMods] Creating local_security.py...")
    local_sec_code = '''import os
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class LocalSecurity:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def scrub_text(self, text: str) -> str:
        if not text:
            return text
        results = self.analyzer.analyze(text=text, language='en')
        anonymized_result = self.anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized_result.text
'''
    with open(os.path.join(base_dir, "local_security.py"), "w") as f:
        f.write(local_sec_code)
        
    # 3. Patch index.html for Artifact UI and Proceed button
    print("[ApplyMods] Patching index.html...")
    index_path = os.path.join(base_dir, "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            html = f.read()
            
        if "proceedArtifact()" not in html:
            search_str = "        marked.use({ renderer: renderer, breaks: true, gfm: true });"
            inject_html = """        renderer.link = function(arg1, arg2, arg3) {
            var href, title, text;
            if (typeof arg1 === 'object' && arg1 !== null) {
                href = arg1.href; title = arg1.title; text = arg1.text || arg1.raw || arg1.href;
            } else {
                href = arg1; title = arg2; text = arg3 || arg1;
            }
            if (href && (href.includes('Implementation Plan') || href.includes('artifact') || (href.includes('/brain/') && href.endsWith('.md')))) {
                var artifactName = text || "Implementation Plan";
                return `
                <div class="my-4 border border-teal-500/40 rounded-xl p-5 bg-teal-900/20 flex flex-col gap-3 shadow-sm">
                    <div class="flex items-center gap-2 text-teal-300 font-bold text-lg">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                        ${escapeHtml(artifactName)}
                    </div>
                    <div class="text-sm text-slate-400 break-all">
                        <a href="${escapeHtml(href)}" target="_blank" class="text-teal-400 hover:underline flex items-center gap-1 inline-flex">View Source File</a>
                    </div>
                    <div class="flex mt-3 border-t border-teal-500/30 pt-4">
                        <button onclick="proceedArtifact()" class="bg-teal-600 hover:bg-teal-500 focus:ring-2 focus:ring-teal-400 focus:outline-none text-white font-medium py-2 px-5 rounded shadow transition-colors artifact-proceed-btn flex items-center gap-2">
                            Proceed (Alt+P)
                        </button>
                    </div>
                </div>`;
            }
            return `<a href="${escapeHtml(href||'')}" title="${escapeHtml(title||'')}" target="_blank" class="text-teal-400 hover:underline font-medium">${escapeHtml(text||href)}</a>`;
        };
        marked.use({ renderer: renderer, breaks: true, gfm: true });

        function proceedArtifact() {
            var prompt = "Proceed";
            var model = typeof modelSelector !== 'undefined' && modelSelector ? modelSelector.value : 'gemini-3.8-flash-high';
            if (typeof appendUserMessage === 'function') appendUserMessage(prompt);
            var adminOverride = document.getElementById('admin-override-checkbox') ? document.getElementById('admin-override-checkbox').checked : false;
            if (typeof ws !== 'undefined' && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'prompt', prompt: prompt, model: model, conversation_id: typeof currentConversationId !== 'undefined' ? currentConversationId : null, admin_override: adminOverride, token: typeof authToken !== 'undefined' ? authToken : '' }));
            }
        }
        document.addEventListener('keydown', function(e) {
            if (e.altKey && e.key.toLowerCase() === 'p') {
                e.preventDefault();
                var btns = document.querySelectorAll('.artifact-proceed-btn');
                if (btns.length > 0) btns[btns.length - 1].click();
            }
        });"""
            html = html.replace(search_str, inject_html)
            with open(index_path, "w") as f:
                f.write(html)

    # 4. Patch agent_manager.py
    print("[ApplyMods] Patching agent_manager.py...")
    agent_path = os.path.join(base_dir, "agent_manager.py")
    if os.path.exists(agent_path):
        with open(agent_path, "r") as f:
            am = f.read()
            
        if "self._get_security()" not in am:
            # 4a. Add the _get_security method
            init_str = "self._lock = asyncio.Lock()"
            if init_str in am:
                inject_sec = """self._lock = asyncio.Lock()
        self._local_sec = None

    def _get_security(self):
        if self._local_sec is None:
            try:
                from local_security import LocalSecurity
                self._local_sec = LocalSecurity()
            except ImportError:
                class Dummy:
                    def scrub_text(self, t): return t
                self._local_sec = Dummy()
        return self._local_sec"""
                am = am.replace(init_str, inject_sec)
                
            # 4b. Patch the agent chunk streaming
            target_chunk1 = """                            if delta:
                                self.output_buffer.append(delta)
                                await self.broadcast({"type": "agent_chunk", "chunk": delta})"""
            replace_chunk1 = """                            if delta:
                                delta = self._get_security().scrub_text(delta)
                                self.output_buffer.append(delta)
                                await self.broadcast({"type": "agent_chunk", "chunk": delta})"""
            am = am.replace(target_chunk1, replace_chunk1)
            
            # 4c. Patch the result finish
            target_chunk2 = """                        if not self.output_buffer and final_resp:
                            self.output_buffer.append(final_resp)
                            await self.broadcast({"type": "agent_chunk", "chunk": final_resp})"""
            replace_chunk2 = """                        if not self.output_buffer and final_resp:
                            final_resp = self._get_security().scrub_text(final_resp)
                            self.output_buffer.append(final_resp)
                            await self.broadcast({"type": "agent_chunk", "chunk": final_resp})"""
            am = am.replace(target_chunk2, replace_chunk2)

            with open(agent_path, "w") as f:
                f.write(am)
                
if __name__ == "__main__":
    apply()
