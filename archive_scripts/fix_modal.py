import re

html_path = 'templates/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the HTML
old_html = """    <div id="custom-confirm-modal" class="hidden fixed inset-0 z-[200] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm opacity-0 transition-opacity duration-200">
        <div class="bg-slate-900 border border-slate-700 p-6 rounded-xl shadow-2xl max-w-sm w-full mx-4 transform scale-95 transition-transform duration-200">
            <h3 class="text-lg font-bold text-white mb-3" id="confirm-modal-title">Confirmation Required</h3>
            <p class="text-sm text-slate-300 mb-6" id="confirm-modal-message"></p>
            <div class="flex justify-end gap-3">
                <button id="confirm-modal-no" class="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors">Cancel</button>
                <button id="confirm-modal-yes" class="px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition-colors">Confirm</button>
            </div>
        </div>
    </div>"""

new_html = """    <dialog id="custom-confirm-modal" aria-labelledby="confirm-modal-title" aria-describedby="confirm-modal-message" class="bg-transparent p-0 m-auto backdrop:bg-slate-950/80 backdrop:backdrop-blur-sm">
        <div class="bg-slate-900 border border-slate-700 p-6 rounded-xl shadow-2xl max-w-sm w-full mx-4">
            <h3 class="text-lg font-bold text-white mb-3" id="confirm-modal-title">Confirmation Required</h3>
            <p class="text-sm text-slate-300 mb-6" id="confirm-modal-message"></p>
            <div class="flex justify-end gap-3">
                <button id="confirm-modal-no" class="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors focus:ring-2 focus:ring-teal-500 focus:outline-none">Cancel</button>
                <button id="confirm-modal-yes" class="px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition-colors focus:ring-2 focus:ring-teal-500 focus:outline-none">Confirm</button>
            </div>
        </div>
    </dialog>"""

if old_html in content:
    content = content.replace(old_html, new_html)

# Replace the JS
old_js = """        window.confirm = function(msg) {
            return new Promise(resolve => {
                const modal = document.getElementById('custom-confirm-modal');
                const modalBox = modal.querySelector('div');
                const msgEl = document.getElementById('confirm-modal-message');
                const btnYes = document.getElementById('confirm-modal-yes');
                const btnNo = document.getElementById('confirm-modal-no');
                
                msgEl.innerText = msg;
                
                // Show modal
                modal.classList.remove('hidden');
                requestAnimationFrame(() => {
                    modal.classList.remove('opacity-0');
                    modalBox.classList.remove('scale-95');
                });
                
                const cleanup = () => {
                    modal.classList.add('opacity-0');
                    modalBox.classList.add('scale-95');
                    setTimeout(() => modal.classList.add('hidden'), 200);
                    btnYes.removeEventListener('click', onYes);
                    btnNo.removeEventListener('click', onNo);
                };
                
                const onYes = () => { cleanup(); resolve(true); };
                const onNo = () => { cleanup(); resolve(false); };
                
                btnYes.addEventListener('click', onYes);
                btnNo.addEventListener('click', onNo);
            });
        };"""

new_js = """        window.confirm = function(msg) {
            return new Promise(resolve => {
                const modal = document.getElementById('custom-confirm-modal');
                const msgEl = document.getElementById('confirm-modal-message');
                const btnYes = document.getElementById('confirm-modal-yes');
                const btnNo = document.getElementById('confirm-modal-no');
                
                msgEl.innerText = msg;
                
                const cleanup = () => {
                    modal.close();
                    btnYes.removeEventListener('click', onYes);
                    btnNo.removeEventListener('click', onNo);
                    modal.removeEventListener('cancel', onCancel);
                };
                
                const onYes = () => { cleanup(); resolve(true); };
                const onNo = () => { cleanup(); resolve(false); };
                const onCancel = (e) => { e.preventDefault(); cleanup(); resolve(false); };
                
                btnYes.addEventListener('click', onYes);
                btnNo.addEventListener('click', onNo);
                modal.addEventListener('cancel', onCancel);
                
                modal.showModal();
            });
        };"""

if old_js in content:
    content = content.replace(old_js, new_js)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Modal refactored to native <dialog>.")
